"""The review step: compute the diff, produce the review, post it."""

import json
import logging
import os

from coral import runner
from coral.diff import AddedLine, added_lines, merge_base
from coral.github.client import GitHub
from coral.github.post import post_review
from coral.schema import Anchor, Finding, LineAnchor, PullRequestAnchor, Review

log = logging.getLogger(__name__)


def produce_review(added: list[AddedLine]) -> Review:
    """Where the agent goes. Until then, one hardcoded finding on a line out of the diff."""
    summary = (
        "Coral ran end to end and made no model call. This review is hardcoded and says nothing "
        "about the change."
    )
    anchor: Anchor
    if added:
        first = added[0]
        anchor = LineAnchor(kind="line", path=first.path, line=first.line)
        body = (
            "This is a placeholder finding, anchored to the first line the diff adds: "
            f"`{first.path}` line {first.line}."
        )
    else:
        anchor = PullRequestAnchor(kind="pull_request")
        body = "This is a placeholder finding. The diff adds no lines to anchor it to."
    return Review(
        summary=summary,
        findings=[Finding(body=body, anchor=anchor)],
        everything_already_said=False,
    )


def review() -> None:
    """Review the checked-out change and post the result."""
    # Popped rather than read, so no later code that assembles a child environment out of
    # `os.environ` can pick the token up by accident.
    github = GitHub(token=os.environ.pop("GITHUB_TOKEN"))

    pull_request = json.loads(runner.pull_request_path().read_text())
    owner = pull_request["base"]["repo"]["owner"]["login"]
    repo = pull_request["base"]["repo"]["name"]
    number = pull_request["number"]
    head = pull_request["head"]["sha"]
    base = pull_request["base"]["sha"]

    workspace = runner.workspace()
    added = added_lines(workspace, merge_base(workspace, base, head), head)
    log.info("The change adds %d lines.", len(added))

    post_review(github, owner, repo, number, head, produce_review(added))
