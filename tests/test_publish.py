"""Tests of `coral.publish`.

Nothing here posts. Most of `publish()` has no unit test of its own: its judgment is `owed` and an
`exists()` call, and its prose is `failure_comment` and `submitted`. The main-push branch is the
exception, because whether it provisions labels is a decision made nowhere else. Each case writes
an event payload into `tmp_path` and points `RUNNER_TEMP` at it, which is the runner's own protocol
rather than a fake of Coral's code.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from coral import runner
from coral.command import Access
from coral.github.client import GitHub
from coral.github.post import IssuePayload, IssuePayloads, write_issue_payloads
from coral.publish import (
    REASON_LIMIT,
    described,
    failure_comment,
    moved_comment,
    owed,
    publish,
)

RUN_URL = "https://github.com/kkestell/coral-test/actions/runs/17"
COMMIT = "9f3a1c2b4d5e6f708192a3b4c5d6e7f809a1b2c3"
PRIOR_COMMIT = "1a2b3c4d5e6f708192a3b4c5d6e7f809a1b2c3d4"


def access(permission: str) -> Access:
    """An `Access` over a GitHub answering the permission endpoint with one verdict."""

    class Answering(GitHub):
        def get(self, path: str) -> Any:
            return {"permission": permission}

    return Access(github=Answering(token="not a real token"), owner="kkestell", repo="coral-test")


def deliver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, payload: dict[str, Any]
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(payload))
    monkeypatch.setenv("GITHUB_EVENT_NAME", name)
    monkeypatch.setenv("GITHUB_REPOSITORY", "kkestell/coral-test")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))


def commented(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str) -> None:
    deliver(
        monkeypatch,
        tmp_path,
        "issue_comment",
        {
            "issue": {"number": 7},
            "comment": {"id": 42, "body": body, "user": {"login": "kestell"}},
        },
    )


def test_a_reason_is_the_exceptions_type_and_message() -> None:
    assert described(RuntimeError("Coral ran out of time.")) == (
        "RuntimeError: Coral ran out of time."
    )


def test_a_message_longer_than_the_limit_is_cut_and_says_so() -> None:
    reason = described(ValueError("x" * (REASON_LIMIT * 2)))
    assert len(reason) == REASON_LIMIT
    assert reason.endswith("…")


def test_a_multiline_message_survives_whole_under_the_limit() -> None:
    # A provider error arrives with newlines in it, and the fence is what makes them harmless.
    assert described(ValueError("one\ntwo")) == "ValueError: one\ntwo"


def test_a_reason_is_fenced_and_the_run_is_linked() -> None:
    comment = failure_comment("RuntimeError: boom", RUN_URL)
    assert "````\nRuntimeError: boom\n````" in comment
    assert RUN_URL in comment
    assert "/coral" in comment


def test_a_comment_with_no_reason_carries_no_fence() -> None:
    comment = failure_comment(None, RUN_URL)
    assert "```" not in comment
    assert RUN_URL in comment


def test_nothing_is_owed_for_a_comment_that_only_mentions_the_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The job-level condition let this delivery allocate a runner. It asked for nothing, so a run
    # that fails on it owes nobody a comment.
    commented(monkeypatch, tmp_path, "You can ask for another look with /coral.")
    assert owed(runner.event(), access("admin")) is False


def test_a_request_that_failed_is_owed_a_comment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commented(monkeypatch, tmp_path, "/coral")
    assert owed(runner.event(), access("admin")) is True


def test_a_request_from_somebody_without_write_access_is_owed_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A stranger cannot make Coral speak, on the failure path either.
    commented(monkeypatch, tmp_path, "/coral")
    assert owed(runner.event(), access("read")) is False


def test_a_pull_request_delivery_that_failed_is_owed_a_comment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deliver(monkeypatch, tmp_path, "pull_request_target", {"pull_request": {"number": 7}})
    assert owed(runner.event(), access("admin")) is True


def test_a_branch_that_moved_under_the_review_gets_the_reason_and_a_way_back() -> None:
    # Nothing re-triggers Coral after a push, so this comment is the only sign the asker gets.
    comment = moved_comment(COMMIT)
    assert COMMIT in comment
    assert "/coral" in comment


def published(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, issues: list[IssuePayload]
) -> list[str]:
    """What `publish()` calls for a main push whose review left these issues, in order."""
    deliver(
        monkeypatch,
        tmp_path,
        "push",
        {"after": COMMIT, "before": PRIOR_COMMIT, "ref": "refs/heads/main"},
    )
    monkeypatch.setenv("GITHUB_TOKEN", "not a real token")
    write_issue_payloads(runner.issues_path(), IssuePayloads(issues=issues))
    calls: list[str] = []
    monkeypatch.setattr("coral.publish.create_labels", lambda *_: calls.append("labels"))
    monkeypatch.setattr("coral.publish.post_issue", lambda *_: calls.append("issue"))
    publish()
    return calls


def test_an_empty_main_review_provisions_no_labels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Review writes the artifact for every main push, so an empty one reaches here too.
    assert published(monkeypatch, tmp_path, []) == []


def test_a_main_review_with_a_finding_provisions_labels_before_filing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    issue = IssuePayload(title="The parser drops the last token.", body="body", labels=["coral"])
    assert published(monkeypatch, tmp_path, [issue]) == ["labels", "issue"]
