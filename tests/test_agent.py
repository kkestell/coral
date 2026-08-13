"""Tests of `coral.agent`.

No model is called and no agent is built here; that is live only. What these tests cover is the
prompt loading, the deadline hook, what the agent is asked for, and two behaviors of the dependency
the construction relies on.
"""

import time
from inspect import signature
from typing import Any

import pytest
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.tools import StructuredTool

import coral.agent
from coral import container
from coral.agent import (
    SHELL_CEILING_SECONDS,
    DeadlineMiddleware,
    SpendHandler,
    SpendMiddleware,
    ToolProgressHandler,
    _run,
    caught,
    execute_tool,
    format_tool_arguments,
    profile_of,
    review_prompt,
    verify_prompt,
)
from coral.deadline import Deadline, budget_seconds
from coral.github.client import GitHub
from coral.github.issues import IssueEvidence
from coral.openrouter import ModelFacts
from coral.schema import Review, Verification
from coral.spend import Ledger, cap_dollars

BUDGET = budget_seconds("20")
CAP = cap_dollars("2.00")

# What `coral/openrouter.py` reduces the default model's entry in a real `GET /api/v1/models`
# answer to, 2026-08-07.
LUNA = ModelFacts(
    context_length=1_050_000,
    max_completion_tokens=128_000,
    parameters=frozenset(
        {
            "include_reasoning",
            "max_completion_tokens",
            "max_tokens",
            "reasoning",
            "reasoning_effort",
            "response_format",
            "seed",
            "structured_outputs",
            "tool_choice",
            "tools",
        }
    ),
)


def test_the_prompt_comes_out_of_the_installed_package() -> None:
    assert "Coral" in review_prompt()


def test_the_verifier_prompt_comes_out_of_the_installed_package() -> None:
    prompt = verify_prompt()
    assert "Coral" in prompt
    assert "search_open_issues" in prompt
    assert "duplicate_issue" in prompt
    assert "untrusted evidence" in prompt


def test_a_live_deadline_lets_the_model_be_called() -> None:
    middleware = DeadlineMiddleware(Deadline(started=time.monotonic(), budget=BUDGET))
    assert middleware.before_model(state={}, runtime=None) is None  # type: ignore[arg-type]


def test_an_expired_deadline_stops_the_run_and_says_what_it_spent() -> None:
    started = time.monotonic() - (BUDGET + 1)
    middleware = DeadlineMiddleware(Deadline(started=started, budget=BUDGET))
    with pytest.raises(RuntimeError, match="ran out of time"):
        middleware.before_model(state={}, runtime=None)  # type: ignore[arg-type]


def answered(metadata: dict[str, Any]) -> LLMResult:
    """One model response, shaped the way LangChain hands it to a callback.

    `response_metadata` is where `ChatOpenRouter` copies the `cost` OpenRouter's `usage` object
    carries, on the streaming path and the other one both.
    """
    message = AIMessage(content="A step.", response_metadata=metadata)
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def test_a_responses_cost_reaches_the_ledger() -> None:
    ledger = Ledger(cap=CAP)
    SpendHandler(ledger, "openai/gpt-5.6-luna").on_llm_end(
        answered({"cost": 2.015e-05, "is_byok": False}), run_id=None
    )
    assert ledger.spent == 2.015e-05


def test_a_response_carrying_no_cost_is_counted_rather_than_treated_as_free() -> None:
    # There is no amount to add, so what the ledger records is that it could not price this one.
    ledger = Ledger(cap=CAP)
    SpendHandler(ledger, "openai/gpt-5.6-luna").on_llm_end(answered({}), run_id=None)
    assert ledger.spent == 0.0
    assert ledger.unpriced == 1


@pytest.mark.parametrize("cost", [float("nan"), float("inf"), -0.01, "free", None])
def test_a_cost_the_ledger_cannot_hold_a_cap_against_is_counted_as_unpriced(cost: Any) -> None:
    # The provider reports this field, so a run is not held to its cap by trusting it. A NaN
    # ledger never reaches the cap and a negative cost pays for later spending; both stop the run
    # instead, which is what an unreported cost already does.
    ledger = Ledger(cap=CAP)
    SpendHandler(ledger, "openai/gpt-5.6-luna").on_llm_end(answered({"cost": cost}), run_id=None)
    assert ledger.spent == 0.0
    assert ledger.unpriced == 1


def test_a_ledger_under_its_cap_lets_the_model_be_called() -> None:
    middleware = SpendMiddleware(Ledger(cap=CAP, spent=0.5))
    assert middleware.before_model(state={}, runtime=None) is None  # type: ignore[arg-type]


def test_a_ledger_at_its_cap_stops_the_run() -> None:
    middleware = SpendMiddleware(Ledger(cap=0.0005, spent=0.000512))
    with pytest.raises(RuntimeError, match="ran out of money"):
        middleware.before_model(state={}, runtime=None)  # type: ignore[arg-type]


def test_a_run_coral_cannot_price_is_stopped_however_little_it_has_counted() -> None:
    # A cap Coral cannot measure against is not a cap, and a passed-through key has no
    # provider-side limit behind it.
    middleware = SpendMiddleware(Ledger(cap=CAP, spent=0.0, unpriced=1))
    with pytest.raises(RuntimeError, match="carried no cost"):
        middleware.before_model(state={}, runtime=None)  # type: ignore[arg-type]


def test_a_failing_tool_answers_with_its_error(caplog: pytest.LogCaptureFixture) -> None:
    # A bad command is the model's to correct on its next step, not a reason to end a review with
    # most of its budget unspent.
    def refuse(command: str) -> str:
        raise RuntimeError("Container unavailable")

    with caplog.at_level("INFO", logger="coral.agent"):
        assert caught("execute", refuse)("pwd") == "RuntimeError: Container unavailable"
    assert any(
        message.startswith("execute failed; handing the error back to the model")
        for message in caplog.messages
    )
    assert not any("refuse" in message for message in caplog.messages)


def test_a_wrapped_tool_keeps_the_signature_langchain_injects_against() -> None:
    def execute(command: str, runtime: int, timeout: int = 300) -> str:
        return command

    assert list(signature(caught("execute", execute)).parameters) == [
        "command",
        "runtime",
        "timeout",
    ]


def test_tool_progress_uses_the_public_name_and_model_arguments(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def execute(command: str, timeout: int, runtime: object | None = None) -> str:
        """Run a command."""
        return command

    tool = StructuredTool.from_function(execute, name="execute")
    with caplog.at_level("INFO", logger="coral.agent"):
        assert (
            tool.invoke(
                {"command": "pwd", "timeout": 30, "runtime": object()},
                config={"callbacks": [ToolProgressHandler()]},
            )
            == "pwd"
        )

    assert "Calling execute(command='pwd', timeout=30)." in caplog.messages
    assert any(message.startswith("execute finished in ") for message in caplog.messages)
    assert not any("runtime" in message or "sync_" in message for message in caplog.messages)


def test_tool_progress_clears_a_failed_calls_timer(caplog: pytest.LogCaptureFixture) -> None:
    def fail(command: str) -> str:
        """Fail to run a command."""
        raise RuntimeError("unavailable")

    handler = ToolProgressHandler()
    tool = StructuredTool.from_function(fail, name="execute")
    with caplog.at_level("INFO", logger="coral.agent"):
        with pytest.raises(RuntimeError, match="unavailable"):
            tool.invoke({"command": "pwd"}, config={"callbacks": [handler]})

    assert handler.calls == {}
    assert any(
        message.startswith("execute failed in ") and "unavailable" in message
        for message in caplog.messages
    )


def test_tool_progress_bounds_and_escapes_long_arguments() -> None:
    command = "first line\n" + "x" * 200
    rendered = format_tool_arguments("execute", {"command": command, "timeout": 30})
    assert rendered.startswith("command='first line\\n")
    assert f"({len(command)} characters), timeout=30" in rendered
    assert command not in rendered
    assert "\n" not in rendered


def test_the_shell_tool_runs_in_its_named_container(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, int]] = []

    def run(name: str, command: str, timeout: int) -> container.Output:
        calls.append((name, command, timeout))
        return container.Output(output="found it", exit_code=3, truncated=False)

    monkeypatch.setattr(container, "execute", run)
    result = execute_tool("coral-reviewer").invoke({"command": "rg token", "timeout": 17})
    assert result == "found it\n\n[exit code: 3]"
    assert calls == [("coral-reviewer", "rg token", 17)]


def test_the_shell_tool_refuses_a_timeout_past_its_ceiling() -> None:
    result = execute_tool("coral-reviewer").invoke(
        {"command": "sleep forever", "timeout": SHELL_CEILING_SECONDS + 1}
    )
    assert result == f"Error: timeout must be between 1 and {SHELL_CEILING_SECONDS} seconds."


class Built:
    """Stands in for the agent: the run reaches `invoke` and gets an empty message list."""

    def __init__(self) -> None:
        self.config: dict[str, Any] = {}

    # These methods intentionally mirror the LangChain object `_run` uses.
    def with_config(self, config: dict[str, Any]) -> "Built":
        self.config = config
        return self

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"messages": []}


def run_against(
    monkeypatch: pytest.MonkeyPatch,
    effort: str = "",
    facts: ModelFacts = LUNA,
    extra_tools: list[Any] | None = None,
    deadline: Deadline | None = None,
    ledger: Ledger | None = None,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Run the reviewer with the agent's construction intercepted, and return what it was built of.

    The model client is real and the framework's factory is not, so everything `_run` decides is
    observable without a request being made.
    """
    built: list[tuple[Any, dict[str, Any], Built]] = []

    def build(model: Any, **keywords: Any) -> Built:
        agent = Built()
        built.append((model, keywords, agent))
        return agent

    monkeypatch.setattr(coral.agent, "create_agent", build)
    _run(
        "not-a-key",
        "openai/gpt-5.6-luna",
        effort,
        facts,
        "coral-reviewer",
        "review this",
        deadline or Deadline(started=time.monotonic(), budget=BUDGET),
        ledger or Ledger(cap=CAP),
        review_prompt(),
        Review,
        extra_tools,
    )
    return built[0][0], built[0][1], built[0][2].config


def test_a_run_that_ended_past_its_budget_fails_rather_than_answering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The middleware checks before each model call, so the request that produced the answer is
    # checked nowhere else. Without this the reviewer's empty review, or the verifier's last
    # verdicts, would be posted after a request that ran past the whole budget.
    spent = Deadline(started=time.monotonic() - (BUDGET + 1), budget=BUDGET)
    with pytest.raises(RuntimeError, match="ran out of time"):
        run_against(monkeypatch, deadline=spent)


def test_a_run_that_ended_over_its_cap_fails_rather_than_answering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="ran out of money"):
        run_against(monkeypatch, ledger=Ledger(cap=CAP, spent=CAP))


def test_a_run_whose_spending_was_never_measured_fails_rather_than_answering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="carried no cost"):
        run_against(monkeypatch, ledger=Ledger(cap=CAP, unpriced=1))


def test_every_run_installs_one_progress_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callbacks = run_against(monkeypatch)[2]["callbacks"]
    assert sum(isinstance(callback, SpendHandler) for callback in callbacks) == 1
    assert sum(isinstance(callback, ToolProgressHandler) for callback in callbacks) == 1


def test_the_structured_output_strategy_is_named_rather_than_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Left to the framework, the strategy is picked from the model's profile and from a table of
    # model names kept upstream, and a model either of those catches answers in the schema on its
    # first response — a review written from the diff alone. Naming the synthetic tool is what
    # holds the agent loop on every model, so a change back to detection fails here.
    strategy = run_against(monkeypatch)[1]["response_format"]
    assert isinstance(strategy, ToolStrategy)
    assert strategy.schema is Review


def test_only_the_verifier_receives_bounded_issue_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = IssueEvidence(GitHub(token="not-a-token"), "owner", "repo", 1)
    reviewer_tools = run_against(monkeypatch)[1]["tools"]
    verifier_tools = run_against(
        monkeypatch,
        extra_tools=[evidence.search_open_issues, evidence.view_issue],
    )[1]["tools"]
    assert len(reviewer_tools) == 1
    assert isinstance(reviewer_tools[0], StructuredTool)
    assert reviewer_tools[0].name == "execute"
    assert verifier_tools[1:] == [evidence.search_open_issues, evidence.view_issue]
    assert not any(isinstance(tool, GitHub) for tool in verifier_tools)


def test_verify_findings_passes_only_issue_evidence_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Any, ...]] = []

    def run(*arguments: Any) -> dict[str, Any]:
        calls.append(arguments)
        return {"structured_response": Verification(verdicts=[])}

    evidence = IssueEvidence(GitHub(token="not-a-token"), "owner", "repo", 1)
    monkeypatch.setattr(coral.agent, "_run", run)
    coral.agent.verify_findings(
        "not-a-key",
        "openai/gpt-5.6-luna",
        "",
        LUNA,
        "coral-verifier",
        "verify this",
        Deadline(started=time.monotonic(), budget=BUDGET),
        Ledger(cap=CAP),
        evidence,
    )
    assert calls[0][-1] == [evidence.search_open_issues, evidence.view_issue]


def test_the_default_models_profile_is_the_one_coral_used_to_carry_by_hand() -> None:
    # The mapping's own check: fetching the listing rather than hardcoding these five numbers is
    # only safe if it reproduces them. This is the unchanged-install half of the configuration
    # inputs, in a unit test.
    assert profile_of(LUNA) == {
        "tool_calling": True,
        "reasoning_output": True,
        "max_input_tokens": 1_050_000,
        "max_output_tokens": 128_000,
        "temperature": False,
    }


def test_a_model_that_takes_a_temperature_says_so() -> None:
    takes_it = ModelFacts(
        context_length=256_000, max_completion_tokens=16_384, parameters=frozenset({"temperature"})
    )
    assert profile_of(takes_it)["temperature"] is True


def test_a_model_with_no_reported_output_ceiling_is_given_none() -> None:
    # Rather than a guess. The key's absence is what LangChain's own lookup miss looks like.
    unreported = ModelFacts(
        context_length=1_048_576, max_completion_tokens=None, parameters=frozenset({"tools"})
    )
    assert "max_output_tokens" not in profile_of(unreported)


def test_no_effort_sends_no_reasoning_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The default input, and today's request: the provider applies its own effort.
    assert run_against(monkeypatch)[0].reasoning is None


def test_an_effort_reaches_openrouters_reasoning_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Passed through unvalidated. What an effort may be is the provider's rule, and its refusal is
    # what a caller who got it wrong reads.
    assert run_against(monkeypatch, effort="high")[0].reasoning == {"effort": "high"}
