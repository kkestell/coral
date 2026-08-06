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
    """The comment that triggered this run, and the namespace its reaction endpoint lives in."""

    id: int
    namespace: Literal["issues", "pulls"]


@dataclass(frozen=True)
class Event:
    """The delivery that started this run, reduced to what Coral acts on."""

    name: str
    owner: str
    repo: str
    number: int
    comment: Comment | None


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
            comment = Comment(id=payload["comment"]["id"], namespace="issues")
        case "pull_request_review_comment":
            number = payload["pull_request"]["number"]
            comment = Comment(id=payload["comment"]["id"], namespace="pulls")
        case _:
            raise AssertionError(f"Coral was invoked on a {name} event, which it does not handle.")

    return Event(name=name, owner=owner, repo=repo, number=number, comment=comment)


def write_output(name: str, value: str) -> None:
    """Publish a step output for the YAML that reads it."""
    # Every value Coral writes is a SHA or a boolean, so the heredoc form of the Actions protocol
    # is not built. The assertion is what stops a later caller assuming multiline works.
    assert "\n" not in value, f"Step output {name} holds a newline: {value!r}"
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"{name}={value}\n")


def temporary_directory() -> Path:
    """Coral's directory under the runner's temporary directory, outside the workspace."""
    directory = Path(os.environ["RUNNER_TEMP"]) / "coral"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def pull_request_path() -> Path:
    """Where resolve leaves the pull request for review to read.

    The pull request is too big for a step output and the temporary directory is outside the
    workspace, so the checkout between the two steps cannot disturb it. This is what keeps the
    pull request fetched once rather than twice.
    """
    return temporary_directory() / "pull-request.json"


def workspace() -> Path:
    """Where the checkout lives. This is the one place that knows."""
    return Path(os.environ["GITHUB_WORKSPACE"])
