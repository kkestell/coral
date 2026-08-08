"""Tests of `coral.runner`.

Each test writes an event payload into `tmp_path` and points the environment at it, which is the
runner's own protocol rather than a fake of Coral's code.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from coral import runner
from coral.runner import Comment, Push


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
            "comment": {"id": 42, "body": "/coral", "user": {"login": "kestell"}},
        },
    )
    event = runner.event()
    assert event.number == 7
    assert event.comment == Comment(id=42, namespace="issues", body="/coral", author="kestell")


def test_a_review_comment_reacts_through_the_pulls_namespace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deliver(
        monkeypatch,
        tmp_path,
        "pull_request_review_comment",
        {
            "pull_request": {"number": 7},
            "comment": {"id": 42, "body": "/coral", "user": {"login": "kestell"}},
        },
    )
    event = runner.event()
    assert event.number == 7
    assert event.comment == Comment(id=42, namespace="pulls", body="/coral", author="kestell")


def test_a_main_push_carries_its_commit_and_prior_main_tip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deliver(
        monkeypatch,
        tmp_path,
        "push",
        {
            "ref": "refs/heads/main",
            "after": "b" * 40,
            "before": "a" * 40,
        },
    )
    event = runner.event()
    assert event.number is None
    assert event.comment is None
    assert event.push == Push(sha="b" * 40, base="a" * 40, ref="refs/heads/main")


def test_an_initial_main_push_carries_githubs_zero_base(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deliver(
        monkeypatch,
        tmp_path,
        "push",
        {"ref": "refs/heads/main", "after": "a" * 40, "before": "0" * 40},
    )
    assert runner.event().push == Push(sha="a" * 40, base="0" * 40, ref="refs/heads/main")


def test_a_comment_whose_author_is_gone_reduces_rather_than_crashing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A deleted account arrives as a null `user`, the same absence the conversation reads off a
    # null `author`. Crashing here would fail the run before the access check could refuse it.
    deliver(
        monkeypatch,
        tmp_path,
        "issue_comment",
        {"issue": {"number": 7}, "comment": {"id": 42, "body": "/coral", "user": None}},
    )
    assert runner.event().comment == Comment(id=42, namespace="issues", body="/coral", author=None)


def test_an_event_coral_does_not_handle_is_a_broken_workflow_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deliver(monkeypatch, tmp_path, "workflow_dispatch", {})
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


def test_mask_writes_one_workflow_command(capsys: pytest.CaptureFixture[str]) -> None:
    runner.mask("sk-or-v1-secret")
    assert capsys.readouterr().out == "::add-mask::sk-or-v1-secret\n"


def test_mask_refuses_a_value_holding_a_newline() -> None:
    with pytest.raises(AssertionError):
        runner.mask("one\ntwo")


def test_the_temporary_directory_is_made_under_the_runners_own(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    assert runner.temporary_directory() == tmp_path / "coral"
    assert runner.pull_request_path() == tmp_path / "coral" / "pull-request.json"
    assert runner.conversation_path() == tmp_path / "coral" / "conversation.json"
    assert runner.push_path() == tmp_path / "coral" / "push.json"
    assert runner.payloads_path() == tmp_path / "coral" / "review-payloads.json"
    assert runner.issues_path() == tmp_path / "coral" / "issue-payloads.json"
    assert runner.reason_path() == tmp_path / "coral" / "reason.txt"
    assert (tmp_path / "coral").is_dir()
