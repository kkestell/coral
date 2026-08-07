"""Which comments are owed the reaction, and the two namespaces it goes through.

A comment on the pull request as a whole is an issue comment and reacts through the issues
namespace; a comment on the diff reacts through the pulls namespace. Neither permission grants
the other, which is why the workflow asks for both.

A review is neither, and is never owed a reaction: GitHub has no endpoint for reacting to one,
which is also why the body of a submitted review is not a place to ask.
"""

from dataclasses import dataclass
from typing import Literal

from coral.command import is_request
from coral.github.client import GitHub
from coral.github.conversation import EYES, Comment, Conversation


@dataclass(frozen=True)
class Request:
    """A comment asking for a review, and the namespace its reaction endpoint lives in."""

    id: int
    namespace: Literal["issues", "pulls"]


def owed(comment: Comment) -> bool:
    """Whether a comment is a request that nobody has acknowledged yet."""
    return not comment.reacted and is_request(comment.body, comment.association)


def requests_in(conversation: Conversation) -> list[Request]:
    """Every request the conversation offers that does not already carry Coral's reaction.

    Not only the request that started this run. The concurrency group cancels a pending run, so
    a request whose own run never started is waiting on this one.
    """
    return [
        *(
            Request(id=comment.database_id, namespace="issues")
            for comment in conversation.comments
            if owed(comment)
        ),
        *(
            Request(id=comment.database_id, namespace="pulls")
            for thread in conversation.threads
            for comment in thread.comments
            if owed(comment)
        ),
    ]


def react(github: GitHub, owner: str, repo: str, requests: list[Request]) -> None:
    """Acknowledge each request, one call each."""
    for request in requests:
        match request.namespace:
            case "issues":
                path = f"/repos/{owner}/{repo}/issues/comments/{request.id}/reactions"
            case "pulls":
                path = f"/repos/{owner}/{repo}/pulls/comments/{request.id}/reactions"
        # The REST endpoint takes the reaction name in lower case. Posting one that is already
        # there returns 200 and creates nothing, so nothing here reads first.
        github.post(path, {"content": EYES.lower()})
