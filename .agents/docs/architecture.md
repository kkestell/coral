# Architecture

How the CLI is organized and runs.

## Platform

- Python 3.13, packaged with `uv`; `coral` is the only console entry point.
- The agent loop is LangChain. Models are reached through OpenRouter with
  `langchain-openrouter`'s `ChatOpenRouter`.
- Docker supplies a separate Ubuntu 24.04 container for each agent's shell.
- `~/.config/coral/settings.json` is the only configuration source.

## Run

- `coral/cli.py` parses the optional scope, loads settings, opens the progress table, and keeps
  stdout for the final review.
- `coral/local.py` chooses a default scope, creates checkout copies, schedules reviewers in a
  thread pool, runs the verifier, filters findings, and renders Markdown.
- `gather_reviews` holds the scheduling policy and takes the function that runs one reviewer, so
  the fallback order is testable without Docker or a model call.
- A repository copy starts from its current `HEAD` and overlays tracked and non-ignored untracked
  working-tree files. A non-repository directory is copied whole.
- Reviewers share only an overall deadline and thread-safe spend ledger. Each has a unique checkout
  and container, keyed by its `review_agents` index.
- A failed reviewer is replaced by the next unused configured model. A reached deadline or spend
  cap raises out of the scheduler instead, because it is shared by every agent.
- The verifier starts after scheduling ends and receives flattened findings in configured reviewer
  order, whichever models produced them.
- Temporary containers and checkout copies are removed after success or failure.
- `coral/progress.py` owns stderr for the run: it holds the root logger's only handler, so a log
  record prints above the table, and the table is repainted below it.
- Each agent updates its own table row as its model responds. The table closes before the review
  prints, so the last table painted stays above it.

## Codebase

- `coral/settings.py` — the settings path, shapes, and boundary validation.
- `coral/local.py` — local scope selection, reviewer scheduling and fallback, and Markdown output.
- `coral/agent.py` — the LangChain loop, OpenRouter client, shell tool, and agent middleware.
- `coral/container.py` — Docker lifecycle, mounts, resource bounds, commands, and bounded output.
- `coral/environment.py` — the environment visible inside an agent container.
- `coral/openrouter.py` — exact model lookup and model-profile facts.
- `coral/schema.py` — reviewer findings, verifier verdicts, and deterministic filtering.
- `coral/progress.py` — the live stderr table, its rows, and the logging it takes over.
- `coral/deadline.py` — the overall deadline and reviewer slice.
- `coral/spend.py` — the shared spend cap and measured total.
- `coral/prompts/review.md` and `coral/prompts/verify.md` — reviewer and verifier instructions.
- `tests/` — one test module per module under test.

## Boundaries

- Agent shell and file operations run only in the agent's container and checkout copy.
- The OpenRouter key remains in the CLI process and is passed only to the model client.
- The container gets no host environment, Docker socket, extra capability, or privileged mode.
- Agent containers retain network access for installing repository dependencies.
- Model-produced data reaches stdout only through the structured review and verification schemas.
- Logs go to stderr; stdout contains only a complete successful review.
