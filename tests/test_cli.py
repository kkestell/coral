"""Tests of `coral.cli`."""

import logging
import sys
from pathlib import Path

import pytest

from coral import cli
from coral.progress import Table
from coral.settings import AgentSettings, Settings

SETTINGS = Settings(
    openrouter_api_key="sk-test",
    review_agents=[AgentSettings(model="reviewer", effort="high")],
    num_reviews=1,
    max_concurrent_reviews=1,
    verification_agent=AgentSettings(model="verifier", effort="low"),
    time_budget_minutes=20,
    spend_cap_dollars=2.0,
)


def test_logging_keeps_coral_at_info_and_silences_httpx(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.NOTSET)
    monkeypatch.setattr(logging.getLogger("httpx"), "level", logging.NOTSET)

    cli.configure_logging()
    logging.getLogger("coral").info("coral progress")
    logging.getLogger("httpx").info("http request details")

    assert capsys.readouterr().err == "coral progress\n"


def test_an_explicit_scope_reaches_the_review_unchanged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[tuple[Path, str, Settings]] = []
    monkeypatch.setattr(sys, "argv", ["coral", "focus on the parser"])
    monkeypatch.setattr(cli, "load_settings", lambda: SETTINGS)

    def review(workspace: Path, scope: str, settings: Settings, table: Table) -> str:
        seen.append((workspace, scope, settings))
        return "done"

    monkeypatch.setattr(cli, "review", review)

    assert cli.main() == 0
    assert seen == [(Path.cwd(), "focus on the parser", SETTINGS)]
    assert capsys.readouterr().out == "done\n"


def test_an_absent_scope_uses_the_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(sys, "argv", ["coral"])
    monkeypatch.setattr(cli, "load_settings", lambda: SETTINGS)
    monkeypatch.setattr(cli, "default_scope", lambda workspace: "the automatic scope")

    def review(workspace: Path, scope: str, settings: Settings, table: Table) -> str:
        seen.append(scope)
        return "done"

    monkeypatch.setattr(cli, "review", review)

    assert cli.main() == 0
    assert seen == ["the automatic scope"]
    assert capsys.readouterr().out == "done\n"


def test_a_failure_is_one_stderr_message_without_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["coral", "anything"])
    monkeypatch.setattr(cli, "load_settings", lambda: (_ for _ in ()).throw(RuntimeError("bad")))

    assert cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Coral failed: bad\n"
