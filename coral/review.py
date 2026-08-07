"""The review step: compute the diff, produce the review, post it."""

import json
import logging
import os

from coral import runner
from coral.diff import AddedLine, added_lines, merge_base
from coral.github.client import GitHub
from coral.github.conversation import Comment, Conversation, read_conversation
from coral.github.post import post_review
from coral.schema import Anchor, Finding, LineAnchor, PullRequestAnchor, Review

log = logging.getLogger(__name__)


def whose(comment: Comment) -> str:
    """Who wrote a comment, as the review reports it."""
    if comment.mine:
        return "Coral"
    return f"{comment.author or 'a deleted account'} ({comment.association})"


def count(many: int, thing: str) -> str:
    """A count and the thing it counts, pluralized."""
    return f"{many} {thing}" if many == 1 else f"{many} {thing}s"


def what_was_read(conversation: Conversation) -> str:
    """What the conversation held, reported so a live run leaves its evidence on the pull request.

    This is a placeholder for the agent's own summary, and nothing here reads the conversation
    for its meaning. It exists because otherwise a fetch that worked and a fetch that returned
    nothing would look the same from the pull request.
    """
    lines = [
        f"Coral read {count(conversation.bound.read, 'comment')} and left "
        f"{conversation.bound.unread} unread: {count(len(conversation.comments), 'comment')} on "
        f"the pull request, {count(len(conversation.reviews), 'review')}, and "
        f"{count(len(conversation.threads), 'thread')}.",
        "",
        (
            "Commits Coral has already reviewed: "
            + ", ".join(f"`{commit}`" for commit in conversation.reviewed_commits)
            if conversation.reviewed_commits
            else "Coral has not reviewed this pull request before."
        ),
    ]
    for comment in [*conversation.comments, *conversation.reviews]:
        lines.append(f"- {whose(comment)} wrote {count(len(comment.body), 'character')}.")
    for thread in conversation.threads:
        state = "resolved" if thread.resolved else "unresolved"
        staleness = "outdated" if thread.outdated else "current"
        authors = ", ".join(whose(comment) for comment in thread.comments)
        lines.append(
            f"- Thread on `{thread.path}` line {thread.line}, {state} and {staleness}, holding "
            f"{count(thread.total_comments, 'comment')} from {authors}."
        )
    return "\n".join(lines)


def produce_review(added: list[AddedLine], conversation: Conversation) -> Review:
    """Where the agent goes. Until then, one hardcoded finding on a line out of the diff."""
    summary = (
        "Coral ran end to end and made no model call. This review is hardcoded and says nothing "
        "about the change.\n\n" + what_was_read(conversation)
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

    conversation = read_conversation(runner.conversation_path())

    workspace = runner.workspace()
    added = added_lines(workspace, merge_base(workspace, base, head), head)
    log.info("The change adds %d lines.", len(added))

    post_review(github, owner, repo, number, head, produce_review(added, conversation))
