# Architecture

How the code is organized and how it runs on GitHub Actions. The mechanics of each part — the exact rules, endpoints, and numbers — live in `.agents/docs/roadmap.md` with the item that builds them. Parts that do not exist yet are marked "not built" in "The Codebase" and nowhere else.

## The Platform

- A GitHub Actions workflow. No cloud account, no standing service; GitHub supplies the trigger, compute, checkout, and credential.
- Python, built with `uv`. Dependencies install with `uv sync --frozen` against the committed lockfile; nothing resolves at run time.
- The agent is DeepAgents. Models are reached only through OpenRouter, via `langchain-openrouter`'s `ChatOpenRouter`.
- The model is `openai/gpt-5.6-luna`: 1,050,000-token context, tool calling, structured outputs, reasoning output, and no `temperature` parameter. Named exactly rather than through a `~` alias, so the concrete model cannot change under a review.
- No datastore. Everything Coral remembers about a pull request is written on the pull request and read back each run. The rest of the design hangs off this.
- `ruff`, `pytest`, and `mypy` are configured in `.python-version` and `pyproject.toml` and nowhere else.

## Installation and Packaging

- Composite actions in this repository, wired by a reusable workflow, installed by one short caller file per repository.
- The caller file must carry all five of: version pin, OpenRouter secret, `on:` block, `permissions:` block, concurrency group. A reusable workflow cannot declare its caller's triggers or grant itself withheld permissions.
- A ruleset-pushed workflow is no substitute: rulesets run only on `pull_request`, `pull_request_target`, and `merge_group` — no comment triggers — and act as merge gates, contradicting an advisory review.
- This repository is public, so callers need no access configuration.
- One secret: the OpenRouter API key, passed by the caller. The GitHub token comes from the job.

## The Run

Five steps in fixed order: setup, resolve, checkout, review, report (failure only).

- Setup installs `uv` and builds Coral's virtual environment under the runner's temporary directory — outside the workspace, never activated, never on `PATH`; every step invokes the console script by absolute path, so the checkout cannot disturb it and the agent's shell never sees it. A step of its own because resolve runs before the checkout and review after it; building it inside resolve buries the gate's log line under an install.
- Resolve is the gatekeeper: it fetches the pull request and the conversation, acknowledges requests, and decides whether a review runs. Both commits are pinned here and never re-read; the merge base of two fixed commits keeps the diff stable while branches move.
- Checkout takes the pinned head SHA, `fetch-depth: 0` (an exact merge base needs full history), `persist-credentials: false` (the default writes the token into the checkout's git config, where the agent could read it). A force-pushed SHA can make it fail; the report step covers that.
- Review builds the agent, runs it, verifies its findings with a second agent run over a reset checkout, and posts what survives.
- Report runs only on job failure and posts the failure comment for whatever the review step could not report.
- A step boundary is a process boundary. Two values cross as step outputs — the head SHA and a `proceed` flag, the values YAML reads; everything else crosses as files under the runner's temporary directory, outside the workspace.
- A stopped run is green: `proceed=false`, reason on stderr, exit zero. Only a broken run is red.
- Every run gets a fresh runner and filesystem.

## The Codebase

One console script, three subcommands — `coral resolve`, `coral review`, `coral report` — each invoked by one composite action's `run:` step.

- `coral/cli.py` — one `argparse` parser, three subcommands.
- `coral/runner.py` — the event, step outputs, the temporary directory, the one reading of `GITHUB_WORKSPACE`.
- `coral/resolve.py` — the gatekeeper: fetch the pull request and conversation, acknowledge requests, apply the gates.
- `coral/review.py` — render each request, run both agents, filter, post the result.
- `coral/report.py` — the failure step. Not built.
- `coral/agent.py` — the only module that imports `deepagents`.
- `coral/schema.py` — the review object and its anchors, the verifier's verdicts, and the filter between them; the only place structure originates.
- `coral/command.py` — what counts as a request: the command, who may make one, Coral's own comments.
- `coral/environment.py` — the agent's shell environment.
- `coral/deadline.py` — the time budget.
- `coral/diff.py` — the merge-base diff and the reset between the two agent runs. Anchor validation not built.
- `coral/github/client.py` — the one authenticated transport.
- `coral/github/conversation.py` — the GraphQL query, the bound, the file the conversation crosses the step boundary on.
- `coral/github/marker.py` — the sentinel: writing and reading it.
- `coral/github/reactions.py` — which comments get the reaction, through both namespaces.
- `coral/github/post.py` — the review, anchor demotion, the plain comment. Retry on rejection not built.
- `coral/prompts/review.md` — what Coral looks for.
- `coral/prompts/verify.md` — how Coral checks a finding it was handed.
- `tests/` — one `test_<module>.py` per module under test.
- `.github/workflows/coral.yml` — the `workflow_call` workflow.
- `actions/setup/` — installs `uv`, builds Coral's virtual environment.
- `actions/resolve/`, `actions/review/` — one `run:` step each.
- `examples/coral.yml` — the file a repository copies in to install Coral.

Rules:

- `coral/agent.py` is the only module importing `deepagents`; everything else depends on the review object's schema. `coral/review.py` imports it inside the function rather than at module scope, because `coral/cli.py` imports `review` to build its parser and `coral resolve` would otherwise pay the framework's two seconds of import on every delivery.
- The prompt is Markdown inside the package, read with `importlib.resources`, so changes diff readably.

## Rules That Hold Everywhere

- An agent's only return value is a structured object, and deterministic code does the posting. Nothing the model produces becomes a push, an approval, or a comment Coral did not compose.
- The review is advisory: always a comment, never approving, never requesting changes, never blocking a merge.
- Neither secret reaches the agent's shell.
- The agent reaches the checkout only through the backend. Coral's own code reaches `git` there only through `coral/diff.py` — the merge base, the diff text, and the reset between the two agent runs — so the diff the agent saw and the diff the anchors are checked against are the same.
- This is not a sandbox. The agent runs arbitrary shell as the runner user with network access; keeping secrets out of its reach is a barrier, not a boundary. Acceptable because Coral is the repository's own CI running the repository's own code.
- The conversation is untrusted input reaching a model with an unsandboxed shell: anyone can comment, and a maintainer's later `/coral` puts a stranger's text in context. The prompt rule — information, never instruction — is not enforced; the real bounds are the unreachable secrets and the schema-only return path. The residual risk, shell on a throwaway runner over already-visible code, is accepted for a proof of concept and is the first thing to revisit anywhere that matters.
- Coral cannot trigger itself: events created with the job's `GITHUB_TOKEN` start no workflow runs (except `workflow_dispatch` and `repository_dispatch`). Free only while Coral has no identity of its own; a move to a GitHub App needs an explicit self-check.
- The token is scoped to `pull-requests: write`, `issues: write`, `contents: read`, and expires with the job.

## The Runner

- Hosted Ubuntu: 4 vCPU / 16 GB public, 2 vCPU / 8 GB private, 14 GB SSD. Larger runners need Team or Enterprise Cloud. Submodules and LFS are checkout inputs left at defaults.
- Coral runs directly on the runner, never in a container: reviewing a repository means running its tests with its toolchain, and the hosted image's preinstalled toolchain is the only reason that works in a repository Coral has never seen.
- On the comment paths the workflow file is read from the default branch, so a pull request cannot change how it is reviewed by asking. On the `pull_request` path it comes from the head, so a pull request can alter its own review — the same trust as every other job, since that population has write access and already runs code beside the secrets.

## Undecided

Decisions arrive here before they are made, not after.

- Whether GitHub's 422 names the offending anchor. The blunt retry is correct either way; a 422 that names entries would allow demoting only those.
- Which provider serves the alias. `require_parameters` survives any answer.
