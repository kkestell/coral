"""What every subcommand needs from the Actions runner: the event, step outputs, and paths.

Every value here comes out of `os.environ` by subscript. A missing variable is a broken
invocation rather than an input to recover from, and a `KeyError` naming the variable is the
clearest thing that can happen.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class Comment:
    """The comment that triggered this run, and the namespace its reaction endpoint lives in.

    The body and the author come along because this comment is not always in the fetched
    conversation, and the payload is the only place they can be read without another call.
    """

    id: int
    namespace: Literal["issues", "pulls"]
    body: str
    # `None` when the account that wrote it has been deleted, which is how the conversation reads
    # an author too. Nobody is left to ask about, so the access check refuses it.
    author: str | None


@dataclass(frozen=True)
class Event:
    """The delivery that started this run, reduced to what Coral acts on."""

    name: str
    owner: str
    repo: str
    number: int
    comment: Comment | None


def commented(payload: dict[str, Any], namespace: Literal["issues", "pulls"]) -> Comment:
    """The comment off a comment delivery. Both comment events carry it under the same key."""
    comment = payload["comment"]
    return Comment(
        id=comment["id"],
        namespace=namespace,
        body=comment["body"],
        author=comment["user"]["login"] if comment["user"] else None,
    )


def event() -> Event:
    """Read the delivery GitHub wrote to disk for this job."""
    name = os.environ["GITHUB_EVENT_NAME"]
    owner, repo = os.environ["GITHUB_REPOSITORY"].split("/")
    payload: dict[str, Any] = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())

    # The workflow's `on:` block is the only thing that can produce a name here, so a fourth one
    # is a broken workflow file rather than an event Coral has to understand.
    match name:
        case "pull_request":
            number = payload["pull_request"]["number"]
            comment = None
        case "issue_comment":
            number = payload["issue"]["number"]
            comment = commented(payload, "issues")
        case "pull_request_review_comment":
            number = payload["pull_request"]["number"]
            comment = commented(payload, "pulls")
        case _:
            raise AssertionError(f"Coral was invoked on a {name} event, which it does not handle.")

    return Event(name=name, owner=owner, repo=repo, number=number, comment=comment)


def write_output(name: str, value: str) -> None:
    """Publish a step output for the YAML that reads it."""
    # Every value Coral writes is one line — a SHA, a boolean, or a minted key — so the heredoc
    # form of the Actions protocol is not built. The assertion is what stops a later caller
    # assuming multiline works.
    assert "\n" not in value, f"Step output {name} holds a newline: {value!r}"
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"{name}={value}\n")


def temporary_directory() -> Path:
    """Coral's directory under the runner's temporary directory, outside the workspace."""
    directory = Path(os.environ["RUNNER_TEMP"]) / "coral"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def pull_request_path() -> Path:
    """Where resolve leaves the pull request for the later jobs to read.

    The file crosses a job boundary as an artifact, so the temporary directory it is written in
    is not the one it is read in. It sits outside the workspace, where the checkout cannot
    disturb it, and it is what keeps the pull request fetched once rather than three times.
    """
    return temporary_directory() / "pull-request.json"


def conversation_path() -> Path:
    """Where resolve leaves the conversation for the review job to read.

    The file crosses a job boundary as an artifact, so the temporary directory it is written in
    is not the one it is read in. The conversation is the largest thing that crosses.
    """
    return temporary_directory() / "conversation.json"


def payloads_path() -> Path:
    """Where the review job leaves the two create-review bodies for the publishing job to post.

    The file crosses a job boundary as an artifact, so the temporary directory it is written in
    is not the one it is read in. Its absence is how the publishing job knows no review was
    produced.
    """
    return temporary_directory() / "review-payloads.json"


def reason_path() -> Path:
    """Where the review job leaves why it failed for the publishing job's comment to carry.

    The file crosses a job boundary as an artifact, so the temporary directory it is written in
    is not the one it is read in. A review job that died whole leaves none, and the failure
    comment goes out without a reason.
    """
    return temporary_directory() / "reason.txt"


def checkout_copy_path(name: str) -> Path:
    """Where one agent run's own copy of the checkout lives.

    Inside Coral's temporary directory rather than the workspace, so nothing an agent writes ends
    up in the tree `coral/diff.py` reads. The artifact steps upload named files, so a directory
    sitting beside them never crosses a job boundary.
    """
    return temporary_directory() / name


def run_url() -> str:
    """This job's run in the Actions tab, which is where a failure comment sends the reader."""
    server = os.environ["GITHUB_SERVER_URL"]
    repository = os.environ["GITHUB_REPOSITORY"]
    return f"{server}/{repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}"


def workspace() -> Path:
    """Where the checkout lives. This is the one place that knows."""
    return Path(os.environ["GITHUB_WORKSPACE"])
