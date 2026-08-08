"""Tests of the bounded main-push issue reader."""

from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from coral.github.client import ApiError, GitHub
from coral.github.issues import (
    MAX_BODY_CHARACTERS,
    MAX_CANDIDATES,
    MAX_QUERY_CHARACTERS,
    MAX_SEARCH_TERMS,
    MAX_SEARCHES,
    MAX_VIEWS,
    IssueEvidence,
)


def issue(number: int, title: str = "An ordinary issue", **extra: Any) -> dict[str, Any]:
    return {"number": number, "title": title, "state": "open", **extra}


def reader(
    monkeypatch: pytest.MonkeyPatch, answer: Any, finding_count: int = MAX_SEARCHES
) -> tuple[IssueEvidence, list[str]]:
    paths: list[str] = []

    def get(github: GitHub, path: str) -> Any:
        paths.append(path)
        if callable(answer):
            return answer(path)
        return answer

    monkeypatch.setattr(GitHub, "get", get)
    return IssueEvidence(GitHub(token="not-a-token"), "owner", "repo", finding_count), paths


def test_search_uses_one_fixed_hybrid_open_issue_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence, paths = reader(
        monkeypatch,
        {
            "items": [
                issue(7, "Parser loses the last value", body="A body the search must hide."),
                issue(8, "Closed", state="closed"),
                issue(9, "A pull request", pull_request={"url": "https://example.invalid"}),
            ]
        },
    )

    result = evidence.search_open_issues(0, "parser loses a trailing value")

    parsed = urlsplit(paths[0])
    assert parsed.path == "/search/issues"
    assert parse_qs(parsed.query) == {
        "q": ["repo:owner/repo is:issue is:open parser loses a trailing value"],
        "per_page": [str(MAX_CANDIDATES)],
        "page": ["1"],
        "search_type": ["hybrid"],
    }
    assert "#7: Parser loses the last value" in result
    assert "Closed" not in result
    assert "pull request" not in result
    assert "A body the search must hide." not in result
    assert evidence.candidates == {7}
    assert evidence.searched_findings == {0}


def test_search_keeps_a_maintainer_created_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence, _ = reader(
        monkeypatch,
        {"items": [issue(7, "Fix the missing token", user={"login": "maintainer"})]},
    )

    assert "#7: Fix the missing token" in evidence.search_open_issues(0, "missing token")


def test_search_does_not_page_or_return_more_than_five_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence, paths = reader(
        monkeypatch,
        {"items": [issue(number) for number in range(1, MAX_CANDIDATES + 3)]},
    )

    result = evidence.search_open_issues(0, "a defect")

    assert len(paths) == 1
    assert "#5:" in result
    assert "#6:" not in result
    assert evidence.candidates == set(range(1, MAX_CANDIDATES + 1))


def test_search_refuses_a_repeat_without_another_request(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence, paths = reader(monkeypatch, {"items": []})

    evidence.search_open_issues(0, "a defect")
    result = evidence.search_open_issues(0, "a different wording")

    assert result == "That finding has already searched open issues."
    assert len(paths) == 1
    assert evidence.searches == 1


def test_search_limits_requests_to_ten(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence, paths = reader(monkeypatch, {"items": []}, finding_count=MAX_SEARCHES + 1)

    for finding in range(MAX_SEARCHES):
        evidence.search_open_issues(finding, "a defect")
    result = evidence.search_open_issues(MAX_SEARCHES, "one too many")

    assert result == "The open-issue search limit is exhausted."
    assert len(paths) == MAX_SEARCHES
    assert evidence.searches == MAX_SEARCHES


def test_search_rejects_oversized_or_qualified_terms(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence, paths = reader(monkeypatch, {"items": []})

    oversized = "x" * (MAX_SEARCH_TERMS + 1)
    assert "character limit" in evidence.search_open_issues(0, oversized)
    assert "plain language" in evidence.search_open_issues(1, "repo:another/repository defect")
    assert paths == []
    assert evidence.searched_findings == set()


def test_search_cuts_the_query_at_its_fixed_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence, paths = reader(monkeypatch, {"items": []})

    evidence.search_open_issues(0, "x" * MAX_SEARCH_TERMS)

    assert len(parse_qs(urlsplit(paths[0]).query)["q"][0]) == MAX_QUERY_CHARACTERS


def test_view_reads_only_a_search_candidate_and_records_an_open_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def answer(path: str) -> dict[str, Any]:
        if path.startswith("/search/issues?"):
            return {"items": [issue(7, "Parser loses the last value")]}
        return issue(7, "Parser loses the last value", body="The parser skips a final value.")

    evidence, paths = reader(monkeypatch, answer)
    evidence.search_open_issues(0, "parser loses a trailing value")

    result = evidence.view_issue(7)

    assert paths[1] == "/repos/owner/repo/issues/7"
    assert "Issue #7: Parser loses the last value" in result
    assert "Untrusted issue evidence" in result
    assert "The parser skips a final value." in result
    assert evidence.viewed_issues == {7}
    assert evidence.views == 1


def test_view_refuses_an_unsearched_number_without_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence, paths = reader(monkeypatch, {"items": []})

    assert evidence.view_issue(7) == "That issue was not returned by this review's searches."
    assert paths == []
    assert evidence.views == 0


def test_view_refuses_a_boolean_even_when_issue_one_was_a_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence, paths = reader(monkeypatch, issue(1, body="Evidence."))
    evidence.candidates.add(1)

    assert evidence.view_issue(True) == "That issue was not returned by this review's searches."
    assert paths == []


@pytest.mark.parametrize(
    "response",
    [
        issue(7, state="closed"),
        issue(7, pull_request={"url": "https://example.invalid"}),
    ],
)
def test_view_does_not_record_a_closed_issue_or_pull_request(
    monkeypatch: pytest.MonkeyPatch, response: dict[str, Any]
) -> None:
    evidence, _ = reader(monkeypatch, response)
    evidence.candidates.add(7)

    assert evidence.view_issue(7) == "That result is not an open ordinary issue."
    assert evidence.viewed_issues == set()


def test_view_does_not_record_an_unsuccessful_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def failed(github: GitHub, path: str) -> Any:
        raise ApiError("GET", path, 404, "Not Found")

    monkeypatch.setattr(GitHub, "get", failed)
    evidence = IssueEvidence(GitHub(token="not-a-token"), "owner", "repo", 1, candidates={7})

    assert evidence.view_issue(7) == "Unable to view that issue."
    assert evidence.viewed_issues == set()


def test_view_truncates_a_long_body_visibly(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence, _ = reader(monkeypatch, issue(7, body="x" * (MAX_BODY_CHARACTERS + 1)))
    evidence.candidates.add(7)

    result = evidence.view_issue(7)

    assert "x" * MAX_BODY_CHARACTERS in result
    assert "[Body truncated at 20000 characters.]" in result
    assert "x" * (MAX_BODY_CHARACTERS + 1) not in result


def test_view_limits_candidate_reads_to_ten(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence, paths = reader(monkeypatch, issue(7, body="Evidence."))
    evidence.candidates.add(7)

    for _ in range(MAX_VIEWS):
        evidence.view_issue(7)
    result = evidence.view_issue(7)

    assert result == "The candidate issue-view limit is exhausted."
    assert len(paths) == MAX_VIEWS
    assert evidence.views == MAX_VIEWS
