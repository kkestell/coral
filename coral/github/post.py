"""Creating the review, and the plain comment Coral posts when there is no review to make.

A whole-file finding and a pull-request-level finding go into the body by construction rather
than by failure. The `comments` array on the create-review endpoint accepts seven fields and
`subject_type` is not one of them, so there is nowhere for a file-level comment to go in a
batched review, and posting one would mean a second call per finding.
"""

from typing import Any

from coral.github.client import GitHub
from coral.github.marker import marker
from coral.schema import FileAnchor, Finding, LineAnchor, PullRequestAnchor, Review, SpanAnchor


def rendered_finding(finding: Finding) -> str:
    """A finding as Coral posts it, wherever it lands: the severity, the prose, and the evidence.

    Composed here rather than by the model, which returns the three pieces separately. Everything
    below is the same for an anchored comment and for one demoted into the summary.
    """
    parts = [f"**{finding.severity.capitalize()} severity.**"]
    if finding.regression_test is None:
        parts.append("*Speculative — not reproduced by a test.*")
    parts.append(finding.body)
    if finding.regression_test is not None:
        test = finding.regression_test
        parts.append(
            "<details>\n"
            f"<summary>Regression test — <code>{test.path}</code></summary>\n\n"
            f"Run with `{test.command}`:\n\n"
            f"```\n{test.content}\n```\n"
            "</details>"
        )
    return "\n\n".join(parts)


def bullet(entry: str) -> str:
    """One demoted finding as a list item, its later lines indented to stay inside it."""
    lines = entry.splitlines()
    return "\n".join(
        [f"- {lines[0]}"] + [f"  {line}" if line else "" for line in lines[1:]],
    )


def count(many: int, thing: str) -> str:
    """A count and the thing it counts, pluralized. Every prose Coral posts reads through this."""
    return f"{many} {thing}" if many == 1 else f"{many} {thing}s"


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
        rendered = rendered_finding(finding)
        match finding.anchor:
            case SpanAnchor(path=path, start_line=start_line, end_line=end_line):
                comments.append(
                    {
                        "path": path,
                        "start_line": start_line,
                        "line": end_line,
                        "side": "RIGHT",
                        "body": signed(commit, rendered),
                    }
                )
            case LineAnchor(path=path, line=line):
                comments.append(
                    {
                        "path": path,
                        "line": line,
                        "side": "RIGHT",
                        "body": signed(commit, rendered),
                    }
                )
            case FileAnchor(path=path):
                demoted.append(f"**`{path}`** — {rendered}")
            case PullRequestAnchor():
                demoted.append(rendered)

    lines = [
        marker(commit),
        "",
        f"Coral reviewed `{commit}`.",
        "",
        review.summary,
    ]
    if demoted:
        lines += ["", *(bullet(entry) for entry in demoted)]

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
