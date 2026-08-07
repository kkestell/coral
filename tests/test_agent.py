"""Tests of `coral.agent`.

No model is called and no agent is built here; that is live only. What these tests cover is the
prompt loading, the deadline hook, what the agent is asked for, and two behaviors of the dependency
the construction relies on.
"""

import time
from inspect import signature
from pathlib import Path
from typing import Any

import pytest
from langchain.agents.structured_output import ToolStrategy
from langchain_core.tools import StructuredTool

import coral.agent
from coral.agent import (
    SHELL_CEILING_SECONDS,
    ContainerBackend,
    DeadlineMiddleware,
    _run,
    caught,
    forgiving,
    review_prompt,
    verify_prompt,
)
from coral.deadline import STEP_BUDGET_SECONDS, Deadline
from coral.schema import Review


def backend(tmp_path: Path) -> ContainerBackend:
    """A backend over an empty directory. Nothing here executes, so no container is started."""
    return ContainerBackend(tmp_path, "coral-reviewer", SHELL_CEILING_SECONDS)


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


def test_a_failing_tool_answers_with_its_error() -> None:
    # A bad path is the model's to correct on its next step, not a reason to end a review with
    # most of its budget unspent. Observed on a real run, where the first `read_file` call used
    # `..` and the `ValueError` propagated out of `invoke`.
    def refuse(path: str) -> str:
        raise ValueError("Path traversal not allowed")

    assert caught(refuse)("../etc/passwd") == "ValueError: Path traversal not allowed"


def test_a_wrapped_tool_keeps_the_signature_langchain_injects_against() -> None:
    def read(file_path: str, runtime: int, offset: int = 0) -> str:
        return file_path

    assert list(signature(caught(read)).parameters) == ["file_path", "runtime", "offset"]


def test_every_filesystem_tool_is_wrapped(tmp_path: Path) -> None:
    # `execute` included. A shell command that will not parse is the same kind of mistake.
    from deepagents import FilesystemMiddleware

    middleware = forgiving(FilesystemMiddleware(backend=backend(tmp_path)))
    for tool in middleware.tools:
        assert isinstance(tool, StructuredTool)
        assert hasattr(tool.func, "__wrapped__"), f"{tool.name} was left raising"


def test_the_filesystem_middleware_name_is_the_class_name(tmp_path: Path) -> None:
    # Recording a dependency's behavior, and the one Coral's construction rests on: middleware
    # merges by name, so an instance named `FilesystemMiddleware` replaces the framework's own
    # rather than joining it. An upstream rename would leave two middlewares each registering a
    # `read_file` tool, and the shell ceiling would be whichever one won.
    from deepagents import FilesystemMiddleware

    assert FilesystemMiddleware(backend=backend(tmp_path)).name == "FilesystemMiddleware"


def test_the_container_backend_is_still_offered_a_shell(tmp_path: Path) -> None:
    # The framework registers `execute` only for a backend passing `isinstance` against
    # `SandboxBackendProtocol`, which is why the container is a subclass rather than a wrapper
    # forwarding to one. Without this the agent would have file tools and no shell.
    from deepagents import FilesystemMiddleware

    middleware = FilesystemMiddleware(backend=backend(tmp_path))
    assert "execute" in {tool.name for tool in middleware.tools}


def test_the_structured_output_strategy_is_named_rather_than_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Left to the framework, the strategy is picked from the model's profile and from a table of
    # model names kept upstream, and a model either of those catches answers in the schema on its
    # first response — a review written from the diff alone. Naming the synthetic tool is what
    # holds the agent loop on every model, so a change back to detection fails here.
    built: list[dict[str, Any]] = []

    class Built:
        """Stands in for the agent: the run reaches `invoke` and gets an empty message list."""

        def with_config(self, config: dict[str, Any]) -> Built:
            return self

        def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
            return {"messages": []}

    def build(model: Any, **keywords: Any) -> Built:
        built.append(keywords)
        return Built()

    monkeypatch.setattr(coral.agent, "create_deep_agent", build)
    _run(
        "not-a-key",
        tmp_path,
        "coral-reviewer",
        "review this",
        Deadline(started=time.monotonic(), budget=STEP_BUDGET_SECONDS),
        review_prompt(),
        Review,
    )

    strategy = built[0]["response_format"]
    assert isinstance(strategy, ToolStrategy)
    assert strategy.schema is Review


def test_the_container_backends_execute_still_takes_the_ceiling(tmp_path: Path) -> None:
    # The framework introspects `execute`'s signature before forwarding a `timeout`, so an
    # override that dropped the keyword would silently lose the model's own ceiling.
    from deepagents.backends.protocol import execute_accepts_timeout

    assert execute_accepts_timeout(ContainerBackend)
    assert backend(tmp_path).ceiling == SHELL_CEILING_SECONDS
