"""Tests of `coral.github.post`.

Nothing here posts. What the module decides on its own is how a finding reads once Coral has
composed it out of the pieces the model returned separately, and where each finding lands, and
that is what these cover. The retry's control flow is not among them: recovering from a 422 needs
a `GitHub` that fails, and what makes the retry correct is that its payload is `review_payload`
against an empty set, which is tested below.
"""

from typing import Any

from coral.diff import AddedLine
from coral.github.marker import marker
from coral.github.post import (
    bullet,
    count,
    demotion,
    nothing_to_report,
    rendered_finding,
    review_payload,
    signed,
)
from coral.schema import (
    Anchor,
    FileAnchor,
    Finding,
    LineAnchor,
    PullRequestAnchor,
    RegressionTest,
    Review,
    SpanAnchor,
)

COMMIT = "a" * 40

ADDED = {
    AddedLine(path="a.py", line=7),
    AddedLine(path="a.py", line=12),
}

TEST = RegressionTest(
    path="tests/test_parser.py",
    content="def test_it() -> None:\n    assert parse('') == []\n",
    command="pytest tests/test_parser.py::test_it",
)


def finding(severity: str = "medium", regression_test: RegressionTest | None = None) -> Finding:
    return Finding(
        body="The parser drops the last token.",
        anchor=LineAnchor(kind="line", path="a.py", line=7),
        severity=severity,  # type: ignore[arg-type]
        regression_test=regression_test,
    )


def test_the_severity_leads_the_finding() -> None:
    for severity, label in (("low", "Low"), ("medium", "Medium"), ("high", "High")):
        assert rendered_finding(finding(severity)).startswith(f"**{label} severity.**")


def test_a_finding_with_no_test_is_marked_speculative() -> None:
    rendered = rendered_finding(finding())
    assert "*Speculative — not reproduced by a test.*" in rendered
    assert "<details>" not in rendered


def test_a_reproduced_finding_carries_its_test_collapsed() -> None:
    rendered = rendered_finding(finding(regression_test=TEST))
    assert "Speculative" not in rendered
    assert "<details>" in rendered
    assert "tests/test_parser.py" in rendered
    assert "pytest tests/test_parser.py::test_it" in rendered
    assert TEST.content in rendered


def test_the_body_is_always_there() -> None:
    assert "The parser drops the last token." in rendered_finding(finding())
    assert "The parser drops the last token." in rendered_finding(finding(regression_test=TEST))


def test_a_demoted_finding_stays_inside_its_list_item() -> None:
    # A finding demoted into the summary is a list item, and everything after its first line has
    # to be indented or the `<details>` block below it ends the list.
    item = bullet(rendered_finding(finding(regression_test=TEST)))
    assert item.startswith("- **Medium severity.**")
    assert "\n  <details>" in item
    assert "\n<details>" not in item


def test_a_blank_line_in_a_list_item_stays_blank() -> None:
    # Trailing whitespace on an otherwise empty line renders the same but reads as a diff hunk in
    # every later comparison.
    assert bullet("first\n\nsecond") == "- first\n\n  second"


def test_a_signed_body_opens_with_the_marker() -> None:
    assert signed(COMMIT, "prose").startswith(marker(COMMIT))


def test_a_signed_body_naming_no_commit_opens_with_the_bare_sentinel() -> None:
    # What `post_comment` sends when a run failed before anything pinned a commit.
    assert signed(None, "prose").startswith(marker(None))


def test_a_count_of_one_is_singular() -> None:
    assert count(1, "finding") == "1 finding"
    assert count(2, "finding") == "2 findings"


def finding_at(anchor: Anchor, body: str = "The parser drops the last token.") -> Finding:
    return Finding(body=body, anchor=anchor, severity="medium", regression_test=None)


def line(number: int) -> LineAnchor:
    return LineAnchor(kind="line", path="a.py", line=number)


def span(start: int, end: int) -> SpanAnchor:
    return SpanAnchor(kind="span", path="a.py", start_line=start, end_line=end)


def review_of(*findings: Finding, already_said: bool = False) -> Review:
    return Review(
        summary="What the change does.",
        findings=list(findings),
        everything_already_said=already_said,
    )


def payload_of(*findings: Finding) -> dict[str, Any]:
    return review_payload(COMMIT, review_of(*findings), ADDED)


def test_a_line_finding_becomes_one_anchored_comment() -> None:
    anchored = finding_at(line(7))
    assert payload_of(anchored)["comments"] == [
        {
            "path": "a.py",
            "line": 7,
            "side": "RIGHT",
            "body": signed(COMMIT, rendered_finding(anchored)),
        }
    ]


def test_a_span_finding_carries_both_of_its_ends() -> None:
    payload = payload_of(finding_at(span(7, 12)))
    comment = payload["comments"][0]
    assert comment["path"] == "a.py"
    assert comment["start_line"] == 7
    assert comment["line"] == 12
    assert comment["side"] == "RIGHT"


def test_the_review_names_the_commit_it_reviewed() -> None:
    payload = payload_of()
    assert payload["commit_id"] == COMMIT
    # Anything but COMMENT approves the change or blocks the merge.
    assert payload["event"] == "COMMENT"


def test_the_body_carries_the_marker_the_commit_and_the_summary() -> None:
    body = payload_of()["body"]
    assert body.startswith(marker(COMMIT))
    assert f"Coral reviewed `{COMMIT}`." in body
    assert "What the change does." in body


def test_an_unattachable_line_finding_names_its_file_and_its_line() -> None:
    body = payload_of(finding_at(line(99)))["body"]
    assert "Findings not anchored to a line:" in body
    assert "- **`a.py`, line 99** — **Medium severity.**" in body


def test_a_whole_file_finding_names_its_file() -> None:
    body = payload_of(finding_at(FileAnchor(kind="file", path="a.py")))["body"]
    assert "- **`a.py`, the whole file** — **Medium severity.**" in body


def test_a_pull_request_finding_is_demoted_with_no_place_prefix() -> None:
    # It concerns no place, so there is nothing to name.
    whole = finding_at(PullRequestAnchor(kind="pull_request"))
    assert demotion(whole) == rendered_finding(whole)


def test_a_demoted_finding_keeps_its_test_inside_its_list_item() -> None:
    reproduced = Finding(
        body="The parser drops the last token.",
        anchor=FileAnchor(kind="file", path="a.py"),
        severity="high",
        regression_test=TEST,
    )
    body = payload_of(reproduced)["body"]
    assert "\n  <details>" in body
    assert "\n<details>" not in body


def test_a_review_with_no_demotions_has_no_lead_in_line() -> None:
    body = payload_of(finding_at(line(7)))["body"]
    assert "Findings not anchored" not in body


def mixed() -> Review:
    return review_of(
        finding_at(line(7), "An anchored line."),
        finding_at(line(99), "A line off the diff."),
        finding_at(span(7, 12), "A span."),
        finding_at(span(1, 3), "A span off it."),
        finding_at(FileAnchor(kind="file", path="a.py"), "A whole file."),
        finding_at(PullRequestAnchor(kind="pull_request"), "The change as a whole."),
    )


def appearances(payload: dict[str, Any], body: str) -> int:
    """How many times one finding's prose appears anywhere in the review being posted."""
    posted = [payload["body"], *(comment["body"] for comment in payload["comments"])]
    return sum(str(text).count(body) for text in posted)


def test_no_finding_is_lost() -> None:
    # The done condition, asserted directly: every finding that survived verification is on the
    # pull request exactly once, wherever it landed.
    review = mixed()
    payload = review_payload(COMMIT, review, ADDED)
    assert len(payload["comments"]) == 2
    for finding in review.findings:
        assert appearances(payload, finding.body) == 1


def test_no_finding_is_lost_when_nothing_attaches() -> None:
    # The payload the retry posts. Everything lands in the summary and nothing is anchored.
    review = mixed()
    payload = review_payload(COMMIT, review, set())
    assert payload["comments"] == []
    for finding in review.findings:
        assert appearances(payload, finding.body) == 1


def test_the_two_empty_outcomes_read_differently() -> None:
    # A second "nothing found" that reads as retracting the first review is what this prevents.
    assert nothing_to_report(review_of(already_said=True)) != nothing_to_report(review_of())
    assert nothing_to_report(review_of()) in review_payload(COMMIT, review_of(), ADDED)["body"]
    assert (
        nothing_to_report(review_of(already_said=True))
        in review_payload(COMMIT, review_of(already_said=True), ADDED)["body"]
    )


def test_a_review_with_findings_claims_neither_emptiness() -> None:
    body = payload_of(finding_at(line(7)))["body"]
    assert nothing_to_report(review_of()) not in body
    assert nothing_to_report(review_of(already_said=True)) not in body
