"""Tests of `coral.cli`."""

import logging
import sys

import pytest

from coral.cli import configure_logging


def test_logging_keeps_coral_at_info_and_silences_httpx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured: dict[str, object] = {}

    def basic_config(**keywords: object) -> None:
        configured.update(keywords)

    monkeypatch.setattr(logging, "basicConfig", basic_config)
    monkeypatch.setattr(logging.getLogger("httpx"), "level", logging.NOTSET)
    configure_logging()

    assert configured == {"level": logging.INFO, "format": "%(message)s", "stream": sys.stderr}
    assert logging.getLogger("httpx").level == logging.WARNING
