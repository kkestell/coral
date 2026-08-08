"""The agent: the model client, the backend, the middleware, and the two runs.

The only module that imports the agent framework. Everything else in Coral depends on the review
object in `coral/schema.py` and never on DeepAgents, which is what keeps the framework's two
seconds of import off `coral resolve` and keeps the rest of the code testable without it.
"""

import functools
import logging
import time
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, Final

from deepagents import (
    FilesystemMiddleware,
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.model_profile import ModelProfile
from langchain_core.messages import HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.tools import StructuredTool
from langchain_openrouter import ChatOpenRouter
from langgraph.runtime import Runtime
from pydantic import SecretStr

from coral import container
from coral.deadline import Deadline
from coral.openrouter import ModelFacts
from coral.schema import Review, Verification, review_from_result, verification_from_result
from coral.spend import Ledger

log = logging.getLogger(__name__)

# `create_deep_agent` adds a general-purpose subagent of its own unless a harness profile turns it
# off, and that subagent is outside every bound below: its own filesystem middleware keeps the
# framework's 3,600-second shell ceiling, and the elapsed-time check cannot run between steps that
# happen inside a `task` call. Disabled, and with no subagents passed, the `task` tool is not
# exposed at all. The key is the provider, which `ChatOpenRouter` reports as `openrouter`.
register_harness_profile(
    "openrouter",
    HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)),
)

# `ChatOpenRouter` takes its timeout in milliseconds. No real run has come near it: real reviews
# in `kkestell/coral-test` used 14 to 51 messages against the 200-message `STEP_CAP` and a
# verifier run confirming one finding used 9, while the longest single shell command any of them
# ran took 12.2 seconds against the 300-second `SHELL_CEILING_SECONDS`. Both hold as chosen.
MODEL_TIMEOUT_MILLISECONDS: Final = 180_000
STEP_CAP: Final = 200
SHELL_CEILING_SECONDS: Final = 300

# One retry rather than the default two, which is deadline arithmetic. The elapsed check runs
# between steps, so the worst overshoot past a passing check is one in-flight model request. Two
# retries make that up to three 180-second attempts plus a 300-second backoff window — about
# fourteen minutes, past the ten minutes of headroom before the job's own timeout. One makes it
# about eight and a half. No real run has fired a retry.
MODEL_RETRIES: Final = 1


class ContainerBackend(LocalShellBackend):
    """The framework's local backend with its one shell method sent into the container.

    Only `execute` moves. Every file tool is inherited unchanged: they are Coral's own Python over
    `root_dir`, resolving virtual paths under it and refusing traversal, and `root_dir` is the copy
    the container has mounted at `/checkout`. So a scratch file written with `write_file` is
    immediately runnable in the shell, and the other way around.

    A subclass rather than a wrapper around the backend, because the middleware exposes the
    `execute` tool only to a backend passing `isinstance(backend, SandboxBackendProtocol)`.
    """

    def __init__(self, checkout: Path, container_name: str, timeout: int) -> None:
        super().__init__(checkout, timeout=timeout)
        self.container_name = container_name
        self.ceiling = timeout

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        result = container.execute(self.container_name, command, timeout or self.ceiling)
        return ExecuteResponse(
            output=result.output, exit_code=result.exit_code, truncated=result.truncated
        )


class DeadlineMiddleware(AgentMiddleware[Any, Any]):
    """Stops the run when Coral's budget is spent, checked before each model call."""

    def __init__(self, deadline: Deadline) -> None:
        super().__init__()
        self.deadline = deadline

    def before_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        # Raised rather than ended gracefully. A fired deadline is a failure, and a graceful end
        # would arrive as "the agent returned no structured review" with the reason lost. The
        # exception propagates out of `invoke`, where the review step turns it into a comment; the
        # message is the whole of what that comment says the reason was.
        if self.deadline.expired():
            raise RuntimeError(
                f"Coral ran out of time after {self.deadline.elapsed():.0f} seconds, against a "
                f"budget of {self.deadline.budget:.0f}."
            )
        return None


class SpendHandler(BaseCallbackHandler):
    """Adds what each response cost to the ledger.

    A callback rather than a middleware hook, because it is the only place that sees the
    summarization middleware's own model call. That middleware calls the model from its own
    `before_model`, keeps the text, and replaces the message list, so the message carrying that
    call's cost never reaches a state a middleware can read — and those are the largest calls in a
    run. LangChain hands the ambient callbacks the `LLMResult` holding that same message.
    """

    def __init__(self, ledger: Ledger, model: str) -> None:
        self.ledger = ledger
        self.model = model

    def on_llm_end(self, response: LLMResult, **keywords: Any) -> None:
        for generations in response.generations:
            for generation in generations:
                assert isinstance(generation, ChatGeneration), f"{type(generation).__name__}"
                metadata = generation.message.response_metadata
                # Every OpenRouter completion measured carries a cost, with nothing asked for. One
                # that does not is counted rather than passed over: `SpendMiddleware` stops the run
                # at the next check, because a review whose spending Coral cannot measure is one
                # the caller's cap does not hold.
                if "cost" not in metadata:
                    log.warning("A response from %s carried no cost.", self.model)
                    self.ledger.unpriced += 1
                    continue
                self.ledger.add(float(metadata["cost"]))


class SpendMiddleware(AgentMiddleware[Any, Any]):
    """Stops the run when the ledger reaches its cap, checked before each model call."""

    def __init__(self, ledger: Ledger) -> None:
        super().__init__()
        self.ledger = ledger

    def before_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        # A cap Coral cannot measure against is not a cap, so this stops the run too. Only the
        # minted key's own limit would have caught the spending, and a passed-through key has none.
        if self.ledger.unpriced:
            raise RuntimeError(
                f"{self.ledger.unpriced} of this run's responses carried no cost, so Coral cannot "
                f"hold it to its cap of ${self.ledger.cap:.6f}. It had counted "
                f"${self.ledger.spent:.6f} of that."
            )
        # Raised for the same reason `DeadlineMiddleware` raises, and checked in the same place:
        # between steps, so the overshoot past a passing check is one in-flight model request. Six
        # decimal places because a cap of a fraction of a cent has to be legible.
        if self.ledger.exceeded():
            raise RuntimeError(
                f"Coral ran out of money after ${self.ledger.spent:.6f}, against a cap of "
                f"${self.ledger.cap:.6f}."
            )
        return None


def profile_of(facts: ModelFacts) -> ModelProfile:
    """The model profile, built from what OpenRouter's listing says about the model.

    Supplied rather than left to LangChain's own lookup, which has no entry for most OpenRouter ids
    and falls back to summarization triggers scaled to 170,000 tokens rather than the real window.
    `temperature` is false for a model that rejects the parameter outright, which the profile is
    what tells LangChain. No key here decides the structured-output strategy; `_run` names it.
    """
    profile: ModelProfile = {
        "tool_calling": "tools" in facts.parameters,
        "reasoning_output": "reasoning" in facts.parameters,
        "temperature": "temperature" in facts.parameters,
        "max_input_tokens": facts.context_length,
    }
    # Left out rather than guessed for a model whose ceiling the listing does not report. An
    # absent key is what the lookup's own miss looks like, and LangChain reads it the same way.
    if facts.max_completion_tokens is not None:
        profile["max_output_tokens"] = facts.max_completion_tokens
    return profile


def review_prompt() -> str:
    """What Coral looks for, read out of the installed package."""
    return (files("coral") / "prompts" / "review.md").read_text(encoding="utf-8")


def verify_prompt() -> str:
    """How Coral checks a finding, read out of the installed package."""
    return (files("coral") / "prompts" / "verify.md").read_text(encoding="utf-8")


def caught(inner: Callable[..., Any]) -> Callable[..., Any]:
    """A tool function that answers with its own error instead of raising it."""

    @functools.wraps(inner)
    def call(*arguments: Any, **keywords: Any) -> Any:
        start = time.monotonic()
        try:
            return inner(*arguments, **keywords)
        except Exception as error:
            log.info("A tool call failed; handing the error back to the model: %s", error)
            return f"{type(error).__name__}: {error}"
        finally:
            log.info("%s took %.1f seconds.", inner.__name__, time.monotonic() - start)

    # `functools.wraps` copies `__wrapped__`, which is what keeps `inspect.signature` seeing the
    # real parameters. LangChain reads them to decide which arguments to inject.
    return call


def forgiving(middleware: FilesystemMiddleware) -> FilesystemMiddleware:
    """Hand each tool's errors to the model rather than ending the run.

    A path with `..` in it, a file that is not there, a command that will not parse: the model
    wrote the argument and the model is the one who can fix it on the next step. LangChain turns
    only a `ToolException` into an observation and the backend raises `ValueError`, so without
    this one wrong path ends a review with fifteen minutes still on its budget. Observed on a
    real run, where the first `read_file` call used `..` and took the whole review down with it.
    """
    for tool in middleware.tools:
        assert isinstance(tool, StructuredTool), f"{tool.name} is a {type(tool).__name__}"
        assert tool.func is not None, f"{tool.name} has no sync implementation to wrap"
        tool.func = caught(tool.func)
    return middleware


def _run(
    api_key: str,
    name: str,
    effort: str,
    facts: ModelFacts,
    checkout: Path,
    container_name: str,
    request: str,
    deadline: Deadline,
    ledger: Ledger,
    system_prompt: str,
    response_format: type,
) -> dict[str, Any]:
    """Build an agent over its copy of the checkout, run it, and return its result state.

    The one place the model client, the backend, and the middleware are constructed. Both runs
    share every bound here; what differs between them is the prompt and the type they return.
    """
    profile = profile_of(facts)
    log.info("Reviewing on %s with effort %r and the profile %s.", name, effort, profile)
    model = ChatOpenRouter(
        model=name,
        api_key=SecretStr(api_key),
        timeout=MODEL_TIMEOUT_MILLISECONDS,
        max_retries=MODEL_RETRIES,
        # Supplied whole. DeepAgents injects `ignore` only when it resolves a string model, and
        # Coral passes an instance. `require_parameters` is what keeps the request off an endpoint
        # that cannot serve tool calling, which the model profile alone does not decide.
        openrouter_provider={"require_parameters": True, "ignore": ["azure"]},
        profile=profile,
        # OpenRouter's own reasoning block, and the whole of what an effort does. Left out when the
        # caller named none, which leaves the provider applying its own default; a value the
        # provider refuses comes back as the provider's own words.
        reasoning={"effort": effort} if effort else None,
    )
    # The ceiling needs both halves. The middleware rejects a command whose own `timeout` argument
    # overshoots, telling the model the ceiling rather than clamping; the backend bounds the case
    # where the model omits the argument, which is the common one.
    backend = ContainerBackend(checkout, container_name, SHELL_CEILING_SECONDS)
    agent = create_deep_agent(
        model,
        system_prompt=system_prompt,
        # This instance replaces the framework's own rather than joining it, because middleware
        # merges by `AgentMiddleware.name` and that defaults to the class name. An upstream rename
        # would turn replacement into addition, leaving two middlewares each registering
        # `read_file`; `tests/test_agent.py` pins the name against that.
        #
        # The factory builds its own with three arguments: the backend, the harness profile's
        # tool-description overrides, and a private permissions list. For an instance-passed
        # OpenRouter model the harness profile is the empty null object, so both of those are the
        # parameter defaults and mirroring the backend is mirroring everything. A DeepAgents
        # upgrade that ships an `openrouter` harness profile makes that false.
        #
        # A forwarding wrapper around the backend is not an alternative: it fails the framework's
        # `isinstance` check against `SandboxBackendProtocol`.
        middleware=[
            forgiving(
                FilesystemMiddleware(backend=backend, max_execute_timeout=SHELL_CEILING_SECONDS)
            ),
            DeadlineMiddleware(deadline),
            SpendMiddleware(ledger),
        ],
        backend=backend,
        # Named rather than left to the framework's auto-detection, which asks for the provider's
        # own structured output whenever the model's profile carries `structured_output` or its
        # name matches a table of GPT, Claude, and Grok names kept upstream. That request makes the
        # endpoint answer in the schema on its first response, so the model returns a review
        # written from the diff alone, having read no file and run no test. The synthetic tool
        # instead binds every call with `tool_choice="any"`: the model must call a tool at each
        # step and the run ends when it calls the schema tool, which is the agent loop, on every
        # model rather than on the ones a lookup happens to miss.
        response_format=ToolStrategy(response_format),
    )
    # DeepAgents binds a recursion limit of 9,999 through `with_config`; a second `with_config`
    # on the compiled graph overrides it. There is no constructor parameter for it. The handler
    # rides along here because an ambient callback reaches every model call the run makes,
    # including the summarization middleware's own.
    bounded = agent.with_config(
        {"recursion_limit": STEP_CAP, "callbacks": [SpendHandler(ledger, name)]}
    )

    log.info("Running the agent over %s with %.0f seconds of budget.", checkout, deadline.budget)
    result: dict[str, Any] = bounded.invoke({"messages": [HumanMessage(request)]})
    log.info(
        "The agent finished after %.0f seconds and %d messages.",
        deadline.elapsed(),
        len(result["messages"]),
    )
    return result


def produce_review(
    api_key: str,
    name: str,
    effort: str,
    facts: ModelFacts,
    checkout: Path,
    container_name: str,
    request: str,
    deadline: Deadline,
    ledger: Ledger,
) -> Review:
    """Run the reviewer over its copy of the checkout and return the review it produced, or fail."""
    return review_from_result(
        _run(
            api_key,
            name,
            effort,
            facts,
            checkout,
            container_name,
            request,
            deadline,
            ledger,
            review_prompt(),
            Review,
        )
    )


def verify_findings(
    api_key: str,
    name: str,
    effort: str,
    facts: ModelFacts,
    checkout: Path,
    container_name: str,
    request: str,
    deadline: Deadline,
    ledger: Ledger,
) -> Verification:
    """Run the verifier over its own fresh copy of the checkout and return its verdicts, or fail."""
    return verification_from_result(
        _run(
            api_key,
            name,
            effort,
            facts,
            checkout,
            container_name,
            request,
            deadline,
            ledger,
            verify_prompt(),
            Verification,
        )
    )
