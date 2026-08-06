# Code Structure

Status: Living document (last updated 2026-08-06)

## Question

This document covers two structural questions, layered. The first is the primary one.

Where does an application's own deterministic code stop and the agent framework start, and what holds that line in one place? Every application surveyed here has a stage that calls a model and stages that do not, and every one of them had to decide how much of the framework the rest of the program is allowed to see.

Second, how does one codebase serve several steps of a CI run, and how does state cross a step boundary? A step boundary is a process boundary. Anything one step learned and a later step needs has to be written somewhere a new process can read it.

## Summary

On the first question the field splits four ways, and the split is not about how much abstraction is used. It is about *what* gets abstracted. One group hides the model call behind a hand-written interface and lets the framework's orchestration primitives spread freely elsewhere. One group refuses the framework outright and writes its own orchestrator per command. One group treats the agent as an object injected into a deterministic loop, where the loop knows nothing about models and everything about result types. One group has no boundary at all and constructs the agent inside the class that also runs everything else.

A second finding cuts across all four, and it is the one the surveyed code disagrees on most sharply: **where the typing starts.** Every project here advertises structured data moving through its pipeline. In only one of them does that structure originate at the model boundary. In the others the model returns prose, and the structure is recovered afterwards by parsing tags, repairing YAML, or casting. The type annotations look the same in both cases. What differs is whether a malformed model reply is rejected or quietly reshaped, and the surveyed code shows several places where it is quietly reshaped in the direction of success.

On the second question the split is narrower and turns on one choice: whether the code is packaged as a container or installed onto the runner. Container packaging gives one process that reads everything from the environment, and needs no cross-step protocol because there is only one step. Runner installation forces the multi-step protocol into the open, where the boundary carries file paths, and in one case an entire pre-quoted shell command.

## Prior art

### The framework behind a hand-written interface

`amelia` states a Protocol of its own and requires agents to talk only to that.

- `amelia/amelia/drivers/base.py:177` — `DriverInterface`, a `typing.Protocol` with `generate`, `execute_agentic` (line 206), `get_usage`, `get_tool_definitions`, and `cleanup_session`. This is the declared boundary.
- `amelia/amelia/agents/reviewer.py:13-17` — the reviewer imports its own schema, its own tool profile, and `amelia.drivers.base`. It never imports `deepagents` or `langchain`.
- `amelia/amelia/drivers/api/deepagents.py:15-25` — the framework imports are concentrated here, and this is the only file under `drivers/api/` that names `create_deep_agent`.
- `amelia/amelia/drivers/factory.py:6-10` — the factory selects between `ApiDriver`, `ClaudeCliDriver`, and `CodexCliDriver`. Three implementations is what makes the Protocol load-bearing rather than decorative.
- `amelia/amelia/agents/_driver_init.py` — every agent builds the same driver, options, and prompts triple through one helper, so there is a single call site to fake in tests.

The abstraction pays for itself in the test suite. Fourteen test files fake the driver by patching `amelia.agents._driver_init.get_driver`, for example `amelia/tests/unit/agents/test_reviewer.py:36`. Only four test files patch a framework symbol, and all four are tests of the adapter itself, under `tests/unit/drivers/`.

### No framework at all, one orchestrator per command

`pr-agent` reviews pull requests without an agent framework in the middle. The model is a function that takes two strings and returns one.

- `pr-agent/pr_agent/algo/ai_handlers/base_ai_handler.py:19` — `chat_completion(model, system, user, temperature, img_path)`. No tools, no schema, no loop. Implementations for litellm, langchain, and openai sit beside it in the same directory.
- `pr-agent/pr_agent/tools/pr_reviewer.py:216-240` — `_get_prediction` renders two Jinja2 templates and awaits the handler. The whole model interaction is those twenty-four lines.
- `pr-agent/pr_agent/settings/pr_reviewer_prompts.toml:1` — prompts live outside Python, one TOML file per command, as Jinja2 templates with the diff interpolated in.
- `pr-agent/pr_agent/git_providers/` — gathering the diff and publishing the result are one subpackage, shared across GitHub, GitLab, Bitbucket, Gitea, and Azure DevOps.

The layout is peer subpackages under one root, divided by what each does rather than by layer. `algo/` holds token budgeting, diff compression, and the model seam. `tools/` holds one orchestrator class per command. `servers/` holds the entrypoints.

### The agent as an object injected into a deterministic loop

`oss-fuzz-gen` inverts the arrangement. The pipeline owns the control flow and receives agents as constructor arguments.

- `oss-fuzz-gen/pipeline.py:38-56` — `Pipeline.__init__` takes three optional lists of `BaseAgent` and hands each list to a stage. The pipeline never constructs an agent.
- `oss-fuzz-gen/pipeline.py:57-92` — `_terminate` decides whether to keep going by `isinstance` checks against `BuildResult` and `AnalysisResult`. The loop's only vocabulary is result types.
- `oss-fuzz-gen/results.py:25-426` — `Result` and its subclasses `BuildResult`, `RunResult`, `AnalysisResult`, `TrialResult`. These are the only things passed between stages.
- `oss-fuzz-gen/stage/base_stage.py:72-79` — the abstract method is `execute(result_history, cycle_count) -> Result`. A stage takes the accumulated history and appends to it.

### No boundary at all

`open-strix` is a shipped tool built on the same framework as amelia, with no adapter layer.

- `open-strix/open_strix/app.py:21` — `from deepagents import create_deep_agent`, at module scope.
- `open-strix/open_strix/app.py:344` — `class OpenStrixApp(DiscordMixin, SchedulerMixin, ToolsMixin, WebChatMixin)`, thirty-seven methods, assembled from four mixins.
- `open-strix/open_strix/app.py:533-539` — the single `create_deep_agent` call in the package is a method on that class, a few lines after the same method has built the model, resolved skill directories, and rendered the system prompt.

The package is flat. Twenty modules sit directly in `open_strix/` with no subpackages, and several are very large: `web_ui.py` is 116 KB, `tools.py` is 63 KB, `app.py` is 55 KB.

### Where prompts live

Every project surveyed moved prompts out of the code that calls the model. They disagree on where to.

- `pr-agent/pr_agent/settings/` — Jinja2 templates inside TOML, one file per command, seventeen files.
- `amelia/amelia/agents/prompts/` — a package of four modules. `defaults.py` holds a `PROMPT_DEFAULTS` mapping, and `resolver.py:63-74` looks up a database override first and falls through to the default.
- `open-strix/open_strix/prompts.py:17` — module-level string constants, with `render_*` functions beside them that assemble the variable sections.
- `amelia/amelia/skills/review/` — per-language review guidance as markdown files outside Python entirely, loaded at runtime.

### One container, one process, everything from the environment

`pr-agent` ships as a Docker action, and the multi-step problem does not arise because there is one step.

- `pr-agent/action.yaml:18-20` — `using: 'docker'`, pointing at `Dockerfile.github_action_dockerhub`.
- `pr-agent/Dockerfile.github_action:7-13` — `pip install --no-cache-dir .` installs the package into the image, then the source is added and `github_action/entrypoint.sh` becomes the entrypoint.
- `pr-agent/github_action/entrypoint.sh:3` — one line, running one module.
- `pr-agent/pr_agent/servers/github_action_runner.py:85-90` — `run_action` reads `GITHUB_EVENT_NAME`, `GITHUB_EVENT_PATH`, and the tokens from `os.environ`, then reads the event JSON from the file at that path and dispatches on the event name.

`python-semantic-release` packages the same way but keeps the wrapper inside the repository as a subdirectory rather than at the root.

- `python-semantic-release/action.yml:161-162` — `using: docker`, `image: src/gh_action/Dockerfile`.
- `python-semantic-release/src/gh_action/action.sh:182-189` — the wrapper's entire job is translation. It folds the `INPUT_*` variables into one command string and runs the same console script a local user would run.

### Composite steps, a virtualenv on the runner, state through step outputs

`cibuildwheel` installs itself onto the runner and therefore has to answer the cross-step question explicitly.

- `cibuildwheel/action.yml:28-29` — `using: composite`, four steps.
- `cibuildwheel/action.yml:31-35` — `actions/setup-python` with `update-environment: false`, so the interpreter is available without being placed on `PATH`. Its path arrives in the next step as `steps.python.outputs.python-path`.
- `cibuildwheel/action.yml:63-66` — the install target is `os.environ["GITHUB_ACTION_PATH"]`. The action installs its own checkout as a package.
- `cibuildwheel/action.yml:70` — the virtualenv is created under `RUNNER_TEMP`, outside the workspace, so a checkout cannot disturb it.
- `cibuildwheel/action.yml:76-88` — only the wanted binaries are symlinked into a separate clean directory, so prepending that directory to `PATH` exposes `cibuildwheel` without exposing the virtualenv's `python` or `pip`.
- `cibuildwheel/action.yml:113-116` — three values are written to `GITHUB_OUTPUT`: `prepend-path`, `cmd-bash`, and `cmd-pwsh`. The command line is assembled in Python with `shlex.join`, and a hand-written `pwsh_quote` produces the PowerShell variant.
- `cibuildwheel/action.yml:130-137` — the later step does `export PATH="$CIBW_PREPEND_PATH:$PATH"` and then `eval "$CIBW_CMD_BASH"`.

So the boundary here carries two different kinds of thing. One is a location on disk. The other is an executable command, pre-quoted, in two shell dialects.

### The library writes its own step outputs

Two projects put the code that talks to the Actions runner inside the library rather than in the wrapper.

- `python-semantic-release/src/semantic_release/cli/github_actions_output.py:158-165` — `write_if_possible` appends to the file named by `GITHUB_OUTPUT`, and returns quietly when that variable is unset, so the same path runs off CI.
- `python-semantic-release/src/semantic_release/cli/github_actions_output.py:146-154` — multiline values are emitted with a `<<EOF` heredoc delimiter; single-line values are plain assignments.
- `python-semantic-release/src/semantic_release/cli/commands/version.py:577` — `ctx.call_on_close(gha_output.write_if_possible)` registers the write as a Click teardown, so it happens on every exit path the command can take.
- `python-semantic-release/src/semantic_release/cli/commands/version.py:486-812` — the output object is built early and its fields are filled in as the command proceeds. `released = True` is set at line 812, near the end.
- `pr-agent/pr_agent/algo/utils.py:1258-1271` — `github_action_output` does the same job, called from inside the review tool at `pr_agent/tools/pr_reviewer.py:253`.
- `cibuildwheel/cibuildwheel/ci.py:26-35` — `detect_ci_provider` checks for `GITHUB_ACTIONS` in the environment, and `cibuildwheel/logger.py:258-260` writes the run summary to `GITHUB_STEP_SUMMARY` when that variable is present.

The teardown-hook arrangement in `python-semantic-release` is the strictest version of this. Registering the write before the work begins means an incomplete run still produces outputs, describing however far it got.

## How the field splits

### Approach A — the model call behind a hand-written Protocol

- **What it is:** A Protocol or abstract class the application owns, listing only the operations the application needs. One adapter module per framework or provider implements it. Agents depend on the Protocol.
- **Exemplified by:** `amelia/amelia/drivers/base.py:177`, with adapters in `amelia/drivers/api/` and `amelia/drivers/cli/`. Also `pr-agent/pr_agent/algo/ai_handlers/base_ai_handler.py:4`, at a much smaller surface.
- **Tradeoffs its authors accepted:** A second interface to maintain, which has to be widened every time the framework offers something new that an agent wants. In amelia the Protocol has grown five methods and a `SubmitToolDef` dataclass at `drivers/base.py:145` to carry structured-output tool definitions across the boundary in a framework-neutral way.
- **Failure mode:** The Protocol covers the operation it was drawn around and nothing else, and the framework enters through whatever the Protocol does not mention. In amelia the Protocol covers the model call, and LangGraph is imported directly across `amelia/pipelines/`. The pipeline layer has a Protocol of its own at `pipelines/base.py`, and its `create_graph` method returns `CompiledStateGraph[Any]` at `pipelines/base.py:98-101`, so a framework type is part of the contract rather than behind it. `pipelines/review/graph.py:9-10` builds a `StateGraph` by hand. A reader who trusts the driver layer will conclude the framework is replaceable, and it is not.

### Approach B — no framework, one orchestrator class per command

- **What it is:** The application calls the model provider directly through a two-string interface and writes its own control flow. There is no agent, no tool loop, and no framework to abstract.
- **Exemplified by:** `pr-agent/pr_agent/tools/pr_reviewer.py`, one class per command, with siblings for description and code suggestions.
- **Tradeoffs its authors accepted:** Anything an agent framework provides has to be built. Token budgeting and diff compression are their own modules under `algo/`, and the model gets one shot at producing the whole review.
- **Failure mode:** Without tool calling there is no structured output, so the reply is prose that must contain parseable data. What that costs is visible in the cautionary findings below.

### Approach C — the agent injected into a deterministic loop, typed results as the only currency

- **What it is:** Ordinary code owns the loop. Agents are objects handed in from outside. Every stage takes the accumulated result history and returns a `Result`, and the loop's decisions are `isinstance` checks.
- **Exemplified by:** `oss-fuzz-gen/pipeline.py:38-92` with `oss-fuzz-gen/stage/base_stage.py:72`.
- **Tradeoffs its authors accepted:** The result classes become the real interface, and they accumulate. `results.py` is ten classes and `RunResult` extends `BuildResult`, so a stage receiving a `Result` must ask what it actually got before using it.
- **Failure mode:** The injection is positional. `stage/writing_stage.py:53-65` selects agents by list index, and because the index depends on which optional agent the caller supplied, the stage checks `get_agent(index=0).name == 'FunctionAnalyzer'` and then reaches for index 2 instead of index 1. The stage has come to encode its caller's argument ordering, which is the coupling the injection was supposed to remove.

### Approach D — no boundary, the framework in the application class

- **What it is:** The framework is imported where it is used. Agent construction is a method on the class that also owns transports, scheduling, and storage.
- **Exemplified by:** `open-strix/open_strix/app.py:344-539`.
- **Tradeoffs its authors accepted:** No indirection, and the shortest path from reading the framework's documentation to working code. This is a real tool with a scheduler, a Discord transport, and a web interface, so the approach evidently ships.
- **Failure mode:** With the framework imported at module scope in the class that does everything, the framework symbol becomes the only test seam. Nine test files under `open-strix/tests/` monkeypatch `app_mod.create_deep_agent`, including `tests/test_discord.py:28` and `tests/test_hooks.py:328`. Every test that wants to exercise scheduling or message handling must first stub out agent construction.

### Approach E — container packaging, so there is only one step

- **What it is:** The code ships as an image. The action is one step, the process reads everything it needs from the environment and from the event JSON file, and there is no cross-step protocol.
- **Exemplified by:** `pr-agent/action.yaml:18-20` with `pr-agent/Dockerfile.github_action:7-13`; `python-semantic-release/action.yml:161-162`.
- **Tradeoffs its authors accepted:** Image build or pull time on every run, and the container's own toolchain rather than the runner's preinstalled one.
- **Failure mode:** The container's environment replaces the runner's, so anything the workflow set up outside the container has to be passed in deliberately. And because the image is built from a specification rather than from the checkout, the action definition and the code can drift. `python-semantic-release/src/gh_action/requirements.txt:1` pins `python-semantic-release == 10.6.1`, so the Docker action runs a published release, not the repository it lives in.

### Approach F — composite steps, installed onto the runner, state through step outputs and files

- **What it is:** A composite action of several steps. An early step installs the package into a virtualenv on the runner and publishes what later steps need as step outputs. Later steps are shell steps that use those outputs.
- **Exemplified by:** `cibuildwheel/action.yml:28-148`.
- **Tradeoffs its authors accepted:** The cross-step protocol is now the author's problem, and it is visible in the action file rather than hidden in a process. cibuildwheel pays for this with a Python program embedded as a heredoc inside YAML, and with two copies of the command-quoting logic because the last step is bash on one platform and PowerShell on another.
- **Failure mode:** Step outputs are strings, and a string that is later `eval`'d is a command. Quoting becomes a correctness property of the boundary rather than an implementation detail, and it has to be right in every dialect separately. The same hazard in `python-semantic-release` is not hypothetical: `src/gh_action/action.sh:182` builds one command string from the action's inputs, and `action.sh:11` runs it through `eval`.

## Cautionary findings

**A structured-output contract with a prose fallback is not a contract.** `amelia`'s reviewer defines `SubmitReviewInput` at `amelia/amelia/agents/schemas/reviewer.py:17` and passes it as the schema of a submit tool at `amelia/agents/reviewer.py:332-340`. That is the advertised interface. But `reviewer.py:417-432` shows three result paths, tried in order: the tool callback, then interception of the message stream, then `_parse_review_result`, which regex-matches a `Ready:` line out of markdown at `reviewer.py:537-539`. A reader of the schema would not expect the third path to exist.

**That fallback fails open.** `amelia/amelia/agents/reviewer.py:521-532` — when the agent produced no output at all, after two attempts, `_parse_review_result` returns `ReviewResult(approved=True, comments=[], severity=NONE)`. A reviewer that cannot reach its model reports that the code is fine. The log line says `defaulting to approved`, so the behavior is deliberate, and the surrounding code does guard the *error* case separately at `reviewer.py:473-484` by overriding `approved` when `has_error` is set. The empty-output case is not an error case.

**The document that tells contributors where the boundary lives can be wrong.** `amelia/CLAUDE.md` instructs that new drivers and agents must conform to interfaces in `amelia/core/`. No Protocol lives there. `DriverInterface` is in `amelia/drivers/base.py:177`. A contributor following the instruction looks in the wrong package.

**Recovering structure by string repair means keeping a list of key names in sync by hand.** `pr-agent/pr_agent/algo/utils.py:771-780` — `try_fix_yaml` holds a hardcoded `keys_yaml` list of eight strings such as `'relevant line:'` and `'improved code:'`, extended per call site by a `keys_fix_yaml` argument. The caller at `pr_agent/tools/pr_reviewer.py:249-252` passes seven more, including `'estimated_effort_to_review_[1-5]:'`. Those strings are field names from a prompt template in a TOML file. Nothing checks that the two agree, so renaming a field in the prompt silently disables its repair rule.

**Output written from deep inside a library can fail silently.** `pr-agent/pr_agent/algo/utils.py:1259-1270` wraps the whole of `github_action_output` in `try`/`except Exception`, logs, and returns. A workflow whose later steps consume that output sees an empty value rather than a failure. Compare `python-semantic-release/src/semantic_release/cli/github_actions_output.py:158-163`, which returns early only when the environment variable is absent and lets a write error propagate.

**A typed result that is cast rather than checked is an annotation, not a guarantee.** `oss-fuzz-gen/stage/writing_stage.py:68` — `build_result = cast(BuildResult, agent_result)`. The pipeline's termination logic at `pipeline.py:68-80` does use `isinstance`, and handles the case where the last result is not the expected type. But the stage that produced it asserted the type without checking it, so a mismatch surfaces later and further away.

**The typing frequently does not start at the model.** `oss-fuzz-gen/agent/base_agent.py:120-143` — `_parse_tag`, `_parse_tags`, and `_filter_code` pull content out of the reply by locating XML-ish tags and fenced code blocks in text. The stage layer above is rigorously typed. The boundary underneath it is string handling.

## Open threads

The DeepAgents backend protocol was not read. `amelia/amelia/drivers/api/deepagents.py:55` defines `class LocalSandbox(FilesystemBackend, SandboxBackendProtocol)`, which is the framework's own extension point for filesystem access, and it is a closer analogue to a single-backend seam than anything in this document. It is 46 KB and deserves its own pass.

Reusable workflows were not surveyed. Every axis-two project here publishes composite or Docker actions. None of the repositories read here publishes a `workflow_call` workflow that declares its own permissions and concurrency, which is a different packaging question from the one covered above.

Nothing here reads a conversation back from a hosting platform as its only memory. All four axis-one projects hold state in a database, in a work directory, or in a result-history list passed down a loop.

Two candidate approaches to prompt storage were found but not read: prompts as packaged markdown resources loaded with `importlib.resources`, seen in `dean2021/codeviewx`, and prompts as YAML files with a loader, seen in `twanew/OmniWriter`. Neither repository was cloned.

The four repositories on the first axis were surveyed for layout. Their test suites were read only far enough to count how each one fakes the model, which is what produced the seam findings for approaches A and D. How the deterministic stages themselves are tested was not examined.

## Sources

Every citation above begins with a repository name. Each name resolves here to a URL and the full commit it was read at, so a path and a line number still resolve after the clone is gone. `.agents/references.md` carries the same repositories with a description of each and where inside it to look.

- `amelia` — https://github.com/existential-birds/amelia at `1e70d5f3e34312de5fcc51157d899d13fd90e211`. Read: `amelia/drivers/base.py`, `amelia/drivers/factory.py`, `amelia/drivers/api/deepagents.py`, `amelia/agents/reviewer.py`, `amelia/agents/_driver_init.py`, `amelia/agents/schemas/reviewer.py`, `amelia/agents/prompts/resolver.py`, `amelia/pipelines/base.py`, `amelia/pipelines/review/graph.py`, `tests/unit/agents/test_reviewer.py`, `CLAUDE.md`
- `pr-agent` — https://github.com/qodo-ai/pr-agent at `4a26c38d33d16ea490d6f0dd5c11b06e6c2f2cac`. Read: `pr_agent/algo/ai_handlers/base_ai_handler.py`, `pr_agent/algo/utils.py`, `pr_agent/tools/pr_reviewer.py`, `pr_agent/servers/github_action_runner.py`, `pr_agent/settings/pr_reviewer_prompts.toml`, `action.yaml`, `Dockerfile.github_action`, `github_action/entrypoint.sh`
- `oss-fuzz-gen` — https://github.com/google/oss-fuzz-gen at `c0982c5d40a7e93ce70fd319705804b9a29954d0`. Read: `pipeline.py`, `results.py`, `stage/base_stage.py`, `stage/writing_stage.py`, `agent/base_agent.py`
- `open-strix` — https://github.com/tkellogg/open-strix at `11fede7594695eeb4b92a5ce4804286a7b04a1d2`. Read: `open_strix/app.py`, `open_strix/prompts.py`, `tests/`
- `cibuildwheel` — https://github.com/pypa/cibuildwheel at `1828c10ab37f080699c7b81cea34097c684a7074`. Read: `action.yml`, `cibuildwheel/ci.py`, `cibuildwheel/logger.py`
- `python-semantic-release` — https://github.com/python-semantic-release/python-semantic-release at `c74aa3b99de6d9c721f8bd6d2abfa142298b94c9`. Read: `action.yml`, `src/gh_action/action.sh`, `src/gh_action/Dockerfile`, `src/gh_action/requirements.txt`, `src/semantic_release/cli/github_actions_output.py`, `src/semantic_release/cli/commands/version.py`
