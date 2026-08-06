# DeepAgents Control Points

Status: Living document (last updated 2026-08-06)

## Question

An application that embeds an agent framework inherits the framework's runtime limits. Some of those limits the application can set. Others the framework sets for it, at construction time, using parameters the public factory function does not expose. The question this document answers is which is which, in DeepAgents specifically, and what applications do when they need a limit the factory does not offer.

A second question rides along with it, because in this stack the two are entangled. When the model is reached through a router rather than a provider, the capability the framework relies on — tool calling, structured output, a reasoning setting — is a property of whichever upstream provider serves the request, not of the model name in the request. So: where does a capability guarantee stop being a guarantee?

Everything below was read at a specific version. DeepAgents was read at `0.7.4`. LangChain, LangGraph, and `langchain-openrouter` were read at the commits recorded under Sources. The OpenRouter model catalogue and models.dev were queried on 2026-08-06.

## Summary

DeepAgents assembles its middleware stack inside `create_deep_agent` and does not expose the middleware constructors' parameters. The important consequence is that four separate limits — the shell timeout ceiling, the summarization thresholds, the filesystem tool allowlist, and the grep match cap — all live on middleware the factory builds itself. None of them appear in the factory's signature.

The factory does, however, let a caller pass replacement middleware. Middleware supplied through the `middleware=` argument is merged into the assembled stack by name, and a name collision replaces the framework's instance in place rather than adding a second one. Because `AgentMiddleware.name` defaults to the class name, passing `FilesystemMiddleware(backend=..., max_execute_timeout=300)` replaces the framework's own `FilesystemMiddleware` and keeps its position in the stack. This is the seam through which every middleware-level limit is reachable, and it is covered by the framework's own tests.

The step budget is reachable a different way. The compiled graph carries a bound `recursion_limit` of 9,999, set by `create_deep_agent` at the end of construction. A config passed at invocation time overrides it, because LangGraph merges the bound config with the invocation config and the invocation config wins for scalar keys.

Applications in the wild split four ways on how they take control: configure the framework's own middleware, wrap or subclass the backend, copy the middleware wholesale into the application, or accept the defaults. The four differ mostly in what the model is told. Rejecting an over-long timeout at the middleware tells the model its request was refused and what the maximum is. Clamping it inside a backend does not, so the model believes it received the hour it asked for.

On the provider layer, the router alias `~deepseek/deepseek-v4-flash-latest` exists and advertises the capabilities the design depends on, but its endpoint list is empty, so which upstream providers serve it cannot be read from the API. The concrete release it currently redirects to lists 22 endpoints, and several of those do not support structured outputs. A model-level capability list on a router is a union across providers, not a promise about any one of them.

## What the framework decides, and what it hands over

### The factory's surface

`create_deep_agent` accepts eighteen parameters (`deepagents/graph.py:268-288`). Relevant ones are `model`, `tools`, `system_prompt`, `middleware`, `subagents`, `permissions`, `backend`, `interrupt_on`, `response_format`, `state_schema`, `checkpointer`, and `store`. There is no `max_execute_timeout`, no `recursion_limit`, and no summarization configuration.

`response_format` is present (`deepagents/graph.py:280`) and is forwarded unchanged to `create_agent` (`deepagents/graph.py:927`). Its type is `ResponseFormat[ResponseT] | type[ResponseT] | dict[str, Any] | None`, so a bare Pydantic model class is accepted as well as an explicit strategy object.

### Middleware assembly

The main agent's stack is built as a list in one function body. Order is: `SkillsMiddleware` when `skills` was passed, then `FilesystemMiddleware`, then `SubAgentMiddleware` when there are inline subagents, then summarization middleware, then `PatchToolCallsMiddleware` (`deepagents/graph.py:817-846`). A tail follows: harness-profile middleware, prompt-caching middleware, `MemoryMiddleware` when `memory` was passed, and `HumanInTheLoopMiddleware` when interrupts are configured (`deepagents/graph.py:855-876`).

`FilesystemMiddleware` is constructed with exactly three arguments — the backend, the profile's tool-description overrides, and the private permissions list (`deepagents/graph.py:820-826`). Every other parameter on that middleware takes its default. Summarization middleware is built unconditionally by a factory that takes the model and the backend (`deepagents/graph.py:843`).

Caller-supplied middleware is merged by `_apply_custom_middleware` (`deepagents/graph.py:201-235`). Each entry whose `.name` already exists in the stack replaces that entry at its existing index. Each entry whose name is new is spliced in after the last core entry, ahead of the tail. `AgentMiddleware.name` is a property returning `self.__class__.__name__` unless overridden (`langchain/agents/middleware/types.py:411-417`), so an instance of `FilesystemMiddleware` collides with the framework's own instance and takes its place.

The framework tests this behavior directly. `tests/unit_tests/test_graph.py:2550` opens a test class whose docstring is "Integration tests: user-supplied middleware replaces same-named defaults in create_deep_agent", and `test_summarization_middleware_replaces_default` at line 2581 asserts that exactly one summarization middleware survives and that it is the caller's instance.

Replacement also reaches the automatically added general-purpose subagent. That subagent gets its own stack containing its own `FilesystemMiddleware` (`deepagents/graph.py:752-760`), and caller middleware whose name matches one of that stack's default slots is inherited into it (`deepagents/graph.py:777-778`, tested at `tests/unit_tests/test_graph.py:2759`). Caller middleware whose name matches nothing in the subagent's defaults stays on the main agent only.

Two middleware classes cannot be removed at all. `FilesystemMiddleware` and `SubAgentMiddleware` are listed as required scaffolding, and excluding either raises `ValueError` (`deepagents/graph.py:238-253`). Replacing them by name is a different operation and is allowed.

### The shell timeout

There are three separate numbers, at three layers, and only one of them is a ceiling.

`LocalShellBackend.__init__` takes `timeout`, defaulting to `DEFAULT_EXECUTE_TIMEOUT`, which is 120 seconds (`deepagents/backends/local_shell.py:22`, `:112`). It is stored as `self._default_timeout` (`:192`) and used only when the caller of `execute` omits its own: `effective_timeout = timeout if timeout is not None else self._default_timeout` (`:297`). So a backend-level `timeout` is a default and never a ceiling, and the docstring says so (`:151-158`).

`FilesystemMiddleware.__init__` takes `max_execute_timeout`, defaulting to 3600 (`deepagents/middleware/filesystem.py:1606`). The docstring states the default is one hour and that any per-command timeout above it is rejected with an error message (`:1621-1626`). Values must be positive (`:1652-1654`).

The enforcement is a rejection, not a clamp. The `execute` tool checks `timeout > self._max_execute_timeout` and returns a `ToolMessage` with `status="error"` reading `Error: timeout {timeout}s exceeds maximum allowed ({max}s).` (`deepagents/middleware/filesystem.py:2812-2826`, and the same check in the async path at `:2901-2913`). The command does not run. The model is told the number it may not exceed.

The tool's own argument schema tells the model that `0` disables the timeout: "Optional timeout in seconds for this command. Overrides the default timeout. Use 0 for no-timeout execution on backends that support it." (`deepagents/middleware/filesystem.py:1198-1200`). The prompt fragment repeats it (`:1297`). On `LocalShellBackend` that is not true. The middleware's guard only rejects negatives and values above the ceiling, so `0` passes, and then the backend raises `ValueError("timeout must be positive, got 0")` (`deepagents/backends/local_shell.py:298-300`), which the middleware turns into `Error: Invalid parameter.` (`deepagents/middleware/filesystem.py:2875-2882`). A model following the tool description spends a step discovering this.

`LocalShellBackend.execute` runs `subprocess.run` with `shell=True`, `stdin=subprocess.DEVNULL`, `capture_output=True`, and the resolved timeout (`deepagents/backends/local_shell.py:303-313`). A timeout returns exit code 124 with a message rather than raising (`:344-353`).

### The environment the shell inherits

`LocalShellBackend` does not inherit the parent environment by default. `inherit_env` defaults to `False`, and with `env=None` the backend's environment is the empty dict (`deepagents/backends/local_shell.py:114-115`, `:196-201`). `subprocess.run` is then called with `env=self._env` (`:311`). An application that wants the runner's toolchain on `PATH` has to pass `inherit_env=True` and override the variables it wants gone, or build the environment explicitly.

### The step budget

`create_deep_agent` ends by binding a config onto the compiled graph: `.with_config({"recursion_limit": 9_999, "metadata": {...}})` (`deepagents/graph.py:935-944`).

Two default values matter here and they are not the same. LangChain Core's `DEFAULT_RECURSION_LIMIT` is 25 (`langchain_core/runnables/config.py:171`). LangGraph carries its own, read from the environment: `DEFAULT_RECURSION_LIMIT = int(getenv("LANGGRAPH_DEFAULT_RECURSION_LIMIT", "10007"))` (`langgraph/_internal/_config.py:32`). A compiled LangGraph agent that nobody configures therefore runs to 10,007 supersteps, and DeepAgents' 9,999 is eight steps below that rather than far above a sane baseline.

An invocation-time config overrides the bound one. `Pregel.with_config` merges into a copy of the graph's config (`langgraph/pregel/main.py:927-931`), and the streaming entry point resolves the effective config as `ensure_config(self.config, config)` (`langgraph/pregel/main.py:3163`, and the sync path at `:2750`). LangGraph's `ensure_config` takes several configs and, for a scalar key such as `recursion_limit`, the last non-empty value wins (`langgraph/_internal/_config.py:322`, assignment at `:406`). So passing `config={"recursion_limit": 200}` to `invoke` or `ainvoke` yields 200.

`merge_configs` in both libraries treats the default value as "unset" and will not let it override anything: `if config["recursion_limit"] != DEFAULT_RECURSION_LIMIT` (`langchain_core/runnables/config.py:487-489`, and `langgraph/_internal/_config.py:184-186`). That guard exists because `ensure_config` fills the key in on every config it touches. It means the one value that cannot be requested through a `merge_configs` path is the default itself.

A superstep count is what is bounded, not a tool call or a model call. Exhausting it raises `GraphRecursionError` (`langgraph/pregel/main.py:3005-3011` and `:3486-3492`), which subclasses `RecursionError` (`langgraph/errors.py:67`). A limit below 1 raises `ValueError` at run time (`langgraph/pregel/main.py:2563-2564`).

### Summarization

Summarization middleware is installed unconditionally, for the main agent, for the general-purpose subagent, and for every declarative subagent (`deepagents/graph.py:673`, `:758`, `:843`).

Its thresholds are chosen from the model's profile. `compute_summarization_defaults` checks whether `model.profile` is a dict carrying an integer `max_input_tokens`. When it is, the trigger is 85% of the input budget and 10% of messages are kept (`deepagents/middleware/summarization.py:260-275`). When it is not, the fallback is a fixed 170,000-token trigger keeping six messages (`:279-286`). For a model whose profile reports a 1,048,576-token input budget, compaction fires at roughly 891,000 tokens.

The DeepAgents subclass reports itself under the public name. `_DeepAgentsSummarizationMiddleware.name` returns the string `"SummarizationMiddleware"` for the exact class, falling back to the real class name for subclasses (`deepagents/middleware/summarization.py:487-505`). That is what makes both string-form exclusion and name-collision replacement target it.

Unlike LangChain's own summarization middleware, this one offloads evicted messages to `/conversation_history/{thread_id}.md` on the backend before replacing them, and embeds that path in the summary so the agent can read it back (`deepagents/middleware/summarization.py:1618-1623`).

### The backend protocol

`BackendProtocol` is an `abc.ABC` with no abstract methods, so a subclass may implement a subset and inherit `NotImplementedError` for the rest (`deepagents/backends/protocol.py:377-378`). It declares `ls`, `read`, `grep`, `glob`, `write`, `edit`, `delete`, `upload_files`, `download_files`, and an async variant of each, most of which default to `asyncio.to_thread` over the sync form.

Its docstring is explicit that the file operations are not sugar over a shell: they enforce literal-only matching rather than regex, return structured result objects, support a match cap, and carry filesystem permission rules, none of which raw `execute` provides (`deepagents/backends/protocol.py:384-396`).

`SandboxBackendProtocol` extends it with an `id` property and `execute`/`aexecute` (`deepagents/backends/protocol.py:814-869`). Despite the name it is an ordinary class, not a `typing.Protocol`, and the framework detects execution support with `isinstance(backend, SandboxBackendProtocol)` (`deepagents/middleware/filesystem.py:1421-1440`). A wrapper that holds a backend and forwards attribute access is therefore invisible to that check; taking over `execute` means subclassing.

Whether the `execute` tool offers a `timeout` argument at all is decided by signature inspection. `execute_accepts_timeout` reads `inspect.signature(cls.execute)` and looks for a `timeout` parameter, caching per class (`deepagents/backends/protocol.py:890-910`). When a model passes a timeout to a backend whose `execute` lacks the parameter, the tool returns `Error: This sandbox backend does not support per-command timeout overrides. Update your sandbox package to the latest version, or omit the timeout parameter.` (`deepagents/middleware/filesystem.py:2846-2856`).

`LocalShellBackend` subclasses both `FilesystemBackend` and `SandboxBackendProtocol` (`deepagents/backends/local_shell.py:26`), so its file operations are direct Python and its `execute` is a subprocess. `virtual_mode` defaults to `True`, which maps agent paths under `root_dir` and blocks traversal for file operations only; the class docstring says four times that it does not restrict shell commands (`deepagents/backends/local_shell.py:111`, `:127-149`).

One combination is refused outright. Passing `permissions` alongside a backend that supports execution raises `NotImplementedError`, because tool-level permissions for the `execute` tool do not exist (`deepagents/middleware/filesystem.py:1667-1674`).

`FilesystemMiddleware` also takes a `tools` allowlist of filesystem tool names, with `read_file` mandatory in any explicit list (`deepagents/middleware/filesystem.py:1608`, `:1649-1651`), and a `grep_max_count` defaulting to 1000 (`:1607`).

### Structured output

`response_format` reaches `create_agent`, which normalizes it. A raw schema is wrapped in `AutoStrategy` (`langchain/agents/factory.py:997-998`), and `AutoStrategy` is resolved per request: when `_supports_provider_strategy` returns true the request uses `ProviderStrategy`, otherwise `ToolStrategy` (`langchain/agents/factory.py:1339-1343`).

`_supports_provider_strategy` reads `model.profile` and returns true when the profile reports `structured_output`, with a carve-out for pre-3-series Gemini models that cannot combine structured output with tools (`langchain/agents/factory.py:536-581`). Failing that it falls back to a regex over known model names.

The result lands on the graph state under `structured_response`, and it is `NotRequired` — optional (`langchain/agents/middleware/types.py:352`). When the model produces an ordinary message instead, the key is explicitly set to `None` (`langchain/agents/factory.py:219-222`). An application reading it has to handle absence.

`ToolStrategy` raises `MultipleStructuredOutputsError` when the model calls more than one output tool and `StructuredOutputValidationError` when the arguments fail validation (`langchain/agents/structured_output.py:41-75`).

## Claims checked against source

Each row is a claim from `.agents/docs/technical-requirements.md` and what the source says. Nothing here decides what to do about a mismatch.

- **`max_execute_timeout` lives on `FilesystemMiddleware` and defaults to 3,600 seconds** (TR-52). Holds. `deepagents/middleware/filesystem.py:1606`.
- **`create_deep_agent` neither accepts nor forwards `max_execute_timeout`** (TR-52). Holds as stated, and is not the whole picture. The factory's signature has no such parameter (`deepagents/graph.py:268-288`) and it builds `FilesystemMiddleware` with three arguments (`:820-826`). A caller-supplied `FilesystemMiddleware` carrying the parameter replaces that instance by name, in the main stack and in the general-purpose subagent's stack (`:883`, `:777-778`, tested at `tests/unit_tests/test_graph.py:2550-2593`).
- **`LocalShellBackend(timeout=...)` sets only a default** (TR-52). Holds. `deepagents/backends/local_shell.py:297`.
- **The ceiling clamps** (TR-52). Does not hold. The middleware rejects the tool call and reports the maximum to the model; it does not lower the value and proceed (`deepagents/middleware/filesystem.py:2812-2826`).
- **A wrapper around the backend can take over `execute`** (TR-52). Holds only for a subclass. Execution support is an `isinstance` check against `SandboxBackendProtocol` (`deepagents/middleware/filesystem.py:1440`), and whether the tool exposes a `timeout` argument is decided by inspecting the class's `execute` signature (`deepagents/backends/protocol.py:890-910`).
- **DeepAgents sets `recursion_limit` to 9,999** (TR-51). Holds. `deepagents/graph.py:937`. The number is eight below LangGraph's own default of 10,007 (`langgraph/_internal/_config.py:32`), not far above a default of 25.
- **`recursion_limit` can be overridden on the compiled graph** (TR-51). Holds, at invocation time. `langgraph/pregel/main.py:3163` merges the graph's bound config with the invocation config, last scalar wins (`langgraph/_internal/_config.py:406`).
- **Summarization middleware is installed by default** (TR-41). Holds, unconditionally, for the main agent and every subagent (`deepagents/graph.py:673`, `:758`, `:843`). Its trigger is 85% of the model profile's `max_input_tokens` when that profile exists (`deepagents/middleware/summarization.py:260-275`), which is about 891,000 tokens for a 1,048,576-token budget.
- **`response_format` is a parameter on `create_deep_agent`** (TR-39). Holds. `deepagents/graph.py:280`, forwarded at `:927`. The object arrives under the `structured_response` state key, which is optional and is set to `None` when the model answers with prose (`langchain/agents/factory.py:219-222`).
- **Filesystem operations and shell execution both come from one backend object** (TR-35). Holds. `FilesystemMiddleware` holds a single `self.backend` and every tool routes through it; `SandboxBackendProtocol` extends `BackendProtocol` rather than sitting beside it (`deepagents/backends/protocol.py:814`).
- **The backend is a single swappable dependency** (TR-35, TR-37). Holds with three qualifications. `SkillsMiddleware`, `MemoryMiddleware`, `SubAgentMiddleware`, and the summarization middleware each receive the same backend instance (`deepagents/graph.py:819`, `:829`, `:843`, `:865`), so a replacement `FilesystemMiddleware` must be given the same instance or two notions of the checkout exist. `LocalShellBackend`'s `virtual_mode` bounds file operations and not shell commands (`deepagents/backends/local_shell.py:127-149`). And `permissions` cannot be combined with an execution-capable backend at all (`deepagents/middleware/filesystem.py:1667-1674`).
- **`langchain-openrouter` exists and provides `ChatOpenRouter`** (TR-6). Holds. Version 0.2.7 on PyPI, source in the LangChain monorepo at `libs/partners/openrouter`, class defined at `langchain_openrouter/chat_models.py:104`. It depends on the `openrouter` SDK rather than on `langchain-openai`. DeepAgents itself enforces a floor of 0.2.0 when resolving an OpenRouter model spec (`deepagents/profiles/provider/_openrouter.py:27`, `:89-119`).
- **`ChatOpenRouter` takes `timeout` in milliseconds** (TR-51). Holds. The field is `request_timeout: int | None = Field(default=None, alias="timeout")` with the docstring "Timeout for requests in milliseconds. Maps to SDK `timeout_ms`." (`langchain_openrouter/chat_models.py:221-222`), passed through as `client_kwargs["timeout_ms"]` (`:453-454`).
- **`openrouter_provider` is a kwarg on `ChatOpenRouter`** (TR-40). Holds. `openrouter_provider: dict[str, Any] | None = None` (`langchain_openrouter/chat_models.py:305`), placed into the request body as `params["provider"]` (`:791-792`).
- **`~deepseek/deepseek-v4-flash-latest` exists and offers a 1,048,576-token window with tool calling, structured outputs, and reasoning effort** (TR-7). Holds at the model level. OpenRouter returns it with `context_length` 1048576, `max_completion_tokens` 65536, and `supported_parameters` including `tools`, `tool_choice`, `structured_outputs`, `response_format`, `reasoning`, and `reasoning_effort`. Its description reads "This model always redirects to the latest model in the DeepSeek V4 Flash family." Its tokenizer is reported as `Router`. models.dev agrees, and `langchain-openrouter` ships a matching profile keyed with the tilde (`langchain_openrouter/data/_profiles.py:7373-7393`) reporting `tool_calling: True`, `structured_output: True`, `reasoning_output: True`, and `max_input_tokens: 1048576`.
- **Roughly thirty providers serve this model** (TR-40). Does not hold as stated for the alias. `GET /api/v1/models/~deepseek/deepseek-v4-flash-latest/endpoints` returns an empty `endpoints` array, so the alias's provider set is not readable from the API. The concrete release it currently redirects to, `deepseek/deepseek-v4-flash-0731`, returns 22 endpoints.

## How the field splits

Four approaches to bounding an embedded DeepAgents agent, described neutrally.

### Approach A — Configure the framework's own middleware

- **What it is:** construct the framework's middleware class with the parameters you need and pass it through `middleware=`, letting name collision replace the framework's instance.
- **Exemplified by:** `deepagents/graph.py:201-235` is the mechanism; `tests/unit_tests/test_graph.py:2550-2593` is the framework's own test of it.
- **Tradeoffs its authors accepted:** the caller now owns arguments the framework used to pass, including the backend, the profile's tool-description overrides, and the private permissions list. Miss one and behavior changes silently — a replacement `FilesystemMiddleware` built without `custom_tool_descriptions` drops whatever the active harness profile was rewriting.
- **Failure mode:** the collision is by string. Renaming the framework class, or a version that stops naming the middleware what it names it today, turns the replacement into an addition. Two `FilesystemMiddleware` instances in one stack both register a `read_file` tool.

### Approach B — Subclass or wrap the backend

- **What it is:** put the limit in the object that runs the command rather than in the middleware that validates the request.
- **Exemplified by:** `amelia/drivers/api/deepagents.py:55-127`, a `LocalSandbox` that subclasses `FilesystemBackend` and `SandboxBackendProtocol` and hardcodes a 300-second timeout inside its own `execute`.
- **Tradeoffs its authors accepted:** the cap is unconditional and needs no cooperation from the middleware. The class comment records why the explicit protocol inheritance is there: `SandboxBackendProtocol` is not runtime-checkable, so `isinstance` would fail without it (`amelia/drivers/api/deepagents.py:58-61`).
- **Failure mode:** the model is not told. A request for 3,600 seconds that is silently served as 300 looks to the model like a command that failed on its merits. Worse, amelia's `execute(self, command)` omits the `timeout` parameter entirely, so `execute_accepts_timeout` reports false (`deepagents/backends/protocol.py:890-910`) and every model request carrying a timeout is refused with a message telling the model to upgrade its sandbox package — advice no model can act on. The per-command timeout feature is gone and the fixed 300 seconds is all there is.

### Approach C — Copy the middleware into the application

- **What it is:** vendor `FilesystemMiddleware` into your own tree and edit it.
- **Exemplified by:** `ferqx/sandbox-agent`, `graphs/build_app_agent_v3/patch_filesystem_middleware.py`, a 2,280-line replacement declaring its own `max_execute_timeout: int = 3_600` at line 395. Also `SSAFY14-D103/AIG`, `AI/app/agent/personal/factory/deep_agent_factory.py`, a 1,131-line replacement that renames the parameter `max_execute_timeout_sec` and defaults it to a module constant `MAX_EXECUTE_TIMEOUT_SEC = 900` (line 78, used at line 306).
- **Tradeoffs its authors accepted:** total control over the tool implementations, the descriptions, and the eviction logic, at the cost of tracking upstream by hand.
- **Failure mode:** copying the class copies its defaults. `ferqx/sandbox-agent` reproduces the 3,600-second ceiling verbatim, so the effort of replacing the middleware bought no change to the limit. The framework's own GitHub code-search results are dominated by whole vendored copies of `deepagents`, which is the same failure at repository scale.

### Approach D — Accept the defaults

- **What it is:** call `create_deep_agent`, invoke with no config, and take whatever limits the framework and LangGraph carry.
- **Exemplified by:** `open-strix/open_strix/app.py:533-540` constructs the agent with model, tools, prompt, backend, skills, and subagents and nothing else, then invokes it as `await agent.ainvoke({"messages": agent_messages})` with no config at all (`:1037`).
- **Tradeoffs its authors accepted:** nothing to maintain, and the framework's choices track the framework.
- **Failure mode:** there is no deadline. The run is bounded at 9,999 supersteps, each shell command may ask for an hour, and the process has no other stop condition. For an always-on harness with a human watching a chat transport this is survivable. For a batch job with a wall-clock budget it is not a bound at all.

### Where the step budget is set

Two of the four applications surveyed set a step budget and two do not. `amelia/server/orchestrator/runner.py:283` puts `"recursion_limit": 100` into the config it builds for `astream`, alongside the thread id and its own `configurable` payload. `open-strix` passes no config. Neither attempts to change the bound 9,999 on the compiled graph itself, which matches the mechanics: the invocation config is the documented place for it.

### Where structured output is requested

`amelia` names the strategy explicitly rather than letting the framework choose: `agent_kwargs["response_format"] = ToolStrategy(schema=schema)` (`amelia/drivers/api/deepagents.py:319-320`). It then reads `result.get("structured_response")` and, when the key is absent, logs a warning naming the type of the last message and falls through to prose recovery (`:328-339`). The explicit `ToolStrategy` forgoes native structured output on every model, in exchange for one code path that behaves the same everywhere.

## The provider layer

### Reaching the router

Two shapes appear. `langchain-openrouter` is a dedicated integration built on the `openrouter` SDK, exposing `openrouter_provider` for routing control and `app_url`/`app_title` for attribution (`langchain_openrouter/chat_models.py:177-193`, `:305`). The alternative is `ChatOpenAI` pointed at OpenRouter's base URL, which is what `amelia` does — a provider-preset table resolving to a base URL and an API-key environment variable name, handed to a single chat-model constructor (`amelia/drivers/api/chat_model.py:109-165`). The second shape gives up the routing object; there is nowhere to put `provider`.

DeepAgents has opinions about OpenRouter, but only for string model specs. `resolve_model` returns a `BaseChatModel` instance unchanged and applies its provider profile only when the model arrives as a string (`deepagents/_models.py:54-57`). The OpenRouter profile does three things: it raises `ImportError` when the installed `langchain-openrouter` is below 0.2.0, it injects attribution headers when the corresponding environment variables are unset, and it injects `openrouter_provider={"ignore": ["azure"]}` (`deepagents/profiles/provider/_openrouter.py:79-86`). That last one has a documented reason: OpenRouter's `/responses` beta is stateless, so a replayed `rs_*` reasoning item cannot be looked up upstream and the request fails with `"Item with id 'rs_...' not found"` (`:42-54`). An application that constructs `ChatOpenRouter` itself gets none of this.

### The alias

`~deepseek/deepseek-v4-flash-latest` is one of eleven tilde-prefixed aliases in OpenRouter's catalogue of 340 models. The others follow the same shape: `~anthropic/claude-sonnet-latest`, `~google/gemini-flash-latest`, `~openai/gpt-latest`, `~x-ai/grok-latest`, `~moonshotai/kimi-latest`. Its `tokenizer` is reported as `Router` rather than `DeepSeek`, and its `created` timestamp is later than the concrete release it currently points at.

The alias's `supported_parameters` list is identical to the concrete `deepseek/deepseek-v4-flash-0731`. Its endpoint list is empty. So the parameter list on an alias is inherited rather than derived from live endpoints, and there is no API call that answers "which providers will serve this alias".

### Where a capability guarantee stops

The concrete release's 22 endpoints do not agree on capabilities. Every one of them lists `tools`, `tool_choice`, `reasoning`, and `reasoning_effort`. They diverge on structured output. DeepInfra, Morph, Fireworks, AkashML, Baidu, Cloudflare, Together, Parasail, AtlasCloud, SiliconFlow, Ionstream, Ambient, Io Net, Venice, Mancer 2, and Phala list `structured_outputs`. BaseTen, CoreWeave, Sail Research, Novita, GMICloud, and DeepSeek's own endpoint do not — and of those, BaseTen and CoreWeave list neither `structured_outputs` nor `response_format`. Context windows also vary from 131,072 (AkashML) to 1,048,576, with CoreWeave and AtlasCloud at 262,144.

This is the gap worth naming. The model-level `supported_parameters` list is a union over endpoints. A request pinned to the model name and left to route freely can land on a provider that does not implement the parameter the framework relies on. Since `_supports_provider_strategy` decides between native structured output and tool-based structured output from the model *profile* and not from the serving endpoint (`langchain/agents/factory.py:559-572`), the profile saying `structured_output: True` selects the native path for every request, including ones routed to an endpoint that does not offer it.

OpenRouter's routing object has a field aimed exactly at this. Per the provider-routing documentation (read 2026-08-06), `require_parameters` is a boolean defaulting to false whose effect is "Only use providers that support all parameters in your request". The neighbouring fields are `order` (a sequence to try, which disables load balancing), `only` (an allowlist), `ignore` (a denylist), `allow_fallbacks` (default true; when false, only the primary providers are attempted), `data_collection`, `quantizations`, `sort`, and `max_price`. An allowlist and a parameter requirement are different instruments: the allowlist names providers you have tested, and `require_parameters` names the capability you need and lets OpenRouter work out who has it.

## Cautionary findings

**A tool description that is wrong for the backend in use.** The `execute` tool tells every model that `0` means no timeout (`deepagents/middleware/filesystem.py:1198-1200`, repeated in the prompt at `:1297`). With `LocalShellBackend` the value is rejected downstream as non-positive (`deepagents/backends/local_shell.py:298-300`). The middleware that owns the description cannot know which backend it will be handed, so the description is written for the most permissive case.

**A per-command timeout that disappears on signature drift.** `execute_accepts_timeout` inspects the backend class rather than asking it (`deepagents/backends/protocol.py:890-910`). A hand-written backend that predates the `timeout` parameter loses the feature silently, and the error text handed to the model — update your sandbox package — is addressed to a human. `amelia/drivers/api/deepagents.py:75` is a live instance of this.

**A guarantee that is enforced at the tool and not at the backend.** `FilesystemMiddleware` applies `permissions` in its own tool implementations, not in the backend, and the docstring says so: "Direct backend usage does not currently incorporate `permissions`" (`deepagents/graph.py:475-478`). Combining permissions with an execution-capable backend raises `NotImplementedError` rather than silently doing nothing (`deepagents/middleware/filesystem.py:1667-1674`), which is the better half of the story. The `_permissions` parameter is underscore-prefixed and documented as an internal detail that may move to the backend layer (`deepagents/middleware/filesystem.py:1642-1647`).

**A default that reads as a raise and is not.** DeepAgents' 9,999 recursion limit looks like a deliberate widening of LangChain Core's 25. LangGraph's own default is 10,007 (`langgraph/_internal/_config.py:32`), so the binding lowers the ceiling by eight steps.

**A ceiling that cannot be set to its own default.** `merge_configs` skips a `recursion_limit` equal to `DEFAULT_RECURSION_LIMIT` on the theory that it was filled in rather than chosen (`langchain_core/runnables/config.py:487-489`, `langgraph/_internal/_config.py:184-186`). A caller who genuinely wants the default value cannot express it through that path.

**Vendoring the middleware without changing the number it exists to change.** `ferqx/sandbox-agent` carries a 2,280-line copy of `FilesystemMiddleware` whose `max_execute_timeout` still defaults to 3,600 (`graphs/build_app_agent_v3/patch_filesystem_middleware.py:395`).

## Open threads

- **`BaseSandbox` and the offload path.** `deepagents/backends/sandbox.py` is 1,501 lines and implements every file operation by shelling out through `execute`, and `execute_with_offload` writes oversized output to a capture path on the sandbox filesystem instead of into the message (`deepagents/middleware/filesystem.py:2861-2868`). Neither was read. It is the shape any containerized or remote compute target would take.
- **`CompositeBackend`.** 954 lines, routes path prefixes to different backends, and changes the answer to "does this backend support execution" to a question about its default member (`deepagents/middleware/filesystem.py:1436-1437`). `open-strix` uses it (`open_strix/app.py:491-498`). Not read.
- **Harness profiles.** `_harness_profile_for_model` selects a per-model profile that can add middleware, rewrite tool descriptions, exclude tools, prepend a base system prompt, and disable the general-purpose subagent (`deepagents/graph.py:605`). Five built-in profiles ship, for Anthropic Haiku 4.5, Opus 4.7, Sonnet 4.6, NVIDIA Nemotron 3 Ultra, and OpenAI Codex. Whether any profile matches an OpenRouter-served DeepSeek model, and therefore whether a prompt or a middleware arrives uninvited, was not determined.
- **The `openrouter` SDK.** `langchain-openrouter` depends on `openrouter>=0.9.2`, a separate package that was not read. Retry behavior, how `timeout_ms` is applied, and whether it distinguishes a connect timeout from a read timeout are all decided there.
- **Reasoning effort through `ChatOpenRouter`.** The model advertises `reasoning` and `reasoning_effort`. Which constructor field on `ChatOpenRouter` sets them, and what happens when a routed provider ignores them, was not read.
- **Live behavior of the alias.** Everything above is catalogue metadata and source. No request was made, so which provider actually serves the alias, and whether a native structured-output request succeeds against it, is unverified.
- **`PatchToolCallsMiddleware` and `_message_eviction`.** Both are installed by default and both rewrite the message list. Neither was read.
- **`vstorm-co/pydantic-deepagents`.** Still unread. A second framework in the same shape would show whether the middleware-replacement seam is a convention or a DeepAgents particular.

## Sources

Repositories, each at the commit it was read at:

- `deepagents` — https://github.com/langchain-ai/deepagents at `21fd0d6794dcbe09b67e678863c14e02c4f2b6d9`. Package version `0.7.4`. Paths in this document beginning `deepagents/` or `tests/` are relative to `libs/deepagents/`.
- `langchain` — https://github.com/langchain-ai/langchain at `3579fe93eeb238cf8b3e0c3865d5a894de4f2d10`. Paths beginning `langchain/agents/` are relative to `libs/langchain_v1/`; paths beginning `langchain_core/` are relative to `libs/core/`; paths beginning `langchain_openrouter/` are relative to `libs/partners/openrouter/`, where `_version.py` reads `0.2.7`.
- `langgraph` — https://github.com/langchain-ai/langgraph at `658541c4960f329864a2523fc7d52427e8190bed`. Paths beginning `langgraph/` are relative to `libs/langgraph/`.
- `amelia` — https://github.com/existential-birds/amelia at `1e70d5f3e34312de5fcc51157d899d13fd90e211`.
- `open-strix` — https://github.com/tkellogg/open-strix at `11fede7594695eeb4b92a5ce4804286a7b04a1d2`.
- `ferqx/sandbox-agent` — https://github.com/ferqx/sandbox-agent, file `graphs/build_app_agent_v3/patch_filesystem_middleware.py` read at `ea6167a4448615c57e1158cf86d0a184448138b2`.
- `SSAFY14-D103/AIG` — https://github.com/SSAFY14-D103/AIG, file `AI/app/agent/personal/factory/deep_agent_factory.py` read at `519d28c1b16fe590cbca223ad03256a9f8e78abf`.

Documents and APIs:

- `langchain-openrouter` release metadata — https://pypi.org/pypi/langchain-openrouter/json, read 2026-08-06. Latest version 0.2.7; dependencies `langchain-core<2.0.0,>=1.4.7` and `openrouter<1.0.0,>=0.9.2`.
- OpenRouter model catalogue — `GET https://openrouter.ai/api/v1/models`, read 2026-08-06. 340 models, eleven of them tilde-prefixed aliases.
- OpenRouter endpoint listings — `GET https://openrouter.ai/api/v1/models/{id}/endpoints` for `~deepseek/deepseek-v4-flash-latest` (0 endpoints) and `deepseek/deepseek-v4-flash-0731` (22 endpoints), read 2026-08-06.
- OpenRouter provider routing reference — https://openrouter.ai/docs/features/provider-routing, read 2026-08-06.
- models.dev catalogue — `GET https://models.dev/api.json`, read 2026-08-06. The `openrouter` provider entry lists 339 models including `~deepseek/deepseek-v4-flash-latest` with `tool_call`, `reasoning`, and `structured_output` all true.
- `deepagents` threat model — `libs/deepagents/THREAT_MODEL.md` in the repository above, generated 2026-03-28. States that `LocalShellBackend` is not the default and must be supplied explicitly, and that the library provides no operating-system-level process isolation.
