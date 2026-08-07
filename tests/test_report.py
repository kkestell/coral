"""Tests of `coral.report`.

Nothing here posts. What the module decides on its own is whether a comment is owed and what that
comment reads like. Each case writes an event payload into `tmp_path` and points `RUNNER_TEMP` at
it, which is the runner's own protocol rather than a fake of Coral's code.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from coral import runner
from coral.report import REASON_LIMIT, described, failure_comment, owed

RUN_URL = "https://github.com/kkestell/coral-test/actions/runs/17"


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
            "comment": {"id": 42, "body": body, "author_association": "OWNER"},
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


def test_nothing_is_owed_once_the_review_step_has_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commented(monkeypatch, tmp_path, "/coral")
    runner.reported_path().write_text("")
    assert owed(runner.event()) is False


def test_nothing_is_owed_for_a_comment_that_only_mentions_the_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The job-level condition let this delivery allocate a runner. It asked for nothing, so a run
    # that fails on it owes nobody a comment.
    commented(monkeypatch, tmp_path, "You can ask for another look with /coral.")
    assert owed(runner.event()) is False


def test_a_request_that_failed_is_owed_a_comment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commented(monkeypatch, tmp_path, "/coral")
    assert owed(runner.event()) is True


def test_a_pull_request_delivery_that_failed_is_owed_a_comment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deliver(monkeypatch, tmp_path, "pull_request", {"pull_request": {"number": 7}})
    assert owed(runner.event()) is True
