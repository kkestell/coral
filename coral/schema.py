"""The review object the agent returns, and the rule that its absence is a failure.

This module is the contract between the agent and everything else. It imports nothing from
Coral and nothing from the agent framework: the dataclasses below are handed to the framework
as `response_format`, which validates the model's JSON straight into them, so the type the
model fills is the type the posting code reads.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field


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


Anchor = SpanAnchor | LineAnchor | FileAnchor | PullRequestAnchor


@dataclass(frozen=True)
class Finding:
    """One thing worth saying about the change, and the place it concerns."""

    body: Annotated[str, Field(description="The finding, written for the author of the change.")]
    anchor: Anchor


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


# LangChain sets `structured_response` to None when the model answers with prose, and the key is
# optional, so an absent key and a None both mean the same thing: no review came back.
def review_from_result(result: Mapping[str, object]) -> Review:
    """Read the review out of the agent's result state, or fail."""
    review = result.get("structured_response")
    if review is None:
        raise RuntimeError(
            "The agent returned no structured review. Coral does not recover a review from prose."
        )
    assert isinstance(review, Review), f"structured_response held a {type(review).__name__}"
    return review
