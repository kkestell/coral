# Reference Implementations

Status: Living document (last updated 2026-08-06)

Repositories that past research read, and what was in them. Nothing here is checked out. Each entry carries the URL and the commit it was read at, so `/research` can clone it into a scratch directory when a topic needs it again and throw it away afterwards.

This catalogue grows one research topic at a time and is never complete. It holds what past topics needed and nothing else. A new topic scans the `Read for` lines to decide whether anything here already speaks to it, and goes looking for new repositories when nothing does.

## Repositories

### `deepagents`

- Source: https://github.com/langchain-ai/deepagents
- Commit: `21fd0d6794dcbe09b67e678863c14e02c4f2b6d9`
- Stack: Python 3.11+, LangChain 1.x, LangGraph; a monorepo whose `libs/deepagents` holds the SDK, version `0.7.4`
- What it is: The agent framework Coral is built on. `create_deep_agent` assembles a LangGraph agent from a middleware stack it builds itself, so most runtime limits live on middleware constructors the factory does not expose. Middleware passed by the caller is merged into that stack by name, and a name collision replaces the framework's instance in place, which is the seam every middleware-level limit is reachable through.
- Read for: DeepAgents control points — what the framework decides at construction and what it hands over. The shell-timeout ceiling, the summarization thresholds, the filesystem tool allowlist, and the grep cap all live on `FilesystemMiddleware` and the summarization factory rather than on `create_deep_agent`. The step budget is bound onto the compiled graph and overridden at invocation time.
- Where to look: `libs/deepagents/deepagents/graph.py` — the whole factory, the middleware stack it builds, `_apply_custom_middleware`'s replace-by-name merge, and the `recursion_limit` bound at the end; `libs/deepagents/deepagents/middleware/filesystem.py` — `max_execute_timeout` and the `execute` tool that rejects rather than clamps, plus `supports_execution`; `libs/deepagents/deepagents/backends/protocol.py` — `BackendProtocol` and `SandboxBackendProtocol`, and `execute_accepts_timeout`'s signature inspection; `libs/deepagents/deepagents/backends/local_shell.py` — `LocalShellBackend`, whose `timeout` is a default and whose environment is empty unless asked otherwise; `libs/deepagents/deepagents/middleware/summarization.py` — installed unconditionally, thresholds read off the model profile; `libs/deepagents/deepagents/profiles/provider/_openrouter.py` — the version floor and the injected `openrouter_provider` ignore rule, applied only to string model specs; `libs/deepagents/tests/unit_tests/test_graph.py:2550` — the test class proving user middleware replaces same-named defaults; `libs/deepagents/THREAT_MODEL.md` — where the framework places trust

### `langchain`

- Source: https://github.com/langchain-ai/langchain
- Commit: `3579fe93eeb238cf8b3e0c3865d5a894de4f2d10`
- Stack: Python monorepo; `libs/langchain_v1` is the 1.x `langchain` package, `libs/core` is `langchain-core`, `libs/partners/openrouter` is `langchain-openrouter` at version `0.2.7`
- What it is: The layer beneath DeepAgents, and the home of the OpenRouter integration. `create_agent` is what DeepAgents' factory returns, so structured-output strategy selection and the `AgentMiddleware` contract are decided here.
- Read for: DeepAgents control points — how `response_format` resolves, and how `ChatOpenRouter` is configured. A raw schema becomes `AutoStrategy`, which picks native structured output or a tool-based fallback per request from the model's bundled profile rather than from the endpoint that serves the request. `ChatOpenRouter` takes `timeout` in milliseconds and `openrouter_provider` as the routing object.
- Where to look: `libs/langchain_v1/langchain/agents/factory.py` — `_supports_provider_strategy`, the `AutoStrategy` resolution, and the `structured_response` state key being cleared when the model answers with prose; `libs/langchain_v1/langchain/agents/structured_output.py` — the three strategies and their error types; `libs/langchain_v1/langchain/agents/middleware/types.py` — `AgentMiddleware.name` defaulting to the class name, which is what makes replace-by-name work; `libs/core/langchain_core/runnables/config.py` — `merge_configs` refusing to let the default `recursion_limit` override anything; `libs/partners/openrouter/langchain_openrouter/chat_models.py` — the millisecond timeout and the provider routing kwarg; `libs/partners/openrouter/langchain_openrouter/data/_profiles.py` — the bundled models.dev-derived capability table, keyed including the tilde aliases

### `langgraph`

- Source: https://github.com/langchain-ai/langgraph
- Commit: `658541c4960f329864a2523fc7d52427e8190bed`
- Stack: Python; `libs/langgraph` holds the `Pregel` runtime
- What it is: The graph runtime the agent compiles to. It owns the step budget and its own config-merging rules, which differ from LangChain Core's.
- Read for: DeepAgents control points — where a step budget is actually enforced. LangGraph's own `DEFAULT_RECURSION_LIMIT` is read from `LANGGRAPH_DEFAULT_RECURSION_LIMIT` and defaults to 10,007, so DeepAgents' bound 9,999 is a small reduction rather than a large widening. An invocation-time config overrides the bound one, and exhausting the budget raises `GraphRecursionError`.
- Where to look: `libs/langgraph/langgraph/_internal/_config.py` — the 10,007 default, `ensure_config`'s last-scalar-wins merge, and the same default-value guard as LangChain Core; `libs/langgraph/langgraph/pregel/main.py` — `with_config` copying the graph, the `ensure_config(self.config, config)` resolution on the streaming paths, and the recursion-limit check that raises; `libs/langgraph/langgraph/errors.py` — `GraphRecursionError` subclassing `RecursionError`

### `amelia`

- Source: https://github.com/existential-birds/amelia
- Commit: `1e70d5f3e34312de5fcc51157d899d13fd90e211`
- Stack: Python 3.12, DeepAgents, LangGraph, models via OpenRouter, `uv`, Pydantic, loguru, FastAPI, pytest
- What it is: A local orchestrator that runs a code change through architect, developer, reviewer, and evaluator agents in a loop, then opens and reviews pull requests. It walls its agent framework behind an interface of its own and supports three interchangeable drivers behind it, one of which is DeepAgents and two of which are coding CLIs.
- Read for: Code structure — the model call behind a hand-written Protocol. The application declares its own interface listing only the operations it needs, and one adapter module per framework implements it. Gives up a second interface to maintain, and the framework re-enters through whatever the interface does not mention.
- Read for: DeepAgents control points — the shell cap put in a hand-written backend rather than in the framework's middleware. `LocalSandbox` subclasses `FilesystemBackend` and `SandboxBackendProtocol` and hardcodes 300 seconds inside its own `execute`. Gives up the per-command timeout entirely: its `execute` omits the `timeout` parameter, so the framework's signature inspection reports the feature unsupported and every model request carrying one is refused. Also the step budget set at invocation time, and structured output requested as an explicit `ToolStrategy` with a prose fallback when `structured_response` is absent. Reaches OpenRouter through `ChatOpenAI` and a base URL rather than through `langchain-openrouter`, so there is nowhere to put the provider routing object.
- Where to look: `amelia/drivers/base.py` — the `DriverInterface` Protocol, the declared framework boundary; `amelia/drivers/api/deepagents.py` — the DeepAgents adapter, the one place the framework is named, holding `LocalSandbox` at the top and the `create_deep_agent` call with `ToolStrategy` and the `structured_response` fallback below it; `amelia/drivers/api/chat_model.py` — the provider-preset table resolving to a base URL and an API-key environment variable; `amelia/server/orchestrator/runner.py:283` — `recursion_limit` set to 100 in the config handed to `astream`; `amelia/drivers/factory.py` — selection between the three drivers, which is what makes the Protocol load-bearing; `amelia/agents/reviewer.py` — an agent that reaches the model only through the Protocol, with a structured submit tool and a prose-parsing fallback beneath it; `amelia/agents/prompts/` — prompts as defaults with a database override resolver; `amelia/pipelines/base.py` and `amelia/pipelines/review/graph.py` — LangGraph used directly, showing where the boundary stops; `tests/unit/agents/test_reviewer.py` — the driver faked at one helper, which is the seam the Protocol bought

### `pr-agent`

- Source: https://github.com/qodo-ai/pr-agent
- Commit: `4a26c38d33d16ea490d6f0dd5c11b06e6c2f2cac`
- Stack: Python 3.12, litellm, Jinja2, dynaconf, Docker; no agent framework
- What it is: A mature pull request review bot that posts reviews, descriptions, and code suggestions across GitHub, GitLab, Bitbucket, Gitea, and Azure DevOps. It reviews code without an agent framework at all: the model interface is one method taking a system string and a user string, prompts are Jinja2 templates in TOML files, and the reply is YAML embedded in prose that a repair function reassembles when the model gets it wrong. Closest functional sibling to Coral, and it ships as a Docker action as well as a webhook server.
- Read for: Code structure — no framework, one orchestrator class per command. The model is a function taking a system string and a user string, and the application writes its own control flow. Gives up tool calling, so structured output has to be recovered from prose. Also container packaging, so the action is one step: the process reads everything from the environment and the event JSON, and there is no cross-step protocol.
- Where to look: `pr_agent/algo/ai_handlers/base_ai_handler.py` — the whole model seam, one abstract method; `pr_agent/tools/pr_reviewer.py` — one orchestrator class for the review command, from diff to published comment; `pr_agent/algo/utils.py` — `try_fix_yaml` and `github_action_output`, both cautionary; `pr_agent/settings/pr_reviewer_prompts.toml` — prompts as templates outside Python; `pr_agent/servers/github_action_runner.py` — everything read from the environment and the event JSON; `action.yaml` with `Dockerfile.github_action` and `github_action/entrypoint.sh` — how one library serves many entrypoints

### `oss-fuzz-gen`

- Source: https://github.com/google/oss-fuzz-gen
- Commit: `c0982c5d40a7e93ce70fd319705804b9a29954d0`
- Stack: Python, Google ADK, LiteLLM, Docker; its own stage and agent abstractions
- What it is: Google's harness that has models write OSS-Fuzz fuzz targets, then actually builds and runs them and feeds the coverage and crash data back into the next attempt. A plain `Pipeline` class owns a three-stage loop and receives agents as constructor arguments, and the loop's only vocabulary is a hierarchy of result types.
- Read for: Code structure — the agent injected into a deterministic loop, typed results as the only currency. Ordinary code owns the loop, agents arrive as constructor arguments, and stages communicate only through a `Result` class hierarchy. Gives up naming: injection is positional, and stages end up encoding their caller's argument order.
- Where to look: `pipeline.py` — the deterministic loop, agents injected, termination decided by `isinstance` on result types; `results.py` — the `Result` hierarchy that is the sole currency between stages; `stage/base_stage.py` and `stage/writing_stage.py` — the stage contract, and positional agent selection as its failure mode; `agent/base_agent.py` — tag and code-fence parsing, showing the typing does not start at the model

### `open-strix`

- Source: https://github.com/tkellogg/open-strix
- Commit: `11fede7594695eeb4b92a5ce4804286a7b04a1d2`
- Stack: Python, DeepAgents, LangChain, `uv`, Discord, FastAPI
- What it is: An always-on autonomous agent harness with a Discord transport, a web interface, a scheduler, and MCP support, published to PyPI. It uses the same framework as `amelia` with no adapter layer at all, the package is twenty modules flat with no subpackages, and the agent is constructed inside a thirty-seven-method class assembled from four mixins. Read it for what the absence of a boundary costs, which is measurable in its test suite.
- Read for: Code structure — no boundary. The framework is imported where used and the agent is built inside the class that owns everything else. Gives up the test seam, so the framework symbol becomes the only place to stub.
- Read for: DeepAgents control points — accepting every framework default. `create_deep_agent` is called with model, tools, prompt, backend, skills, and subagents and nothing else, and the agent is invoked with no config at all, so the run is bounded only at 9,999 supersteps and each shell command may ask for an hour. Gives up any deadline, which is survivable for an always-on harness with a human watching and is not a bound for a job with a wall clock.
- Where to look: `open_strix/app.py` — the god-class, framework imported at module scope, agent construction as one of its methods, the `CompositeBackend` assembled just above it, and the bare `ainvoke` with no config; `open_strix/prompts.py` — prompts as module constants with render functions; `tests/` — nine files monkeypatching `create_deep_agent` because it is the only seam

### `cibuildwheel`

- Source: https://github.com/pypa/cibuildwheel
- Commit: `1828c10ab37f080699c7b81cea34097c684a7074`
- Stack: Python, published to PyPI and also shipped as a composite GitHub Action
- What it is: The wheel-building tool. Read for its packaging rather than its purpose: it is a normal Python package that also ships an `action.yml`, and it installs its own checkout into a virtualenv under `RUNNER_TEMP`, then hands later steps a directory to prepend to `PATH` and a fully quoted command line, in both bash and PowerShell, through step outputs. The clearest worked example of the cross-step protocol being visible rather than hidden inside one process.
- Read for: Code structure — composite steps, installed onto the runner, state through step outputs. An early step builds a virtualenv under `RUNNER_TEMP` and publishes paths and a pre-quoted command line as step outputs. Gives up hidden plumbing: quoting becomes a correctness property of the step boundary, in every shell dialect separately. Also the library writing its own Actions outputs, no-oping when the environment variable is absent.
- Where to look: `action.yml` — the whole four-step composite, including a Python program embedded as a heredoc that builds the virtualenv and writes the step outputs; `cibuildwheel/ci.py` — the library detecting that it is running under Actions; `cibuildwheel/logger.py` — writing the run summary to `GITHUB_STEP_SUMMARY`

### `python-semantic-release`

- Source: https://github.com/python-semantic-release/python-semantic-release
- Commit: `c74aa3b99de6d9c721f8bd6d2abfa142298b94c9`
- Stack: Python, Click, GitPython, Docker; published to PyPI and also shipped as a Docker GitHub Action
- What it is: Version-bump, changelog, and GitHub-release automation driven by commit messages. Read for two structural choices: the action wrapper is a subdirectory of the same repository and does nothing but translate `INPUT_*` variables into command-line flags for the ordinary console script, and the code that reports results back to the runner lives in the library and is registered as a teardown hook so it fires on every exit path. Its `requirements.txt` pins a published release, so the action runs a different version of the code than the repository holds.
- Read for: Code structure — container packaging, so the action is one step, with the wrapper kept inside the repository rather than at the root. Gives up the runner's preinstalled toolchain, and lets the action definition drift from the code when the image installs a published release. Also the library writing its own Actions outputs: registering the write as a teardown hook makes an interrupted run still report how far it got.
- Where to look: `src/semantic_release/cli/github_actions_output.py` — writing `GITHUB_OUTPUT` from inside the library, with heredoc delimiters for multiline values; `src/semantic_release/cli/commands/version.py` — the teardown-hook registration, and the fields being filled in as the command proceeds; `src/gh_action/action.sh` — the translation layer, and its `eval` of a built command string; `src/gh_action/Dockerfile` with `src/gh_action/requirements.txt` — how the code lands in the image

### `ferqx/sandbox-agent`

- Source: https://github.com/ferqx/sandbox-agent
- Commit: `ea6167a4448615c57e1158cf86d0a184448138b2` (the commit that last touched the one file read; the repository was not cloned)
- Stack: Python, DeepAgents, LangGraph
- What it is: An agent harness carrying a 2,280-line copy of the framework's `FilesystemMiddleware` in its own tree. Only that file was read.
- Read for: DeepAgents control points — vendoring the middleware as the way to control it. Gives up nothing structurally and buys nothing either: the copy reproduces the framework's 3,600-second `max_execute_timeout` default verbatim, so replacing the middleware left the limit exactly where it was.
- Where to look: `graphs/build_app_agent_v3/patch_filesystem_middleware.py:395` — the carried-forward default

### `SSAFY14-D103/AIG`

- Source: https://github.com/SSAFY14-D103/AIG
- Commit: `519d28c1b16fe590cbca223ad03256a9f8e78abf` (the commit that last touched the one file read; the repository was not cloned)
- Stack: Python, DeepAgents
- What it is: An agent factory carrying a 1,131-line replacement of `FilesystemMiddleware`, with the timeout ceiling renamed and lowered. Only that file was read.
- Read for: DeepAgents control points — the same vendoring approach as `ferqx/sandbox-agent`, carried through. The parameter is renamed `max_execute_timeout_sec` and defaults to a module constant set to 900 seconds. Gives up tracking upstream by hand across a thousand lines to change one number.
- Where to look: `AI/app/agent/personal/factory/deep_agent_factory.py:78` — `MAX_EXECUTE_TIMEOUT_SEC = 900`, used at line 306

### `slsa-framework/slsa-github-generator`

- Source: https://github.com/slsa-framework/slsa-github-generator
- Commit: `4d014fae4dbd39eb09e8d40348b73db095e6ba9a`
- Stack: Go, TypeScript, YAML; ten `workflow_call` workflows in `.github/workflows/` over more than thirty composite actions spread across `.github/actions/`, `actions/`, and `internal/builders/`
- What it is: SLSA's build provenance generators, published as reusable workflows other projects call. The largest worked example of the arrangement Coral wants, and the one that spends the most to make the caller's version pin reach the actions the workflow runs. Read for its packaging rather than for provenance.
- Read for: Reusable workflow and composite action packaging — discovering the workflow's own identity at run time, then checking it out. A JavaScript action reads the run's OIDC token and pulls the repository, ref, and path out of the `job_workflow_ref` claim, with a fallback that scans the run's `referenced_workflows`. The builder repository is then checked out into the workspace at a literal path, and every later step uses a `./` reference into it. Gives up an `id-token: write` scope the caller must grant, a `dist/` bundle to maintain, and a fallback that filters by a hardcoded repository name and fails outright when the caller pins by digest. The bootstrap steps that run before the checkout stay hardcoded to `@main`, so a caller pinning a release tag still gets whatever those four actions hold today. Also the source of the low-entropy-secret warning: a declared `workflow_call` secret whose value is an ordinary word gets redacted out of unrelated inputs.
- Where to look: `.github/workflows/builder_go_slsa3.yml:133,145,160,194` — the four bootstrap references, all `slsa-framework/slsa-github-generator/...@main`; `.github/workflows/builder_go_slsa3.yml:135-145` — the detect job and its `id-token: write` permission; `.github/workflows/builder_go_slsa3.yml:194-213` — the checkout into `__BUILDER_CHECKOUT_DIR__` and the first `./` references into it; `.github/actions/detect-workflow-js/src/detect.ts:34-61` — `detectWorkflowFromOIDC`, decoding the token and splitting `job_workflow_ref` on its first `@`; `.github/actions/detect-workflow-js/src/detect.ts:63-134` — the API fallback, its hardcoded repository filter, and the missing-ref error for digest-pinned callers; `.github/actions/secure-builder-checkout/action.yaml` — the checkout wrapper, one pinned `actions/checkout` with `persist-credentials: false`; `.github/workflows/generator_container_slsa3.yml:30-45` — named `workflow_call` secrets offered as both secret and input; `internal/builders/container/README.md:220-226` — why, in the authors' words

### `actions/runner`

- Source: https://github.com/actions/runner
- Commit: `2009b20729fdf49c50a88e0ca368906c16a3129c`
- Stack: C#, .NET; `src/runnerversion` reads `2.336.0`
- What it is: The GitHub Actions runner itself, and the only readable source for how an action reference becomes a directory on disk. The Actions service compiles workflow files and is closed, so the runner is where the boundary between "documented" and "verifiable" sits for anything about `uses:` resolution.
- Read for: Reusable workflow and composite action packaging — how `./` and `$/` resolve, and what a composite action's steps are allowed to read. A `./` reference becomes a path under `github.workspace` with no download; a `$/` reference is rewritten into an ordinary `owner/repo@sha` reference before any download, using the repository and commit of the workflow file that defines the running job. The action manifest schema is where the ban on the `secrets` context inside composite actions is enforced.
- Where to look: `src/Runner.Worker/ActionManager.cs:190-201` — `$/` resolution reading `JobContext.WorkflowRepository` and `WorkflowSha`, with a comment stating this is correct for reusable workflows; `src/Runner.Worker/ActionManager.cs:699-711` — `./` joined to the workspace, and the throw for an unresolved `$/`; `src/Runner.Worker/ActionManager.cs:715-719` — where downloaded actions land; `src/Runner.Worker/ActionManager.cs:319-351` — nested resolution grouped by parent action, so a composite's `$/` resolves against that composite's repository; `src/Runner.Worker/ActionManager.cs:1553-1580` — `ResolveSelfRepositoryReferences`, the rewrite itself; `src/Sdk/DTPipelines/Pipelines/PipelineConstants.cs:44,50` — the `self` and `selfRepository` alias strings; `src/Runner.Common/Constants.cs:46,184` — the nine-level composite depth cap and the `actions_self_repository` feature variable; `src/Runner.Worker/action_yaml.json` — the `step-with`, `step-env`, `step-if`, and `string-steps-context` definitions, whose context allowlists omit `secrets`, and `composite-runs`, which permits no action-level `env`; `src/Runner.Worker/Handlers/CompositeActionHandler.cs:250-295` — how a composite step's `env` is built from the job's environment plus the invoking step's overrides; `src/Test/L0/Worker/ActionManagerL0.cs:3614,3738,3816` — the feature-flag-off case, the cross-repository composite resolving to its parent, and the three-level chain

### `DataDog/code-review-action`

- Source: https://github.com/DataDog/code-review-action
- Commit: `2c558ddeddb86069cd6c49793a6bd61c4dbeb71f`
- Stack: YAML and JavaScript; one 1,263-line `workflow_call` workflow, no `action.yml` anywhere
- What it is: An AI pull request reviewer published as a reusable workflow, split into six jobs so that the job holding the model has no write access to GitHub and a separate job does all the posting. The closest published sibling to Coral in both purpose and packaging, and its workflow file opens with a sixty-line security model written for whoever edits it next.
- Read for: Reusable workflow and composite action packaging — the no-composite-actions approach, and the `job` context route to your own repository. Declares three provider API keys as named `workflow_call` secrets rather than inheriting. Carries its own `permissions: {}` plus per-job grants and its own `concurrency` group, leaving the caller's file with only `on:`, `uses:`, `with:`, and `secrets:`. Checks out its own repository with `repository: ${{ job.workflow_repository }}` and `ref: ${{ job.workflow_sha }}`, needing no OIDC scope and no JavaScript. Gives up the caller-side permissions block, so the per-job split works only where the calling repository's default token already carries `pull-requests: write`.
- Where to look: `.github/workflows/code-review.yml:1-60` — the security model comment, including the trust boundaries and the rule against adding secrets to the reviewing job; `.github/workflows/code-review.yml:139-148` — the three declared secrets, each `required: false`; `.github/workflows/code-review.yml:150-163` — workflow-level `permissions: {}` and the concurrency group keyed on the pull request number read from the caller's payload; `.github/workflows/code-review.yml:394-416` — the self-checkout by `job.workflow_repository` and `job.workflow_sha`, and the two scripts copied into an artifact so later jobs share them; `README.md:24-52` — the caller-side quickstart and the required secret names

### `ansible-community/github-docs-build`

- Source: https://github.com/ansible-community/github-docs-build
- Commit: `0442e4ef1e1f2ac6169f4c8f74cf8c1aa905e91b`
- Stack: YAML; four `workflow_call` workflows in `.github/workflows/` over four composite actions in `actions/`
- What it is: Ansible's shared documentation build, and a small clean example of the arrangement Coral wants — reusable workflows and composite actions in one published repository. Read for its packaging only.
- Read for: Reusable workflow and composite action packaging — the self repository reference in production. Commit `0442e4e`, dated 2026-08-01, adopted `$/` for every internal reference.
- Where to look: `.github/workflows/_shared-docs-build-pr.yml:312,336,361,385,395` — five `$/actions/...` references inside a `workflow_call` workflow

### `Homebrew/actions`

- Source: https://github.com/Homebrew/actions
- Commit: `d3565f64e59130f1fd713440276f7d3e11079b88`
- Stack: YAML, Ruby, JavaScript; a repository of composite actions, whose `.github/workflows/` holds self-tests rather than published workflows
- What it is: Homebrew's action collection, read for the composite-inside-composite case. Commit `8b335f2`, dated 2026-08-05, replaced hardcoded `Homebrew/actions/...@<sha>` references to sibling actions with `$/`, which is the case where the old approach cost the most: the pinned SHA had to be bumped in every sibling file on every release.
- Read for: Reusable workflow and composite action packaging — `$/` inside a composite action's own steps, and the older `GITHUB_ACTION_PATH` route to a sibling file.
- Where to look: `post-build/action.yml:31,39,48` — three `$/failures-summary-and-bottle-result` references from one composite action to a sibling; `post-build/action.yml:25-27` — a sibling shell script reached as `"$GITHUB_ACTION_PATH/../deprecate-master.sh"`, which worked before `$/` existed and has never worked for a `uses:` reference

### `liatrio-labs/ai-code-review-workflows`

- Source: https://github.com/liatrio-labs/ai-code-review-workflows
- Commit: `7e471a8dd8ef992df21612208795893e5e3eaed8`
- Stack: YAML; one `workflow_call` workflow, no composite actions
- What it is: A second AI pull request reviewer published as a reusable workflow, much smaller than `DataDog/code-review-action` and taking the opposite position on who resolves the pull request.
- Read for: Reusable workflow and composite action packaging — pushing resolution out to the caller. Requires seven facts as declared inputs, including `pr_number`, both SHAs, `author_association`, and `is_draft`, so the caller's file reads the event payload and the published workflow reads none of it. Declares one named secret and puts it on the job's `env:` block. Carries its own `concurrency` group and expects the caller to grant `contents: read` and `pull-requests: write`.
- Where to look: `.github/workflows/codex-review-reusable.yml:1-76` — the whole `workflow_call` block, the declared secret, and the concurrency group; `.github/workflows/codex-review-reusable.yml:85-86` — the key set once as a job-level environment variable; `README.md:31-47` — the caller file, with the permissions block `DataDog/code-review-action` omits

### `HariSekhon/GitHub-Actions`

- Source: https://github.com/HariSekhon/GitHub-Actions
- Commit: `fb055c2b4aa67596c29b863e53158c00c0e3e4e9`
- Stack: YAML; a large collection of `workflow_call` workflows plus composite actions
- What it is: The repository whose author opened community discussion 18601 in 2022, asking how a reusable workflow reaches a composite action beside it. Read to see what was actually adopted, which is nothing: the references are still hardcoded to a branch, and the parameterized-input workaround GitHub staff proposed in 2023 does not appear.
- Read for: Reusable workflow and composite action packaging — the hardcoded full reference, and evidence that the official 2023 workaround did not get taken up.
- Where to look: `.github/workflows/docker_build_aws_ecr.yaml:24,169` — a `workflow_call` trigger and, inside it, `HariSekhon/GitHub-Actions/generate-docker-tags@master`

### `github/rest-api-description`

- Source: https://github.com/github/rest-api-description
- Commit: `e50419c4bb8f2d1d34735044bb3b410863dc0a10`
- Stack: JSON and YAML; generated OpenAPI descriptions of every GitHub REST endpoint, one bundle per product and API version
- What it is: GitHub's machine-readable REST API description, and the authority on request and response schemas. Read for endpoint schemas rather than for code. It carries no permission data: every operation has an `x-github` object, and across all 808 paths those objects only ever hold `category`, `subcategory`, `enabledForGitHubApps`, `githubCloudOnly`, `triggersNotification`, `previews`, `requestBodyParameterName`, `deprecationDate`, and `removalDate`.
- Read for: GitHub's API contract — which fields a request body accepts. The `comments` array on the create-review endpoint declares exactly `path`, `position`, `body`, `line`, `side`, `start_line`, and `start_side`, requiring `path` and `body`, and `subject_type` appears only on the single-review-comment endpoint. The create-review 422 references `validation_failed_simple`, whose `errors` is an array of bare strings.
- Where to look: `descriptions/api.github.com/api.github.com.json` — the whole bundle, 12.9 MB, `info.version` `1.1.4`. Query it with `jq` rather than reading it; the paths that matter are `/repos/{owner}/{repo}/pulls/{pull_number}/reviews`, `/repos/{owner}/{repo}/pulls/{pull_number}/comments`, and `components.schemas["validation-error-simple"]`

### `github/docs`

- Source: https://github.com/github/docs
- Commit: `0b11cf08b8d4328a404753313d0dcd7f14bd97c6`
- Stack: TypeScript, Next.js, Markdown, YAML; the source of docs.github.com
- What it is: The documentation site's source, and the only published place the fine-grained permission requirement for each REST endpoint can be read as data. The generated data files under `src/github-apps/data/` are keyed by permission and list the operations each one reaches, one file per token type per API version.
- Read for: GitHub's API contract — where permission requirements are published and how to read them. A rendered endpoint page embeds a `progAccess` object holding a `permissions` array, and the array's shape encodes the relationship: one object is one required set, multiple objects are alternatives. The data files flatten that into a single boolean and cannot express it.
- Where to look: `src/rest/components/RestAuth.tsx:86-90` — the comment stating the set semantics, and below it the two headings chosen on set count; `data/ui.yml:256-258` — the exact rendered wording for one set, several sets, and none; `src/github-apps/data/fpt-2022-11-28/server-to-server-permissions.json` — the installation-token permission map, the form to query with `jq`; `src/github-apps/components/PermissionsList.tsx` — the reverse-direction table and its "Additional permissions" column; `data/reusables/rest-api/additional-permissions.md`, `permission-header.md`, and `public-access.md` — the three prose caveats that column and the `allowsPublicRead` flag depend on

## Not read

- `github/codeql-action` — the canonical multi-entrypoint Action, with five published step actions over one library and the parsed config serialized to `RUNNER_TEMP` for a later step to read back. Passed over for the code-structure topic because it is TypeScript, and passed over again for the packaging topic because it publishes no `workflow_call` workflow. Worth revisiting if the cross-step question is ever researched on its own.
- `sigstore/gh-action-sigstore-python` — Python composite action that builds a virtualenv inside `GITHUB_ACTION_PATH` and passes the interpreter path as a step output. Same approach as `cibuildwheel`, which is the larger and more active read.
- `pypa/gh-action-pypi-publish` — a composite action that generates a second Docker action at runtime and writes it into the checkout. Genuinely distinct, but exotic enough to teach little that transfers.
- `codeflash-ai/codeflash` — confines the model to a single HTTP client module and does everything else with program analysis. A variant of the no-framework approach `pr-agent` already covers.
- `divar-ir/ai-doc-gen` — splits handlers from agents with pydantic-ai result types as the output contract. The same boundary-behind-an-interface approach as `amelia`, on a smaller surface.
- `MabudAlam/BugViper` — DeepAgents pull request reviewer that imports the framework freely inside function bodies. The same no-boundary finding as `open-strix`, from a much less mature codebase.
- `dean2021/codeviewx` — small clean DeepAgents tool whose prompts are packaged markdown files loaded with `importlib.resources`. The prompt-storage approach is a gap here; the rest of the layout duplicates what is already covered.
- `twanew/OmniWriter` — LangGraph and DeepAgents with prompts as YAML files and output schemas as per-agent `TypedDict`s. Comments and prompts are in Chinese throughout.
- `elie222/inbox-zero` — no agent package at all; every model call is a leaf function returning a Zod-validated object, and validation is doubled by re-resolving returned names against real objects. TypeScript.
- `google/osv-scanner` — two binaries from one Go module, selected by container entrypoint.
- `hynek/build-and-inspect-python-package` — crosses job boundaries by uploading artifacts, which is a mechanism nothing here covers, but the repository is YAML and shell with no source to read.
- `vstorm-co/pydantic-deepagents` — a second framework in the same shape as `deepagents`. Worth reading to learn whether replace-by-name middleware merging is a convention or a DeepAgents particular.
- `openrouter` (the Python SDK) — `langchain-openrouter` depends on it, and retry behavior and how `timeout_ms` is applied are decided there. Has no repository entry because it was reached only through `langchain-openrouter`'s dependency metadata.
