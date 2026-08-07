"""Tests of `coral.agent`.

No model is called and no agent is built here; that is live only. What these tests cover is the
prompt loading, the deadline hook, and one behavior of the dependency the construction relies on.
"""

import time

import pytest

from coral.agent import DeadlineMiddleware, review_prompt, verify_prompt
from coral.deadline import STEP_BUDGET_SECONDS, Deadline


def test_the_prompt_comes_out_of_the_installed_package() -> None:
    assert "Coral" in review_prompt()


def test_the_verifier_prompt_comes_out_of_the_installed_package() -> None:
    assert "Coral" in verify_prompt()


def test_a_live_deadline_lets_the_model_be_called() -> None:
    middleware = DeadlineMiddleware(Deadline(started=time.monotonic(), budget=STEP_BUDGET_SECONDS))
    assert middleware.before_model(state={}, runtime=None) is None  # type: ignore[arg-type]


def test_an_expired_deadline_stops_the_run_and_says_what_it_spent() -> None:
    started = time.monotonic() - (STEP_BUDGET_SECONDS + 1)
    middleware = DeadlineMiddleware(Deadline(started=started, budget=STEP_BUDGET_SECONDS))
    with pytest.raises(RuntimeError, match="ran out of time"):
        middleware.before_model(state={}, runtime=None)  # type: ignore[arg-type]


def test_the_filesystem_middleware_name_is_the_class_name() -> None:
    # Recording a dependency's behavior, and the one Coral's construction rests on: middleware
    # merges by name, so an instance named `FilesystemMiddleware` replaces the framework's own
    # rather than joining it. An upstream rename would leave two middlewares each registering a
    # `read_file` tool, and the shell ceiling would be whichever one won.
    from deepagents import FilesystemMiddleware
    from deepagents.backends import LocalShellBackend

    middleware = FilesystemMiddleware(backend=LocalShellBackend("/tmp"))
    assert middleware.name == "FilesystemMiddleware"
