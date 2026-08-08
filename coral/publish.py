"""The publishing job's step, which is the one place a review or a failure reaches the pull request.

The review job composes and posts nothing; it hands over the finished create-review bodies, or a
reason file when it failed, and this step posts whichever the run earned. The failure comment
covers a review job that died whole — GitHub's own timeout, a vanished runner — as well: no reason
crossed, so the comment goes out without one.

What it does not cover is a death that leaves no publishing job to run: a cancelled run starts
none, and a setup failure leaves no console script. Those are visible in the Actions tab and
nowhere else, and the recovery is asking again.
"""

import json
import logging
import os
from typing import Any, Final

from coral import runner
from coral.command import Access, is_request
from coral.github.client import GitHub
from coral.github.post import (
    post_comment,
    post_issue,
    post_review,
    read_issue_payloads,
    read_payloads,
    state_of,
)
from coral.runner import Event

log = logging.getLogger(__name__)

# What a comment carries of an exception message. It bounds a comment body against a message with
# no bound of its own, a provider error arriving as a page of JSON being the case that needs it.
REASON_LIMIT: Final = 1_000


def described(error: BaseException) -> str:
    """The exception as the pull request sees it: its type, its message, and no more than fits."""
    reason = f"{type(error).__name__}: {error}"
    if len(reason) <= REASON_LIMIT:
        return reason
    return reason[: REASON_LIMIT - 1] + "…"


def failure_comment(reason: str | None, run_url: str) -> str:
    """What Coral says when a run produced no review."""
    fenced = []
    if reason is not None:
        # Four backticks, so a message carrying a fence of its own cannot close this one and
        # reshape the comment around it.
        fenced = ["", "````", reason, "````"]
    return "\n".join(
        [
            "Coral did not review this change: the run failed.",
            *fenced,
            "",
            f"The run is at {run_url}.",
            "",
            "Comment `/coral` to ask for a fresh review.",
        ]
    )


def moved_comment(commit: str) -> str:
    """What Coral says when the branch moved out from under a finished review."""
    return "\n".join(
        [
            f"Coral reviewed `{commit}`, which is no longer the head of this pull request. The "
            "findings are about code the branch no longer carries, so Coral has not posted them.",
            "",
            "Comment `/coral` to ask for a review of the current head.",
        ]
    )


def owed(event: Event, access: Access) -> bool:
    """Whether this run owes the pull request a comment about failing.

    Deciding it costs a permission lookup on the comment paths, and a lookup GitHub refuses
    answers no. Silence is the right way to be wrong here: a comment nobody asked for is Coral
    made to speak by a stranger, and posting the comment needs the same API anyway.
    """
    # The job-level condition is coarse, so a comment merely mentioning `/coral` mid-sentence
    # allocates a runner, and a run that fails there was asked for nothing. A `pull_request`
    # delivery always asks, the condition having already excluded drafts and bots.
    if event.comment is not None and not is_request(
        event.comment.body, event.comment.author, access
    ):
        log.info("The comment that started this run does not ask for a review.")
        return False

    return True


def pinned_commit() -> str | None:
    """The commit resolve pinned, when it got as far as writing the pull request down.

    Reading that file is not the same as knowing the run proceeded — resolve writes it before the
    gates — but the commit on the comment is a label rather than a decision.
    """
    path = runner.pull_request_path()
    if not path.exists():
        return None
    pull_request: dict[str, Any] = json.loads(path.read_text())
    return str(pull_request["head"]["sha"])


def publish() -> None:
    """Post the review this run produced, or say why there is none.

    Which job failed is not named: the run link is one click from that. The commit comes off
    resolve's pull request and never off the review job's artifact, because it is one of the two
    fields the publishing job does not take on trust.
    """
    event = runner.event()
    github = GitHub(token=os.environ["GITHUB_TOKEN"])

    if runner.issues_path().exists():
        assert event.push is not None, "A main-push issue payload needs a push event."
        for payload in read_issue_payloads(runner.issues_path()).issues:
            post_issue(github, event.owner, event.repo, payload)
        return

    if runner.payloads_path().exists():
        assert event.number is not None, "A pull-request review payload needs a pull request event."
        commit = pinned_commit()
        assert commit is not None, "The review crossed without resolve's pull request."
        # Resolve's reading was minutes and two agent runs ago.
        state = state_of(github, event.owner, event.repo, event.number)
        # A review landing after the merge is advice nobody can act on.
        if not state.open:
            log.info("Pull request %d is no longer open; posting nothing.", event.number)
            return
        # A force-push during the review leaves findings about code the branch no longer carries,
        # and GitHub takes them anyway whenever the reviewed commit is still somewhere in the new
        # history. Said on the pull request rather than passed over: nothing re-triggers Coral
        # after a push, so silence leaves the asker waiting for a review that is not coming.
        if state.head_sha != commit:
            log.info(
                "Pull request %d moved from %s to %s; posting no review.",
                event.number,
                commit,
                state.head_sha,
            )
            post_comment(
                github, event.owner, event.repo, event.number, commit, moved_comment(commit)
            )
            return
        post_review(
            github,
            event.owner,
            event.repo,
            event.number,
            commit,
            read_payloads(runner.payloads_path()),
        )
        return

    if event.push is not None:
        log.info("The main-push review produced no issues.")
        return

    assert event.number is not None
    if not owed(event, Access(github=github, owner=event.owner, repo=event.repo)):
        return

    reason = runner.reason_path().read_text() if runner.reason_path().exists() else None
    log.info("Reporting on pull request %d that the run failed.", event.number)
    post_comment(
        github,
        event.owner,
        event.repo,
        event.number,
        pinned_commit(),
        failure_comment(reason, runner.run_url()),
    )
