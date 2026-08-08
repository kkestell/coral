"""Which comments are owed the reaction, and the two namespaces it goes through.

A comment on the pull request as a whole is an issue comment and reacts through the issues
namespace; a comment on the diff reacts through the pulls namespace. Neither permission grants
the other, which is why the workflow asks for both.

A review is neither, and is never owed a reaction: GitHub has no endpoint for reacting to one,
which is also why the body of a submitted review is not a place to ask.
"""

import logging
from dataclasses import dataclass
from typing import Literal

from coral.command import Access, is_request
from coral.github.client import ApiError, GitHub
from coral.github.conversation import EYES, Comment, Conversation

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Request:
    """A comment asking for a review, and the namespace its reaction endpoint lives in."""

    id: int
    namespace: Literal["issues", "pulls"]


def owed(comment: Comment, access: Access) -> bool:
    """Whether a comment is a request that nobody has acknowledged yet."""
    return not comment.reacted and is_request(comment.body, comment.author, access)


def requests_in(conversation: Conversation, access: Access) -> list[Request]:
    """Every request the conversation offers that does not already carry Coral's reaction.

    Not only the request that started this run. The concurrency group cancels a pending run, so
    a request whose own run never started is waiting on this one.
    """
    return [
        *(
            Request(id=comment.database_id, namespace="issues")
            for comment in conversation.comments
            if owed(comment, access)
        ),
        *(
            Request(id=comment.database_id, namespace="pulls")
            for thread in conversation.threads
            for comment in thread.comments
            if owed(comment, access)
        ),
    ]


def react(github: GitHub, owner: str, repo: str, requests: list[Request]) -> None:
    """Acknowledge each request, one call each, and go on when one of them will not take it.

    A failed reaction is logged and costs nothing else. A comment deleted between the fetch and
    the reaction answers 404, and a locked conversation answers 403, and neither is a reason to
    fail a review that had nothing wrong with it and report on the pull request that Coral could
    not read the change. Every status is swallowed alike: the only thing a reaction failure can
    tell Coral is that this comment did not get its acknowledgment.
    """
    for request in requests:
        match request.namespace:
            case "issues":
                path = f"/repos/{owner}/{repo}/issues/comments/{request.id}/reactions"
            case "pulls":
                path = f"/repos/{owner}/{repo}/pulls/comments/{request.id}/reactions"
        try:
            # The REST endpoint takes the reaction name in lower case. Posting one that is already
            # there returns 200 and creates nothing, so nothing here reads first.
            github.post(path, {"content": EYES.lower()})
        except ApiError as error:
            log.warning("Could not acknowledge comment %d: %s", request.id, error)
