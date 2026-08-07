"""Tests of `coral.github.post`.

Nothing here posts. What the module decides on its own is how a finding reads once Coral has
composed it out of the pieces the model returned separately, and that is what these cover.
"""

from coral.github.marker import marker
from coral.github.post import bullet, count, rendered_finding, signed
from coral.schema import Finding, LineAnchor, RegressionTest

COMMIT = "a" * 40

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


def test_a_count_of_one_is_singular() -> None:
    assert count(1, "finding") == "1 finding"
    assert count(2, "finding") == "2 findings"
