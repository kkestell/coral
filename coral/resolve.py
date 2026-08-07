"""The gatekeeper step: fetch the pull request, acknowledge the requests, decide whether to go on.

A decline is not a failure. This step writes `proceed=false`, says why, and exits zero, and the
checkout and review steps skip. A pull request Coral was never going to review is not a broken
pull request.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Final

from coral import runner
from coral.command import is_request
from coral.github.client import GitHub
from coral.github.conversation import Conversation, bound, fetch_conversation, write_conversation
from coral.github.post import post_comment
from coral.github.reactions import Request, react, requests_in
from coral.runner import Event

log = logging.getLogger(__name__)

# The change-size backstop, read off the pull request fetch and so costing no call of its own.
# Both numbers are chosen rather than measured, and both sit well above anything somebody opens
# by hand. Item 9 on the roadmap settles them against real pull requests.
MAX_CHANGED_FILES: Final = 300
MAX_CHANGED_LINES: Final = 30_000


@dataclass(frozen=True)
class Subject:
    """The fetched pull request reduced to the fields the gates read.

    The gates read this rather than the raw JSON, so none of them reaches into a nested payload
    and their tests do not have to build one.
    """

    state: str
    head_sha: str
    # `None` when the head repository is gone, which is what a deleted fork looks like.
    head_repo_id: int | None
    base_repo_id: int
    changed_files: int
    changed_lines: int


@dataclass(frozen=True)
class Decline:
    """Why the run stops, and the comment that reason owes the pull request."""

    reason: str
    comment: str | None


def subject_of(pull_request: dict[str, Any]) -> Subject:
    """Reduce the pull request the fetch returned to what the gates decide on."""
    head = pull_request["head"]["repo"]
    return Subject(
        state=pull_request["state"],
        head_sha=pull_request["head"]["sha"],
        head_repo_id=head["id"] if head else None,
        base_repo_id=pull_request["base"]["repo"]["id"],
        changed_files=pull_request["changed_files"],
        changed_lines=pull_request["additions"] + pull_request["deletions"],
    )


def acknowledgments(event: Event, conversation: Conversation) -> list[Request]:
    """Every request waiting on this run: the conversation's, and the one on the payload.

    The triggering comment is read off the payload rather than out of the conversation. It is
    nearly always in there, and nearly always is not always — the conversation is bounded, a
    thread is read twenty comments deep, and the paging stops after four pages — so a request on
    a busy pull request can be one the fetch did not offer. It is dropped from the conversation's
    list when the conversation produced it as well.
    """
    requests = requests_in(conversation)
    if event.comment is None or not is_request(event.comment.body, event.comment.association):
        return requests
    triggering = Request(id=event.comment.id, namespace=event.comment.namespace)
    return [triggering, *(request for request in requests if request != triggering)]


def declined(event: Event, subject: Subject, conversation: Conversation) -> Decline | None:
    """The reason this run stops, or `None` when there is a review to do.

    The order is what decides which reason a person is given when more than one applies. A
    closed pull request and a fork are both reasons Coral was never going to look at this change
    at all, so neither is reported as the change being too large.
    """
    # Comment paths only. There was no request, so there was nothing to acknowledge either, and
    # the reaction pass skipped this comment for the same reason.
    if event.comment is not None and not is_request(event.comment.body, event.comment.association):
        return Decline(reason="the comment does not ask for a review", comment=None)

    # A review that lands after the merge is advice nobody can act on.
    if subject.state != "open":
        return Decline(reason=f"the pull request is {subject.state}", comment=None)

    # Ids rather than names, because a repository can be renamed and an id cannot be reused. A
    # head repository that is gone is a deleted fork, and is treated as a fork.
    if subject.head_repo_id != subject.base_repo_id:
        return Decline(reason="the head branch lives in a fork", comment=None)

    # The two automatic paths only: a pull request opened ready, converted to draft, and marked
    # ready again. Somebody who asks gets a review whether or not the code has moved.
    if event.comment is None and subject.head_sha in conversation.reviewed_commits:
        return Decline(reason=f"Coral has already reviewed {subject.head_sha}", comment=None)

    # The one stop that says so on the pull request. Every other gate is silent and can be: an
    # inert command asked for nothing, a closed pull request and a fork are states a person can
    # see, and a commit already reviewed has Coral's earlier review sitting on it. This is the
    # only one that leaves somebody waiting for a review that is not coming with nothing on the
    # pull request to explain it, and the only one that can stop an automatic review.
    if subject.changed_files > MAX_CHANGED_FILES or subject.changed_lines > MAX_CHANGED_LINES:
        return Decline(
            reason=(
                f"the change is {subject.changed_files} files and {subject.changed_lines} lines"
            ),
            comment=(
                f"This change is {subject.changed_files} files and {subject.changed_lines} "
                "lines, which exceeds what Coral will read. Coral has not reviewed it."
            ),
        )

    return None


def resolve() -> None:
    """Pin the commits Coral will review, or stop the run."""
    event = runner.event()
    github = GitHub(token=os.environ["GITHUB_TOKEN"])
    pull_request = github.get(f"/repos/{event.owner}/{event.repo}/pulls/{event.number}")

    # Verbatim, because the review step reads the head SHA, the base SHA, the number, and the
    # repository back out of it rather than fetching the pull request a second time.
    runner.pull_request_path().write_text(json.dumps(pull_request))

    conversation = bound(fetch_conversation(github, event.owner, event.repo, event.number))
    write_conversation(runner.conversation_path(), conversation)
    log.info(
        "The conversation holds %d comments, %d reviews, and %d threads, with %d left unread. "
        "Coral has already reviewed %d commits of this pull request.",
        len(conversation.comments),
        len(conversation.reviews),
        len(conversation.threads),
        conversation.bound.unread,
        len(conversation.reviewed_commits),
    )

    # The reaction is the acknowledgment. It comes after the conversation because the request
    # that started this run is not the only one waiting on it, and every request in the
    # conversation is owed one. It comes before every gate because somebody whose request Coral
    # is about to decline still deserves to be told it was heard, and a comment-triggered run
    # gives them no other sign.
    requests = acknowledgments(event, conversation)
    log.info("Acknowledging %d requests.", len(requests))
    react(github, event.owner, event.repo, requests)

    subject = subject_of(pull_request)
    decline = declined(event, subject, conversation)
    if decline is not None:
        log.info("Not reviewing pull request %d: %s.", event.number, decline.reason)
        if decline.comment is not None:
            post_comment(
                github,
                event.owner,
                event.repo,
                event.number,
                subject.head_sha,
                decline.comment,
            )
        runner.write_output("proceed", "false")
        return

    runner.write_output("head-sha", subject.head_sha)
    runner.write_output("proceed", "true")
