"""Creating the review, and the plain comment Coral posts when there is no review to make.

A whole-file finding and a pull-request-level finding go into the body by construction rather
than by failure. The `comments` array on the create-review endpoint accepts seven fields and
`subject_type` is not one of them, so there is nowhere for a file-level comment to go in a
batched review, and posting one would mean a second call per finding.
"""

from typing import Any

from coral.github.client import GitHub
from coral.github.marker import marker
from coral.schema import FileAnchor, LineAnchor, PullRequestAnchor, Review, SpanAnchor


def signed(commit: str, body: str) -> str:
    """A comment body opening with the marker.

    Every comment Coral posts carries one, not only the review body. Coral posts as the
    repository's automation, so the author login belongs to every other bot in the repository as
    well and cannot tell Coral's comments from anything else that account writes. The marker on
    the comment can, wherever the comment sits.
    """
    return f"{marker(commit)}\n\n{body}"


def post_comment(github: GitHub, owner: str, repo: str, number: int, commit: str, body: str) -> Any:
    """Post one comment on the pull request as a whole.

    What Coral has to say when there is no review to post: the change is larger than Coral will
    read, or the run failed. It carries the marker so a later run recognizes it as Coral's, and
    it does not enter the record of reviewed commits, which is read from review bodies alone.
    """
    return github.post(
        f"/repos/{owner}/{repo}/issues/{number}/comments", {"body": signed(commit, body)}
    )


def post_review(
    github: GitHub, owner: str, repo: str, number: int, commit: str, review: Review
) -> Any:
    """Post the whole review as one comment-event review naming the commit it reviewed."""
    comments: list[dict[str, Any]] = []
    demoted: list[str] = []

    for finding in review.findings:
        match finding.anchor:
            case SpanAnchor(path=path, start_line=start_line, end_line=end_line):
                comments.append(
                    {
                        "path": path,
                        "start_line": start_line,
                        "line": end_line,
                        "side": "RIGHT",
                        "body": signed(commit, finding.body),
                    }
                )
            case LineAnchor(path=path, line=line):
                comments.append(
                    {
                        "path": path,
                        "line": line,
                        "side": "RIGHT",
                        "body": signed(commit, finding.body),
                    }
                )
            case FileAnchor(path=path):
                demoted.append(f"**`{path}`** — {finding.body}")
            case PullRequestAnchor():
                demoted.append(finding.body)

    lines = [
        marker(commit),
        "",
        f"Coral reviewed `{commit}`.",
        "",
        review.summary,
    ]
    if demoted:
        lines += ["", *(f"- {entry}" for entry in demoted)]

    return github.post(
        f"/repos/{owner}/{repo}/pulls/{number}/reviews",
        {
            "commit_id": commit,
            "body": "\n".join(lines),
            "comments": comments,
            # Named explicitly: omitting it creates a review in the pending state that nobody
            # but its author can read.
            "event": "COMMENT",
        },
    )
