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
    RegressionTest,
    Review,
    ScopeAnchor,
    SpanAnchor,
    Verdict,
    Verification,
    apply_dispositions,
    finding_dispositions,
    review_from_result,
    verification_from_result,
    where,
)

NO_REVIEW = "The agent returned no structured review. Coral does not recover a review from prose."
NO_VERIFICATION = (
    "The agent returned no structured verification. Coral does not recover verdicts from prose."
)

REVIEWS = TypeAdapter(Review)
VERIFICATIONS = TypeAdapter(Verification)


def finding_payload(anchor: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    return {
        "body": "Something worth saying.",
        "anchor": anchor,
        "severity": "medium",
        "regression_test": None,
        **overrides,
    }


def review_payload(*anchors: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": "One paragraph of summary.",
        "findings": [finding_payload(anchor) for anchor in anchors],
    }


def anchor_from(payload: dict[str, Any]) -> Anchor:
    return REVIEWS.validate_python(review_payload(payload)).findings[0].anchor


def finding(body: str = "Something worth saying.") -> Finding:
    return Finding(
        body=body,
        anchor=ScopeAnchor(kind="scope"),
        severity="low",
        regression_test=None,
    )


def review_of(*findings: Finding) -> Review:
    return Review(summary="One paragraph.", findings=list(findings))


def test_span_anchor_validates() -> None:
    anchor = anchor_from({"kind": "span", "path": "a.py", "start_line": 1, "end_line": 3})
    assert anchor == SpanAnchor(kind="span", path="a.py", start_line=1, end_line=3)


def test_line_anchor_validates() -> None:
    anchor = anchor_from({"kind": "line", "path": "a.py", "line": 7})
    assert anchor == LineAnchor(kind="line", path="a.py", line=7)


def test_file_anchor_validates() -> None:
    anchor = anchor_from({"kind": "file", "path": "a.py"})
    assert anchor == FileAnchor(kind="file", path="a.py")


def test_scope_anchor_validates() -> None:
    assert anchor_from({"kind": "scope"}) == ScopeAnchor(kind="scope")


def test_findings_and_anchors_survive_together() -> None:
    review = REVIEWS.validate_python(
        review_payload(
            {"kind": "line", "path": "a.py", "line": 7},
            {"kind": "scope"},
        )
    )
    assert review.findings == [
        Finding(
            body="Something worth saying.",
            anchor=LineAnchor(kind="line", path="a.py", line=7),
            severity="medium",
            regression_test=None,
        ),
        Finding(
            body="Something worth saying.",
            anchor=ScopeAnchor(kind="scope"),
            severity="medium",
            regression_test=None,
        ),
    ]


def test_empty_review_says_nothing_was_found() -> None:
    review = REVIEWS.validate_python({"summary": "Nothing to report.", "findings": []})
    assert review.findings == []


def test_review_from_result_returns_the_review() -> None:
    review = Review(summary="Fine.", findings=[])
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
    assert "oneOf" not in json.dumps(VERIFICATIONS.json_schema())
    assert schema["$defs"]["Finding"]["properties"]["anchor"]["anyOf"] == [
        {"$ref": "#/$defs/SpanAnchor"},
        {"$ref": "#/$defs/LineAnchor"},
        {"$ref": "#/$defs/FileAnchor"},
        {"$ref": "#/$defs/ScopeAnchor"},
    ]


def test_each_severity_validates() -> None:
    for severity in ("low", "medium", "high"):
        payload = review_payload({"kind": "file", "path": "a.py"})
        payload["findings"][0]["severity"] = severity
        assert REVIEWS.validate_python(payload).findings[0].severity == severity


def test_a_fourth_severity_is_rejected() -> None:
    # The calibration in the prompt has three rungs and the schema is what holds the model to
    # them. A "critical" or a "nit" would otherwise arrive and mean whatever the model meant.
    payload = review_payload({"kind": "file", "path": "a.py"})
    payload["findings"][0]["severity"] = "critical"
    with pytest.raises(ValidationError):
        REVIEWS.validate_python(payload)


def test_an_absent_regression_test_is_rejected() -> None:
    # The field has no default, so a speculative finding is a null the model wrote rather than a
    # key it left out. Otherwise laziness and honesty are indistinguishable.
    payload = review_payload({"kind": "file", "path": "a.py"})
    del payload["findings"][0]["regression_test"]
    with pytest.raises(ValidationError):
        REVIEWS.validate_python(payload)


def test_an_explicit_null_regression_test_validates() -> None:
    validated = REVIEWS.validate_python(review_payload({"kind": "file", "path": "a.py"}))
    assert validated.findings[0].regression_test is None


def test_a_regression_test_validates_whole() -> None:
    payload = review_payload({"kind": "file", "path": "a.py"})
    payload["findings"][0]["regression_test"] = {
        "path": "tests/test_parser.py",
        "content": "def test_it() -> None:\n    assert False\n",
        "command": "pytest tests/test_parser.py::test_it",
    }
    assert REVIEWS.validate_python(payload).findings[0].regression_test == RegressionTest(
        path="tests/test_parser.py",
        content="def test_it() -> None:\n    assert False\n",
        command="pytest tests/test_parser.py::test_it",
    )


def test_each_anchor_names_its_place() -> None:
    # Read twice over: by the verifier's request and by a demoted finding's label.
    assert where(SpanAnchor(kind="span", path="a.py", start_line=3, end_line=9)) == (
        "`a.py`, lines 3 to 9"
    )
    assert where(LineAnchor(kind="line", path="a.py", line=7)) == "`a.py`, line 7"
    assert where(FileAnchor(kind="file", path="a.py")) == "`a.py`, the whole file"
    assert where(ScopeAnchor(kind="scope")) == "the reviewed scope as a whole"


def test_a_verification_validates() -> None:
    verification = VERIFICATIONS.validate_python(
        {
            "verdicts": [
                {
                    "finding": 0,
                    "confirmed": True,
                    "reason": "The test failed as claimed.",
                }
            ],
            "summary": "The final summary.",
        }
    )
    assert verification.verdicts == [
        Verdict(
            finding=0,
            confirmed=True,
            reason="The test failed as claimed.",
        )
    ]
    assert verification.summary == "The final summary."


def test_a_confirmed_finding_survives() -> None:
    kept = finding()
    review = review_of(kept)
    verification = Verification(verdicts=[Verdict(finding=0, confirmed=True, reason="Ran.")])
    survivors = apply_dispositions(review, finding_dispositions(review, verification))
    assert survivors.findings == [kept]


def test_a_rejected_finding_is_dropped() -> None:
    review = review_of(finding())
    verification = Verification(verdicts=[Verdict(finding=0, confirmed=False, reason="Passed.")])
    survivors = apply_dispositions(review, finding_dispositions(review, verification))
    assert survivors.findings == []


def test_a_finding_no_verdict_names_is_dropped() -> None:
    # Silence is not confirmation: the verifier is told to rule on every finding, so a finding it
    # skipped is a run that went wrong rather than a finding that stands.
    review = review_of(finding("First."), finding("Second."))
    verification = Verification(verdicts=[Verdict(finding=0, confirmed=True, reason="Ran.")])
    survivors = apply_dispositions(review, finding_dispositions(review, verification))
    assert [kept.body for kept in survivors.findings] == ["First."]


def test_a_verdict_naming_no_finding_is_ignored() -> None:
    review = review_of(finding())
    verification = Verification(
        verdicts=[
            Verdict(finding=0, confirmed=True, reason="Ran."),
            Verdict(finding=9, confirmed=False, reason="About nothing."),
        ]
    )
    survivors = apply_dispositions(review, finding_dispositions(review, verification))
    assert len(survivors.findings) == 1


def test_conflicting_verdicts_drop_the_finding() -> None:
    review = review_of(finding())
    verification = Verification(
        verdicts=[
            Verdict(finding=0, confirmed=True, reason="Ran."),
            Verdict(
                finding=0,
                confirmed=False,
                reason="On reflection, no.",
            ),
        ]
    )
    survivors = apply_dispositions(review, finding_dispositions(review, verification))
    assert survivors.findings == []


def test_no_verdicts_at_all_drops_every_finding() -> None:
    review = review_of(finding(), finding())
    verification = Verification(verdicts=[])
    survivors = apply_dispositions(review, finding_dispositions(review, verification))
    assert survivors.findings == []


def test_the_summary_passes_through_the_filter() -> None:
    review = Review(summary="What the scope does.", findings=[])
    survivors = apply_dispositions(review, finding_dispositions(review, Verification(verdicts=[])))
    assert survivors.summary == "What the scope does."


@pytest.mark.parametrize(
    ("ruling", "reason"),
    [(None, "no verdict"), (False, "rejected"), (True, "confirmed")],
)
def test_each_finding_disposition_names_the_filtering_decision(
    ruling: bool | None,
    reason: str,
) -> None:
    verdicts = (
        []
        if ruling is None
        else [
            Verdict(
                finding=0,
                confirmed=ruling,
                reason="Checked.",
            )
        ]
    )
    disposition = finding_dispositions(review_of(finding()), Verification(verdicts))[0]
    assert disposition.reason == reason
    assert disposition.kept is (reason == "confirmed")
    assert disposition.verdicts == tuple(verdicts)


def test_verification_from_result_returns_the_verification() -> None:
    verification = Verification(verdicts=[])
    assert verification_from_result({"structured_response": verification}) is verification


def test_verification_from_result_rejects_a_none() -> None:
    with pytest.raises(RuntimeError) as raised:
        verification_from_result({"structured_response": None, "messages": []})
    assert str(raised.value) == NO_VERIFICATION
