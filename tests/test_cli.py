"""Tests of `coral.cli`."""

import logging
import sys

import pytest

from coral import cli

SUBCOMMANDS = ("resolve", "review", "publish", "rehearse")


def test_logging_keeps_coral_at_info_and_silences_httpx(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Asserted through what reaches stderr rather than through the arguments `basicConfig` was
    # passed, because `basicConfig` does nothing at all when the root logger already has a
    # handler — which under pytest it does. Emptying it is what makes the call mean anything.
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.NOTSET)
    monkeypatch.setattr(logging.getLogger("httpx"), "level", logging.NOTSET)

    cli.configure_logging()
    logging.getLogger("coral").info("coral progress")
    logging.getLogger("httpx").info("http request details")

    assert capsys.readouterr().err == "coral progress\n"


@pytest.mark.parametrize("subcommand", SUBCOMMANDS)
def test_each_subcommand_dispatches_only_to_its_handler(
    monkeypatch: pytest.MonkeyPatch, subcommand: str
) -> None:
    called: list[str] = []
    for name in SUBCOMMANDS:
        monkeypatch.setattr(cli, name, lambda arguments=None, name=name: called.append(name))
    # Only rehearse takes arguments of its own, and its commit is positional.
    argv = ["coral", subcommand, "head"] if subcommand == "rehearse" else ["coral", subcommand]
    monkeypatch.setattr(sys, "argv", argv)

    assert cli.main() == 0
    assert called == [subcommand]
