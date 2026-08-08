"""The gatekeeper step: fetch the pull request, acknowledge the requests, decide whether to go on.

A decline is not a failure. This step writes `proceed=false`, says why, and exits zero, and the
checkout and review steps skip. A pull request Coral was never going to review is not a broken
pull request.
"""

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any, Final

from coral import runner
from coral.command import Access, is_request
from coral.deadline import job_timeout_minutes
from coral.github.client import GitHub
from coral.github.conversation import Conversation, bound, fetch_conversation, write_conversation
from coral.github.post import count, post_comment
from coral.github.reactions import Request, react, requests_in
from coral.handoff import encrypt, encryption_key
from coral.openrouter import key_ttl_seconds, mint
from coral.publish import described
from coral.runner import Event
from coral.spend import cap_dollars

log = logging.getLogger(__name__)

# The change-size backstop, read off the pull request fetch and so costing no call of its own.
# Measured against real pull requests in `kkestell/coral-test` sized at 290 files/290 lines and
# at 1 file/29,500 lines, both under the backstop: each reviewed in under a minute, nowhere near
# the deadline or the shell ceiling. Both numbers hold as chosen.
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


def management_key(passed: str, api_key_present: bool) -> str | None:
    """The management key to mint this run's key with, or `None` for a plain key passed through.

    Exactly one of the two secrets. Neither leaves the review job with no credential at all, and
    both leave Coral choosing on the caller's behalf between two keys they told it about. Which
    kind a single secret holds is never detected: that costs a probe request to answer a question
    the caller already knows.
    """
    if bool(passed) == api_key_present:
        held = "both of them" if api_key_present else "neither"
        raise RuntimeError(
            "Coral takes exactly one of the `openrouter_api_key` and `openrouter_management_key` "
            f"secrets, and this run was passed {held}. Pass the one you created."
        )
    return passed or None


def handoff_key(management: str | None, passed: str) -> str | None:
    """Validate the handoff key only when management mode will mint a credential."""
    return encryption_key(passed) if management is not None else None


def reported[T](work: Callable[[], T]) -> T:
    """Run something whose failure the pull request is owed the words of, then re-raise.

    Resolve's other failures reach the pull request as a comment with no reason. A broken
    OpenRouter secret has something to say — OpenRouter's own refusal — and this is the same
    reason file the review step writes, read by the same publishing step.
    """
    try:
        return work()
    except Exception as error:
        runner.reason_path().write_text(described(error))
        raise


def acknowledgments(event: Event, conversation: Conversation, access: Access) -> list[Request]:
    """Every request waiting on this run: the conversation's, and the one on the payload.

    The triggering comment is read off the payload rather than out of the conversation. It is
    nearly always in there, and nearly always is not always — the conversation is bounded, a long
    thread is read at both ends and not through the middle, and the paging stops after four pages
    — so a request on a busy pull request can be one the fetch did not offer. It is dropped from
    the conversation's list when the conversation produced it as well.
    """
    requests = requests_in(conversation, access)
    if event.comment is None or not is_request(event.comment.body, event.comment.author, access):
        return requests
    triggering = Request(id=event.comment.id, namespace=event.comment.namespace)
    return [triggering, *(request for request in requests if request != triggering)]


def declined(
    event: Event, subject: Subject, conversation: Conversation, access: Access
) -> Decline | None:
    """The reason this run stops, or `None` when there is a review to do.

    The order is what decides which reason a person is given when more than one applies. A
    closed pull request and a fork are both reasons Coral was never going to look at this change
    at all, so neither is reported as the change being too large.
    """
    # Comment paths only. There was no request, so there was nothing to acknowledge either, and
    # the reaction pass skipped this comment for the same reason.
    if event.comment is not None and not is_request(
        event.comment.body, event.comment.author, access
    ):
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
        size = f"{count(subject.changed_files, 'file')} and {count(subject.changed_lines, 'line')}"
        return Decline(
            reason=f"the change is {size}",
            comment=(
                f"This change is {size}, which exceeds what Coral will read. Coral has not "
                "reviewed it."
            ),
        )

    return None


def resolve() -> None:
    """Pin the commits Coral will review, or stop the run."""
    # Checked before the fetch, so a budget the caller got wrong is loud on every triggered run
    # rather than only on the ones that reach a review, and here rather than in the review job
    # because this is where the number the review job's `timeout-minutes` reads is derived from it.
    timeout = reported(lambda: job_timeout_minutes(os.environ["CORAL_TIME_BUDGET_MINUTES"]))
    log.info(
        "A budget of %s minutes, so the review job gets a timeout of %d.",
        os.environ["CORAL_TIME_BUDGET_MINUTES"],
        timeout,
    )

    # Also before the fetch, and for the same reason the budget is. The same number is the limit
    # the minted key is created with; the review job validates it again to build the ledger its own
    # accounting runs against.
    cap = reported(lambda: cap_dollars(os.environ["CORAL_SPEND_CAP_DOLLARS"]))

    event = runner.event()
    github = GitHub(token=os.environ["GITHUB_TOKEN"])
    access = Access(github=github, owner=event.owner, repo=event.repo)
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
    requests = acknowledgments(event, conversation, access)
    log.info("Acknowledging %d requests.", len(requests))
    react(github, event.owner, event.repo, requests)

    subject = subject_of(pull_request)
    decline = declined(event, subject, conversation, access)
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

    # After the gates rather than before the fetch, because a fork's pull request arrives with no
    # secrets at all: GitHub withholds every secret but `GITHUB_TOKEN` from a fork-triggered run,
    # so checking here would refuse a run Coral was going to decline anyway, and refuse it with a
    # comment the fork's read-only token cannot post. The plain key's value never comes here; the
    # review job reads that secret itself, and all resolve is told is whether it exists.
    management = reported(
        lambda: management_key(
            os.environ["OPENROUTER_MANAGEMENT_KEY"],
            os.environ["OPENROUTER_API_KEY_PRESENT"] == "true",
        )
    )
    encryption = reported(lambda: handoff_key(management, os.environ["CORAL_KEY_ENCRYPTION_KEY"]))

    # After the gates, so a declined run mints nothing, and before the outputs, so a mint that
    # fails leaves no `proceed=true` behind it. The key is named for the run, which is what ties
    # a key in the OpenRouter dashboard to the review that asked for it.
    if management is not None:
        minted = partial(mint, management, runner.run_url(), key_ttl_seconds(timeout), cap)
        api_key = reported(minted)
        runner.mask(api_key)
        assert encryption is not None
        runner.write_output("encrypted-key", reported(lambda: encrypt(encryption, api_key)))

    runner.write_output("head-sha", subject.head_sha)
    runner.write_output("timeout-minutes", str(timeout))
    runner.write_output("proceed", "true")
