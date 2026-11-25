"""The agent: the model client, its one shell tool, the middleware, and the run.

The only module that imports the agent framework. Everything else in Coral depends on the review
object in `coral/schema.py`, which keeps the framework's import cost off `coral resolve` and keeps
the rest of the code testable without it.
"""

import functools
import logging
import time
from collections.abc import Callable, Mapping
from importlib.resources import files
from typing import Any, Final
from uuid import UUID

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.structured_output import ToolStrategy
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.model_profile import ModelProfile
from langchain_core.messages import HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.tools import StructuredTool
from langchain_openrouter import ChatOpenRouter
from langgraph.config import get_config
from langgraph.runtime import Runtime
from pydantic import SecretStr

from coral import container
from coral.deadline import Deadline, stop_if_expired
from coral.openrouter import ModelFacts
from coral.schema import Review, review_from_result
from coral.spend import Ledger, priced, stop_if_over_cap

log = logging.getLogger(__name__)

# `ChatOpenRouter` takes its timeout in milliseconds. A read-only rehearsal of a 210-line Ox change
# on 2026-11-25 used 75 graph steps and 28 shell calls before its five-minute budget made it
# answer; `STEP_CAP` leaves room over that, and the time budget is what normally ends a run.
MODEL_TIMEOUT_MILLISECONDS: Final = 180_000
STEP_CAP: Final = 100
# The graph steps left when a run stops investigating and answers. A model call is three steps
# with the two `before_model` hooks ahead of it, and a structured answer the framework refuses goes
# back through them for another try, so this leaves room for at least three attempts.
FINAL_STEPS: Final = 12
ANSWER_NOTICE: Final = (
    "This run has reached its step or time bound, and the shell is gone. Call the response tool "
    "now with your real, complete result, written from what you have established so far."
)
SHELL_CEILING_SECONDS: Final = 300

# One retry rather than the default two, which is deadline arithmetic. The elapsed check runs
# between steps, so the worst overshoot past a passing check is one in-flight model request. Two
# retries make that up to three 180-second attempts plus a 300-second backoff window — about
# fourteen minutes, past the ten minutes of headroom before the job's own timeout. One makes it
# about eight and a half. No real run has fired a retry.
MODEL_RETRIES: Final = 1
ARGUMENT_PREVIEW_CHARACTERS: Final = 120
TOOL_ARGUMENT_ORDER: Final = {
    "execute": ("command", "timeout"),
}


def execute_tool(container_name: str, deadline: Deadline) -> StructuredTool:
    """The one repository tool an agent receives, bound to its own container."""

    def execute(command: str, timeout: int = SHELL_CEILING_SECONDS) -> str:
        """Run a shell command in /checkout, with an optional timeout in seconds."""
        if not 1 <= timeout <= SHELL_CEILING_SECONDS:
            return f"Error: timeout must be between 1 and {SHELL_CEILING_SECONDS} seconds."
        # Cut to the time left before the answer reserve, so no command runs into it.
        left = int(deadline.working())
        if left < 1:
            return f"Error: no time is left for shell commands. {ANSWER_NOTICE}"
        result = container.execute(container_name, command, min(timeout, left))
        return f"{result.output}\n\n[exit code: {result.exit_code}]"

    return StructuredTool.from_function(caught("execute", execute), name="execute")


class DeadlineMiddleware(AgentMiddleware[Any, Any]):
    """Stops the run when Coral's budget is spent, checked before each model call."""

    def __init__(self, deadline: Deadline) -> None:
        super().__init__()
        self.deadline = deadline

    def before_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        stop_if_expired(self.deadline)
        return None


class AnswerMiddleware(AgentMiddleware[Any, Any]):
    """Makes the model return its structured result once the run nears `STEP_CAP` or its deadline.

    Every tool but the framework's response-format tool is withdrawn, and that tool is always
    bound with `tool_choice="any"`, so the model's only move is to answer. Past either bound the
    run raises instead and has nothing to return.
    """

    def __init__(self, deadline: Deadline) -> None:
        super().__init__()
        self.deadline = deadline

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], ModelResponse[Any]]
    ) -> ModelResponse[Any]:
        # The superstep LangGraph is running, which is what its recursion limit counts.
        steps = STEP_CAP - get_config()["metadata"]["langgraph_step"]
        seconds = self.deadline.budget - self.deadline.elapsed()
        if steps > FINAL_STEPS and self.deadline.working() > 0:
            return handler(request)
        log.info(
            "The run has %d steps and %.0f seconds left; asking for its result.", steps, seconds
        )
        # A user turn rather than a system-prompt addition, because it is the latest thing the
        # model reads before it answers.
        return handler(
            request.override(tools=[], messages=[*request.messages, HumanMessage(ANSWER_NOTICE)])
        )


class SpendHandler(BaseCallbackHandler):
    """Adds what each response cost to the ledger.

    A callback rather than a middleware hook because LangChain hands it the `LLMResult` carrying
    provider response metadata directly. No message-state convention sits between the reported
    amount and Coral's ledger.
    """

    def __init__(self, ledger: Ledger, model: str) -> None:
        self.ledger = ledger
        self.model = model

    def on_llm_end(self, response: LLMResult, **keywords: Any) -> None:
        for generations in response.generations:
            for generation in generations:
                assert isinstance(generation, ChatGeneration), f"{type(generation).__name__}"
                metadata = generation.message.response_metadata
                # Every OpenRouter completion measured carries a usable cost, with nothing asked
                # for. One that does not is counted rather than passed over: the next limit check
                # stops the run, because a review whose spending Coral cannot measure is one the
                # caller's cap does not hold.
                cost = priced(metadata.get("cost"))
                if cost is None:
                    log.warning(
                        "A response from %s carried no cost Coral can add: %r.",
                        self.model,
                        metadata.get("cost"),
                    )
                    self.ledger.unpriced += 1
                    continue
                self.ledger.add(cost)


def _escaped_repr(value: object) -> str:
    """Render one value without making a second log line."""
    return repr(value).replace("\r", "\\r").replace("\n", "\\n")


def format_tool_arguments(name: str, inputs: Mapping[str, Any]) -> str:
    """Render the model-supplied arguments for one public tool call."""
    allowed = {key: value for key, value in inputs.items() if key != "runtime"}
    order = TOOL_ARGUMENT_ORDER.get(name, ())
    keys = [key for key in order if key in allowed]
    keys.extend(sorted(key for key in allowed if key not in order))
    rendered = []
    for key in keys:
        value = allowed[key]
        if isinstance(value, str) and len(value) > ARGUMENT_PREVIEW_CHARACTERS:
            preview = _escaped_repr(value[:ARGUMENT_PREVIEW_CHARACTERS])
            rendered.append(f"{key}={preview}... ({len(value)} characters)")
        else:
            rendered.append(f"{key}={_escaped_repr(value)}")
    return ", ".join(rendered)


class ToolProgressHandler(BaseCallbackHandler):
    """Logs each agent tool call without logging its result."""

    def __init__(self) -> None:
        self.calls: dict[UUID, tuple[str, float]] = {}

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        inputs: dict[str, Any] | None = None,
        **keywords: Any,
    ) -> None:
        name = str(serialized["name"])
        self.calls[run_id] = (name, time.monotonic())
        log.info("Calling %s(%s).", name, format_tool_arguments(name, inputs or {}))

    def on_tool_end(self, output: Any, *, run_id: UUID, **keywords: Any) -> None:
        call = self.calls.pop(run_id, None)
        if call is None:
            return
        name, started = call
        log.info("%s finished in %.1f seconds.", name, time.monotonic() - started)

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **keywords: Any) -> None:
        call = self.calls.pop(run_id, None)
        if call is None:
            return
        name, started = call
        log.info("%s failed in %.1f seconds: %s", name, time.monotonic() - started, error)


class SpendMiddleware(AgentMiddleware[Any, Any]):
    """Stops the run when the ledger reaches its cap, checked before each model call."""

    def __init__(self, ledger: Ledger) -> None:
        super().__init__()
        self.ledger = ledger

    def before_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        stop_if_over_cap(self.ledger)
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


def prompt(name: str) -> str:
    """One of Coral's prompts, read out of the installed package."""
    return (files("coral") / "prompts" / f"{name}.md").read_text(encoding="utf-8")


def guided(system_prompt: str, instructions: str) -> str:
    """A system prompt followed by the repository owner's guidance, when the caller gave any."""
    if not instructions.strip():
        return system_prompt
    return f"{system_prompt}\n{prompt('guidance')}{instructions.strip()}\n"


def review_prompt(instructions: str = "") -> str:
    """What Coral looks for, with the repository owner's guidance."""
    return guided(prompt("review"), instructions)


def caught(name: str, inner: Callable[..., Any]) -> Callable[..., Any]:
    """A tool function that answers with its own error instead of raising it."""

    @functools.wraps(inner)
    def call(*arguments: Any, **keywords: Any) -> Any:
        try:
            return inner(*arguments, **keywords)
        except Exception as error:
            log.info("%s failed; handing the error back to the model: %s", name, error)
            return f"{type(error).__name__}: {error}"

    # `functools.wraps` copies `__wrapped__`, which is what keeps `inspect.signature` seeing the
    # real parameters. LangChain reads them to decide which arguments to inject.
    return call


def _run(
    api_key: str,
    name: str,
    effort: str,
    facts: ModelFacts,
    container_name: str,
    request: str,
    deadline: Deadline,
    ledger: Ledger,
    system_prompt: str,
    response_format: type[Any],
) -> dict[str, Any]:
    """Build an agent over its container, run it, and return its result state.

    The one place the model client, the backend, and the middleware are constructed.
    """
    profile = profile_of(facts)
    log.info("Reviewing on %s with effort %r and the profile %s.", name, effort, profile)
    model = ChatOpenRouter(
        model=name,
        api_key=SecretStr(api_key),
        timeout=MODEL_TIMEOUT_MILLISECONDS,
        max_retries=MODEL_RETRIES,
        # `require_parameters` keeps the request off an endpoint that cannot serve tool calling.
        # Azure is excluded because its OpenRouter route has not accepted the same tool requests.
        openrouter_provider={"require_parameters": True, "ignore": ["azure"]},
        profile=profile,
        # OpenRouter's own reasoning block, and the whole of what an effort does. Left out when the
        # caller named none, which leaves the provider applying its own default; a value the
        # provider refuses comes back as the provider's own words.
        reasoning={"effort": effort} if effort else None,
    )
    # The tool validates an explicit timeout and supplies the same ceiling when the model omits it.
    agent = create_agent(
        model=model,
        system_prompt=system_prompt,
        middleware=[
            DeadlineMiddleware(deadline),
            SpendMiddleware(ledger),
            AnswerMiddleware(deadline),
        ],
        tools=[execute_tool(container_name, deadline)],
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
    # The recursion limit is the step cap because the graph has no constructor parameter for it.
    # The callbacks ride along here so they reach every model and tool call in the run.
    bounded = agent.with_config(
        {
            "recursion_limit": STEP_CAP,
            "callbacks": [SpendHandler(ledger, name), ToolProgressHandler()],
        }
    )

    log.info(
        "Running the agent in %s with %.0f seconds of budget.", container_name, deadline.budget
    )
    result: dict[str, Any] = bounded.invoke({"messages": [HumanMessage(request)]})
    log.info(
        "The agent finished after %.0f seconds and %d messages.",
        deadline.elapsed(),
        len(result["messages"]),
    )
    # The middleware checks before each model call, so the last response of a run has passed no
    # check at all: a final request can run past the budget or over the cap and still return an
    # answer. Checked once more here, that answer fails the run rather than being reviewed on.
    stop_if_expired(deadline)
    stop_if_over_cap(ledger)
    return result


def produce_review(
    api_key: str,
    name: str,
    effort: str,
    instructions: str,
    facts: ModelFacts,
    container_name: str,
    request: str,
    deadline: Deadline,
    ledger: Ledger,
) -> Review:
    """Run the agent over its copy of the checkout and return the review it produced, or fail."""
    return review_from_result(
        _run(
            api_key,
            name,
            effort,
            facts,
            container_name,
            request,
            deadline,
            ledger,
            review_prompt(instructions),
            Review,
        )
    )
