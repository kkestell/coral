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
from coral.command import is_request
from coral.github.client import GitHub
from coral.github.post import is_open, post_comment, post_review, read_payloads
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


def owed(event: Event) -> bool:
    """Whether this run owes the pull request a comment about failing.

    The question costs no API call, which matters: the failure being reported is often the API
    refusing to answer.
    """
    # The job-level condition is coarse, so a comment merely mentioning `/coral` mid-sentence
    # allocates a runner, and a run that fails there was asked for nothing. A `pull_request`
    # delivery always asks, the condition having already excluded drafts and bots.
    if event.comment is not None and not is_request(event.comment.body, event.comment.association):
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

    if runner.payloads_path().exists():
        github = GitHub(token=os.environ["GITHUB_TOKEN"])
        # Resolve's check was minutes and two agent runs ago, and a review landing after the
        # merge is advice nobody can act on.
        if not is_open(github, event.owner, event.repo, event.number):
            log.info("Pull request %d is no longer open; posting nothing.", event.number)
            return
        commit = pinned_commit()
        assert commit is not None, "The review crossed without resolve's pull request."
        post_review(
            github,
            event.owner,
            event.repo,
            event.number,
            commit,
            read_payloads(runner.payloads_path()),
        )
        return

    if not owed(event):
        return

    reason = runner.reason_path().read_text() if runner.reason_path().exists() else None
    github = GitHub(token=os.environ["GITHUB_TOKEN"])
    log.info("Reporting on pull request %d that the run failed.", event.number)
    post_comment(
        github,
        event.owner,
        event.repo,
        event.number,
        pinned_commit(),
        failure_comment(reason, runner.run_url()),
    )
