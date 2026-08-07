"""The agent: the model client, the backend, the middleware, and the two runs.

The only module that imports the agent framework. Everything else in Coral depends on the review
object in `coral/schema.py` and never on DeepAgents, which is what keeps the framework's two
seconds of import off `coral resolve` and keeps the rest of the code testable without it.
"""

import logging
import os
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
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.model_profile import ModelProfile
from langchain_core.messages import HumanMessage
from langchain_openrouter import ChatOpenRouter
from langgraph.runtime import Runtime
from pydantic import SecretStr

from coral.deadline import Deadline
from coral.environment import shell_environment
from coral.schema import Review, Verification, review_from_result, verification_from_result

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

MODEL: Final = "~deepseek/deepseek-v4-flash-latest"

# Copied by hand from `langchain-openrouter`'s bundled table entry for the concrete release
# `deepseek/deepseek-v4-flash`. The table is looked up by exact name, so the alias above misses it,
# and a model with no profile gets summarization triggers scaled to 170,000 tokens rather than the
# real million.
#
# `structured_output` is deliberately absent, though the real entry carries it. LangChain reads
# that key to pick a native structured-output request over a synthetic tool, and the native request
# makes the endpoint answer in the schema on its first response — so the model returns a review
# written from the diff alone, having called no tool, and sometimes a summary of "...". Omitting the
# key buys the synthetic tool instead, and with it the agent loop: observed five model calls and a
# finding anchored to the right line where the native request managed one call and no anchor.
MODEL_PROFILE: Final[ModelProfile] = {
    "tool_calling": True,
    "reasoning_output": True,
    "max_input_tokens": 1_048_576,
    "max_output_tokens": 65_536,
}

# All chosen rather than measured; item 9 on the roadmap settles them. `ChatOpenRouter` takes its
# timeout in milliseconds.
MODEL_TIMEOUT_MILLISECONDS: Final = 180_000
STEP_CAP: Final = 200
SHELL_CEILING_SECONDS: Final = 300

# One retry rather than the default two, which is deadline arithmetic. The elapsed check runs
# between steps, so the worst overshoot past a passing check is one in-flight model request. Two
# retries make that up to three 180-second attempts plus a 300-second backoff window — about
# fourteen minutes, past the ten minutes of headroom before the job's own timeout. One makes it
# about eight and a half.
MODEL_RETRIES: Final = 1


class DeadlineMiddleware(AgentMiddleware[Any, Any]):
    """Stops the run when Coral's budget is spent, checked before each model call."""

    def __init__(self, deadline: Deadline) -> None:
        super().__init__()
        self.deadline = deadline

    def before_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        # Raised rather than ended gracefully. A fired deadline is a failure, and a graceful end
        # would arrive as "the agent returned no structured review" with the reason lost. The
        # exception propagates out of `invoke`; item 8 on the roadmap turns it into a comment.
        if self.deadline.expired():
            raise RuntimeError(
                f"Coral ran out of time after {self.deadline.elapsed():.0f} seconds, against a "
                f"budget of {self.deadline.budget:.0f}. No review was posted."
            )
        return None


def review_prompt() -> str:
    """What Coral looks for, read out of the installed package."""
    return (files("coral") / "prompts" / "review.md").read_text(encoding="utf-8")


def verify_prompt() -> str:
    """How Coral checks a finding, read out of the installed package."""
    return (files("coral") / "prompts" / "verify.md").read_text(encoding="utf-8")


def _run(
    api_key: str,
    workspace: Path,
    request: str,
    deadline: Deadline,
    system_prompt: str,
    response_format: type,
) -> dict[str, Any]:
    """Build an agent over the checkout, run it, and return its result state.

    The one place the model client, the backend, and the middleware are constructed. Both runs
    share every bound here; what differs between them is the prompt and the type they return.
    """
    model = ChatOpenRouter(
        model=MODEL,
        api_key=SecretStr(api_key),
        timeout=MODEL_TIMEOUT_MILLISECONDS,
        max_retries=MODEL_RETRIES,
        # Supplied whole. DeepAgents injects `ignore` only when it resolves a string model, and
        # Coral passes an instance. `require_parameters` is what keeps the request off an endpoint
        # that cannot serve tool calling, which the model profile alone does not decide.
        openrouter_provider={"require_parameters": True, "ignore": ["azure"]},
        profile=MODEL_PROFILE,
    )
    # The ceiling needs both halves. The middleware rejects a command whose own `timeout` argument
    # overshoots, telling the model the ceiling rather than clamping; the backend bounds the case
    # where the model omits the argument, which is the common one.
    backend = LocalShellBackend(
        workspace, timeout=SHELL_CEILING_SECONDS, env=shell_environment(os.environ)
    )
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
            FilesystemMiddleware(backend=backend, max_execute_timeout=SHELL_CEILING_SECONDS),
            DeadlineMiddleware(deadline),
        ],
        backend=backend,
        response_format=response_format,
    )
    # DeepAgents binds a recursion limit of 9,999 through `with_config`; a second `with_config`
    # on the compiled graph overrides it. There is no constructor parameter for it.
    bounded = agent.with_config({"recursion_limit": STEP_CAP})

    log.info("Running the agent over %s with %.0f seconds of budget.", workspace, deadline.budget)
    result: dict[str, Any] = bounded.invoke({"messages": [HumanMessage(request)]})
    log.info("The agent finished after %.0f seconds.", deadline.elapsed())
    return result


def produce_review(api_key: str, workspace: Path, request: str, deadline: Deadline) -> Review:
    """Run the reviewer over the checkout and return the review it produced, or fail."""
    return review_from_result(_run(api_key, workspace, request, deadline, review_prompt(), Review))


def verify_findings(
    api_key: str, workspace: Path, request: str, deadline: Deadline
) -> Verification:
    """Run the verifier over the reset checkout and return its verdicts, or fail."""
    return verification_from_result(
        _run(api_key, workspace, request, deadline, verify_prompt(), Verification)
    )
