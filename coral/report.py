"""The report step, and the prose both halves of the failure path post.

Two steps can report a failure and only one of them ever does. The review step catches its own,
because it is the step holding the reason. This step runs on job failure and covers everything
before it, where the reason never reached Coral at all. They meet at `runner.reported_path()`.
"""

import json
import logging
import os
from typing import Any, Final

from coral import runner
from coral.command import is_request
from coral.github.client import GitHub
from coral.github.post import post_comment
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

    Neither question costs an API call, which matters: the failure being reported is often the API
    refusing to answer.
    """
    if runner.reported_path().exists():
        log.info("The review step already reported this failure.")
        return False

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


def report() -> None:
    """The report step: say that the run failed, unless the review step already did.

    The comment carries no reason. This step never saw the exception, and the step that did is the
    step that posts it. Which step failed is not named either: the run link is one click from that.
    """
    event = runner.event()
    if not owed(event):
        return

    github = GitHub(token=os.environ["GITHUB_TOKEN"])
    log.info("Reporting on pull request %d that the run failed.", event.number)
    post_comment(
        github,
        event.owner,
        event.repo,
        event.number,
        pinned_commit(),
        failure_comment(None, runner.run_url()),
    )
