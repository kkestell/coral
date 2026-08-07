"""Tests of `coral.environment`.

The point of these tests is the omissions. An allowlist excludes by construction, so what is
worth asserting is that the names which must never reach the agent's shell really do not.
"""

import pytest

from coral.environment import KEEP, shell_environment


def test_every_allowed_name_present_in_the_source_survives() -> None:
    source = dict.fromkeys(KEEP, "value")
    assert shell_environment(source) == source


def test_an_allowed_name_the_source_does_not_have_is_simply_absent() -> None:
    kept = shell_environment({"PATH": "/usr/bin", "HOME": "/home/runner"})
    assert kept == {"PATH": "/usr/bin", "HOME": "/home/runner"}
    assert "TMPDIR" not in kept
    assert "LANG" not in kept


def test_neither_secret_survives() -> None:
    kept = shell_environment(
        {"PATH": "/usr/bin", "GITHUB_TOKEN": "ghs_x", "OPENROUTER_API_KEY": "sk-x"}
    )
    assert kept == {"PATH": "/usr/bin"}


def test_coral_own_interpreter_does_not_survive() -> None:
    # `VIRTUAL_ENV` and the `UV_*` variables point at Coral's virtual environment. A reviewed
    # repository's test suite has to run against its own interpreter, not this one.
    kept = shell_environment(
        {"PATH": "/usr/bin", "VIRTUAL_ENV": "/tmp/coral/.venv", "UV_CACHE_DIR": "/tmp/uv"}
    )
    assert kept == {"PATH": "/usr/bin"}


def test_a_name_nobody_thought_about_does_not_survive() -> None:
    assert shell_environment({"PATH": "/usr/bin", "AWS_SECRET_ACCESS_KEY": "x"}) == {
        "PATH": "/usr/bin"
    }


def test_a_source_without_path_is_a_broken_invocation() -> None:
    with pytest.raises(AssertionError):
        shell_environment({"HOME": "/home/runner"})
