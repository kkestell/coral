"""The two reaction namespaces.

A comment on the pull request as a whole is an issue comment and reacts through the issues
namespace; a comment on the diff reacts through the pulls namespace. Neither permission grants
the other, which is why the workflow asks for both.
"""

from coral.github.client import GitHub
from coral.runner import Event


def react(github: GitHub, event: Event) -> None:
    """Acknowledge the comment that triggered this run."""
    # Posting a reaction that is already there returns 200 rather than creating a second one, so
    # nothing here reads first.
    if event.comment is None:
        return
    match event.comment.namespace:
        case "issues":
            path = f"/repos/{event.owner}/{event.repo}/issues/comments/{event.comment.id}/reactions"
        case "pulls":
            path = f"/repos/{event.owner}/{event.repo}/pulls/comments/{event.comment.id}/reactions"
    github.post(path, {"content": "eyes"})
