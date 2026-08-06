"""Tests of the contract in `coral.schema`.

Validation goes through `pydantic.TypeAdapter`, which is the validator LangChain itself uses on
this type, and every anchor is validated inside a whole `Review` payload because that is the
shape the model actually fills. What these tests pin is the contract, not Pydantic's behavior.
"""

import json
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from coral.schema import (
    Anchor,
    FileAnchor,
    Finding,
    LineAnchor,
    PullRequestAnchor,
    Review,
    SpanAnchor,
    review_from_result,
)

NO_REVIEW = "The agent returned no structured review. Coral does not recover a review from prose."

REVIEWS = TypeAdapter(Review)


def review_payload(*anchors: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": "One paragraph of summary.",
        "findings": [{"body": "Something worth saying.", "anchor": a} for a in anchors],
        "everything_already_said": False,
    }


def anchor_from(payload: dict[str, Any]) -> Anchor:
    return REVIEWS.validate_python(review_payload(payload)).findings[0].anchor


def test_span_anchor_validates() -> None:
    anchor = anchor_from({"kind": "span", "path": "a.py", "start_line": 1, "end_line": 3})
    assert anchor == SpanAnchor(kind="span", path="a.py", start_line=1, end_line=3)


def test_line_anchor_validates() -> None:
    anchor = anchor_from({"kind": "line", "path": "a.py", "line": 7})
    assert anchor == LineAnchor(kind="line", path="a.py", line=7)


def test_file_anchor_validates() -> None:
    anchor = anchor_from({"kind": "file", "path": "a.py"})
    assert anchor == FileAnchor(kind="file", path="a.py")


def test_pull_request_anchor_validates() -> None:
    assert anchor_from({"kind": "pull_request"}) == PullRequestAnchor(kind="pull_request")


def test_findings_and_anchors_survive_together() -> None:
    review = REVIEWS.validate_python(
        review_payload(
            {"kind": "line", "path": "a.py", "line": 7},
            {"kind": "pull_request"},
        )
    )
    assert review.findings == [
        Finding(
            body="Something worth saying.", anchor=LineAnchor(kind="line", path="a.py", line=7)
        ),
        Finding(body="Something worth saying.", anchor=PullRequestAnchor(kind="pull_request")),
    ]


def test_empty_review_says_nothing_was_found() -> None:
    review = REVIEWS.validate_python(
        {"summary": "Nothing to report.", "findings": [], "everything_already_said": False}
    )
    assert review.findings == []
    assert review.everything_already_said is False


def test_empty_review_says_everything_is_already_said() -> None:
    review = REVIEWS.validate_python(
        {"summary": "Already said.", "findings": [], "everything_already_said": True}
    )
    assert review.findings == []
    assert review.everything_already_said is True


def test_review_from_result_returns_the_review() -> None:
    review = Review(summary="Fine.", findings=[], everything_already_said=False)
    assert review_from_result({"structured_response": review, "messages": []}) is review


def test_review_from_result_rejects_a_missing_key() -> None:
    with pytest.raises(RuntimeError) as raised:
        review_from_result({"messages": []})
    assert str(raised.value) == NO_REVIEW


def test_review_from_result_rejects_a_none() -> None:
    with pytest.raises(RuntimeError) as raised:
        review_from_result({"structured_response": None, "messages": []})
    assert str(raised.value) == NO_REVIEW


def test_a_half_filled_span_is_not_quietly_another_anchor() -> None:
    # The union is plain rather than discriminated, so this is the case that proves a span
    # missing its line numbers is rejected instead of validating as a line or a file anchor.
    with pytest.raises(ValidationError):
        anchor_from({"kind": "span", "path": "a.py", "line": 3})


def test_an_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        anchor_from({"kind": "paragraph", "path": "a.py", "line": 3})


def test_a_stray_field_is_dropped_rather_than_refused() -> None:
    # Recorded rather than desired: the posting code cannot assume an anchor rejected everything
    # it did not ask for, and tightening this later is a deliberate change.
    assert anchor_from({"kind": "file", "path": "a.py", "line": 3}) == FileAnchor(
        kind="file", path="a.py"
    )


def test_the_json_schema_uses_anyof_and_never_oneof() -> None:
    # `anyOf` with `$ref`s is the form a strict provider-side validator accepts. A Pydantic
    # discriminator on the anchor union would silently turn this into `oneOf`.
    schema = REVIEWS.json_schema()
    assert "oneOf" not in json.dumps(schema)
    assert schema["$defs"]["Finding"]["properties"]["anchor"]["anyOf"] == [
        {"$ref": "#/$defs/SpanAnchor"},
        {"$ref": "#/$defs/LineAnchor"},
        {"$ref": "#/$defs/FileAnchor"},
        {"$ref": "#/$defs/PullRequestAnchor"},
    ]
