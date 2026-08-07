"""Tests of `coral.runner`.

Each test writes an event payload into `tmp_path` and points the environment at it, which is the
runner's own protocol rather than a fake of Coral's code.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from coral import runner
from coral.runner import Comment


def deliver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, payload: dict[str, Any]
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(payload))
    monkeypatch.setenv("GITHUB_EVENT_NAME", name)
    monkeypatch.setenv("GITHUB_REPOSITORY", "kkestell/coral-test")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))


def test_a_pull_request_event_carries_a_number_and_no_comment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deliver(monkeypatch, tmp_path, "pull_request", {"pull_request": {"number": 7}})
    event = runner.event()
    assert (event.owner, event.repo, event.number) == ("kkestell", "coral-test", 7)
    assert event.comment is None


def test_an_issue_comment_reacts_through_the_issues_namespace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deliver(
        monkeypatch,
        tmp_path,
        "issue_comment",
        {
            "issue": {"number": 7},
            "comment": {"id": 42, "body": "/coral", "author_association": "OWNER"},
        },
    )
    event = runner.event()
    assert event.number == 7
    assert event.comment == Comment(id=42, namespace="issues", body="/coral", association="OWNER")


def test_a_review_comment_reacts_through_the_pulls_namespace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deliver(
        monkeypatch,
        tmp_path,
        "pull_request_review_comment",
        {
            "pull_request": {"number": 7},
            "comment": {"id": 42, "body": "/coral", "author_association": "MEMBER"},
        },
    )
    event = runner.event()
    assert event.number == 7
    assert event.comment == Comment(id=42, namespace="pulls", body="/coral", association="MEMBER")


def test_an_event_coral_does_not_handle_is_a_broken_workflow_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deliver(monkeypatch, tmp_path, "push", {})
    with pytest.raises(AssertionError):
        runner.event()


def test_a_missing_event_path_names_the_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deliver(monkeypatch, tmp_path, "pull_request", {"pull_request": {"number": 7}})
    monkeypatch.delenv("GITHUB_EVENT_PATH")
    with pytest.raises(KeyError) as raised:
        runner.event()
    assert raised.value.args == ("GITHUB_EVENT_PATH",)


def test_write_output_appends_and_leaves_what_was_there_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "output"
    output.write_text("already=here\n")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    runner.write_output("proceed", "true")
    runner.write_output("head-sha", "0f4c1d2")
    assert output.read_text() == "already=here\nproceed=true\nhead-sha=0f4c1d2\n"


def test_write_output_refuses_a_value_holding_a_newline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The heredoc form of the Actions protocol is not built, so a multiline value would be
    # written as a broken one. This is what stops a later caller assuming it works.
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    with pytest.raises(AssertionError):
        runner.write_output("summary", "one\ntwo")


def test_the_temporary_directory_is_made_under_the_runners_own(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    assert runner.temporary_directory() == tmp_path / "coral"
    assert runner.pull_request_path() == tmp_path / "coral" / "pull-request.json"
    assert runner.conversation_path() == tmp_path / "coral" / "conversation.json"
    assert (tmp_path / "coral").is_dir()
