"""Creating the review, and the plain comment Coral posts when there is no review to make.

A whole-file finding and a pull-request-level finding go into the body by construction rather
than by failure. The `comments` array on the create-review endpoint accepts seven fields and
`subject_type` is not one of them, so there is nowhere for a file-level comment to go in a
batched review, and posting one would mean a second call per finding.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from pydantic import TypeAdapter

from coral.diff import AddedLine, attachable
from coral.github.client import ApiError, GitHub
from coral.github.marker import marker
from coral.schema import Finding, LineAnchor, PullRequestAnchor, Review, SpanAnchor, where

log = logging.getLogger(__name__)


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


def signed(commit: str | None, body: str) -> str:
    """A comment body opening with the marker.

    Every comment Coral posts carries one, not only the review body. Coral posts as the
    repository's automation, so the author login belongs to every other bot in the repository as
    well and cannot tell Coral's comments from anything else that account writes. The marker on
    the comment can, wherever the comment sits.
    """
    return f"{marker(commit)}\n\n{body}"


def post_comment(
    github: GitHub, owner: str, repo: str, number: int, commit: str | None, body: str
) -> Any:
    """Post one comment on the pull request as a whole.

    What Coral has to say when there is no review to post: the change is larger than Coral will
    read, or the run failed. It carries the marker so a later run recognizes it as Coral's, and
    it does not enter the record of reviewed commits, which is read from review bodies alone.

    The commit is `None` when a run failed before anything pinned one.
    """
    return github.post(
        f"/repos/{owner}/{repo}/issues/{number}/comments", {"body": signed(commit, body)}
    )


def demotion(finding: Finding) -> str:
    """A finding that will not attach, naming the place it concerns."""
    match finding.anchor:
        case PullRequestAnchor():
            # No label: it concerns no place.
            return rendered_finding(finding)
        case _:
            return f"**{where(finding.anchor)}** — {rendered_finding(finding)}"


def nothing_to_report(review: Review) -> str:
    """Which of the two empty outcomes this is, in Coral's words rather than the model's.

    Coral writes the sentence rather than trusting the summary to make the distinction, because a
    second "nothing found" that reads as retracting the first review is what this prevents.
    """
    if review.everything_already_said:
        return "Everything Coral has to say about this change is already on this pull request."
    return "Coral found nothing to report on this change."


def cost(spent: float) -> str:
    """What the run spent, as the review reports it.

    Four decimal places rather than two: every review measured so far has cost a fraction of a
    cent, and cents would print `$0.00` on all of them.
    """
    return f"*This review cost ${spent:.4f}.*"


def review_payload(
    commit: str, review: Review, added: set[AddedLine], spent: float
) -> dict[str, Any]:
    """The create-review body: what attaches as a comment, and what the summary carries instead."""
    comments: list[dict[str, Any]] = []
    demoted: list[str] = []

    for finding in review.findings:
        match attachable(finding.anchor, added):
            case SpanAnchor(path=path, start_line=start_line, end_line=end_line):
                comments.append(
                    {
                        "path": path,
                        "start_line": start_line,
                        "line": end_line,
                        "side": "RIGHT",
                        "body": signed(commit, rendered_finding(finding)),
                    }
                )
            case LineAnchor(path=path, line=line):
                comments.append(
                    {
                        "path": path,
                        "line": line,
                        "side": "RIGHT",
                        "body": signed(commit, rendered_finding(finding)),
                    }
                )
            case None:
                demoted.append(demotion(finding))

    lines = [
        marker(commit),
        "",
        f"🪸 Coral reviewed `{commit}`.",
        "",
        review.summary,
    ]
    if demoted:
        # Neutral about the cause: a whole-file finding was never going to attach, and a line
        # finding that could not is not the reader's problem.
        lines += ["", "Findings not anchored to a line:", "", *(bullet(entry) for entry in demoted)]
    if not review.findings:
        lines += ["", nothing_to_report(review)]
    lines += ["", cost(spent)]

    # Neither `commit_id` nor `event` is here: both are stamped by `submitted` in the job that
    # posts, so neither is a field the job that composed this body gets a say in.
    return {
        "body": "\n".join(lines),
        "comments": comments,
    }


@dataclass(frozen=True)
class Payloads:
    """The two create-review bodies, one of which the publishing job posts."""

    anchored: dict[str, Any]
    demoted: dict[str, Any]


def payloads(commit: str, review: Review, added: set[AddedLine], spent: float) -> Payloads:
    """Both bodies: the one whose findings attach, and the one where every finding is demoted.

    Both are built here, where the diff is: each needs the added-line set the anchors were checked
    against, and that set exists only in the job holding the checkout. GitHub accepts or rejects a
    review whole, using its own patch generation, so the local check cannot be sufficient and the
    fallback travels with the body it replaces. Nothing attaches to an empty set, so the demoted
    body is the same composition rather than a second path through it.
    """
    return Payloads(
        anchored=review_payload(commit, review, added, spent),
        demoted=review_payload(commit, review, set(), spent),
    )


# The same validator the agent framework runs over the review object, so the project has one
# answer to "JSON back into a frozen dataclass" rather than two.
PAYLOADS: Final = TypeAdapter(Payloads)


def write_payloads(path: Path, payloads: Payloads) -> None:
    """Leave the two bodies where the publishing job will read them."""
    path.write_bytes(PAYLOADS.dump_json(payloads))


def read_payloads(path: Path) -> Payloads:
    """Read the two bodies back into the pair they were written from."""
    return PAYLOADS.validate_json(path.read_bytes())


def submitted(commit: str, payload: dict[str, Any]) -> dict[str, Any]:
    """A body as the publishing job posts it, carrying the two fields it does not take on trust.

    The body crossed a job boundary from the job the agent ran in. `event` is `COMMENT` because
    the review is advisory — anything else approves the change or blocks the merge, and omitting
    it creates a review in the pending state that nobody but its author can read. `commit_id` is
    the commit resolve pinned. Both override whatever the body brought.
    """
    return payload | {"commit_id": commit, "event": "COMMENT"}


def post_review(
    github: GitHub,
    owner: str,
    repo: str,
    number: int,
    commit: str,
    payloads: Payloads,
) -> Any:
    """Post the whole review as one comment-event review, demoting every finding if that is refused.

    The retry is unconditional in what it demotes: it does not read the 422 for which entry was
    bad, because a retry that depends on the body naming one fails silently on a body that does
    not. Confirmed on a real rejection: the body carries only
    `"errors":["Line could not be resolved"]`, naming no anchor.
    """
    path = f"/repos/{owner}/{repo}/pulls/{number}/reviews"
    try:
        return github.post(path, submitted(commit, payloads.anchored))
    except ApiError as rejection:
        if rejection.status != 422:
            raise
        log.warning("GitHub rejected the anchored review: %s", rejection.body)
        return github.post(path, submitted(commit, payloads.demoted))


def is_open(github: GitHub, owner: str, repo: str, number: int) -> bool:
    """Whether the pull request is still open, read at the last moment before posting."""
    return bool(github.get(f"/repos/{owner}/{repo}/pulls/{number}")["state"] == "open")
