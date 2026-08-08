"""The objects the two agent runs return, and the filter that turns them into what gets posted.

This module is the contract between the agent and everything else. It imports nothing from
Coral and nothing from the agent framework: the dataclasses below are handed to the framework
as `response_format`, which validates the model's JSON straight into them, so the type the
model fills is the type the posting code reads.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Annotated, Literal

from pydantic import Field, StrictInt


@dataclass(frozen=True)
class SpanAnchor:
    """A range of lines in one file."""

    kind: Literal["span"]
    path: str
    start_line: Annotated[int, Field(description="First line of the span, 1-based, inclusive.")]
    end_line: Annotated[int, Field(description="Last line of the span, 1-based, inclusive.")]


@dataclass(frozen=True)
class LineAnchor:
    """A single line in one file."""

    kind: Literal["line"]
    path: str
    line: Annotated[int, Field(description="The line this finding is about, 1-based.")]


@dataclass(frozen=True)
class FileAnchor:
    """A whole file."""

    kind: Literal["file"]
    path: str


@dataclass(frozen=True)
class PullRequestAnchor:
    """The pull request as a whole, rather than any one file."""

    kind: Literal["pull_request"]


# A plain union with no Pydantic discriminator on it. The `kind` literals discriminate without
# one, and adding one emits `oneOf` where a strict provider-side validator takes only `anyOf`.
# `tests/test_schema.py` pins the generated schema against that.
Anchor = SpanAnchor | LineAnchor | FileAnchor | PullRequestAnchor


def where(anchor: Anchor) -> str:
    """The place a finding concerns, as prose.

    Read by the verifier's request and by the label on a finding demoted into the summary. It
    lives here because this module is the one both readers already depend on.
    """
    match anchor:
        case SpanAnchor(path=path, start_line=start_line, end_line=end_line):
            return f"`{path}`, lines {start_line} to {end_line}"
        case LineAnchor(path=path, line=line):
            return f"`{path}`, line {line}"
        case FileAnchor(path=path):
            return f"`{path}`, the whole file"
        case PullRequestAnchor():
            return "the pull request as a whole"


@dataclass(frozen=True)
class RegressionTest:
    """A test that demonstrates a finding: fails at the head commit, passes once it is fixed."""

    path: Annotated[str, Field(description="Where to write it in the checkout, relative.")]
    content: Annotated[str, Field(description="The whole file, as it should be written.")]
    command: Annotated[
        str,
        Field(description="Runs exactly this test, and is expected to fail at the head commit."),
    ]


@dataclass(frozen=True)
class Finding:
    """One thing worth saying about the change, and the place it concerns."""

    body: Annotated[str, Field(description="The finding, written for the author of the change.")]
    anchor: Anchor
    severity: Annotated[
        Literal["low", "medium", "high"],
        Field(description="How much damage this does if the change merges as it stands."),
    ]
    # No default, so an absent key is a validation failure rather than a silent `None`: a
    # speculative finding is a null the model wrote, never a field it forgot.
    regression_test: Annotated[
        RegressionTest | None,
        Field(
            description=(
                "The test you wrote and ran that fails because of this finding, or null when no "
                "test can show it. A finding with null here is speculative."
            )
        ),
    ]


@dataclass(frozen=True)
class Review:
    """A review of a pull request: an overall summary and the findings it is made of."""

    summary: str
    findings: list[Finding]
    everything_already_said: Annotated[
        bool,
        Field(
            description=(
                "Read only when findings is empty. True means everything you would say about "
                "this change is already on this pull request and still stands. False means "
                "there was nothing to find."
            )
        ),
    ]


@dataclass(frozen=True)
class Verdict:
    """What the second agent run decided about one of the first run's findings."""

    finding: Annotated[
        int, Field(description="The number of the finding this rules on, as the request gave it.")
    ]
    confirmed: Annotated[
        bool, Field(description="True only if you established the finding yourself.")
    ]
    reason: Annotated[
        str, Field(description="A sentence or two on what you did and what it showed.")
    ]
    duplicate_issue: Annotated[
        StrictInt | None,
        Field(
            ge=1,
            description=(
                "The open issue you viewed that describes this confirmed finding, or null when "
                "none does."
            ),
        ),
    ]


@dataclass(frozen=True)
class Verification:
    """A ruling on every finding in a review."""

    verdicts: list[Verdict]


def confirmed(
    review: Review,
    verification: Verification,
    searched_findings: set[int] | None = None,
    viewed_issues: set[int] | None = None,
) -> Review:
    """The review that survives confirmation and, for main pushes, duplicate checks.

    A finding no verdict names is dropped. The verifier is told to rule on every finding, so
    silence about one is a run that went wrong rather than an endorsement. Main-push evidence is
    supplied together or not at all: without a search a finding cannot be published, and only a
    common issue number the reader viewed can suppress a confirmed finding.
    """
    assert (searched_findings is None) == (viewed_issues is None)
    kept = []
    for index, finding in enumerate(review.findings):
        verdicts = [verdict for verdict in verification.verdicts if verdict.finding == index]
        duplicates = {verdict.duplicate_issue for verdict in verdicts}
        duplicate = duplicates.pop() if len(duplicates) == 1 else None
        code_confirmed = verdicts and all(verdict.confirmed for verdict in verdicts)
        checked = searched_findings is None or index in searched_findings
        matched = duplicate is not None and viewed_issues is not None and duplicate in viewed_issues
        if code_confirmed and checked and not matched:
            kept.append(finding)
    return replace(review, findings=kept)


# LangChain sets `structured_response` to None when the model answers with prose, and the key is
# optional, so an absent key and a None both mean the same thing: nothing came back.
def review_from_result(result: Mapping[str, object]) -> Review:
    """Read the review out of the agent's result state, or fail."""
    review = result.get("structured_response")
    if review is None:
        raise RuntimeError(
            "The agent returned no structured review. Coral does not recover a review from prose."
        )
    assert isinstance(review, Review), f"structured_response held a {type(review).__name__}"
    return review


def verification_from_result(result: Mapping[str, object]) -> Verification:
    """Read the verdicts out of the agent's result state, or fail."""
    verification = result.get("structured_response")
    if verification is None:
        raise RuntimeError(
            "The agent returned no structured verification. Coral does not recover verdicts "
            "from prose."
        )
    assert isinstance(verification, Verification), (
        f"structured_response held a {type(verification).__name__}"
    )
    return verification
