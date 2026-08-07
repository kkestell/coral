# Development

Everything needed to build, run, and check this project on a working machine. Every command here is a real command from this repository — never a plausible guess.

## Prerequisites

- `uv` — installs the interpreter, resolves the dependencies, and runs every command below.
- Python — the version is pinned in the repository, and `uv` installs a matching interpreter itself, so nothing has to be installed by hand.

Nothing else has to exist outside the repository to run the checks. Running Coral against a real pull request needs the two credentials under "Environment", and in normal operation both are supplied by the workflow rather than by a person.

## Setup

1. `uv sync` — creates `.venv/` and installs the project along with its dependencies and the development group. On the runner this is `uv sync --frozen` instead, which refuses to re-resolve.

## Commands

There is no build step. Coral is a console script over one package, and `uv sync` is what makes it runnable.

- Run: `uv run coral <subcommand>`, where the subcommand is `resolve`, `review`, or `publish`
- Test: `uv run pytest`
- Lint: `uv run ruff check`
- Format: `uv run ruff format`
- Type-check: `uv run mypy`

### Driving A Live Check

What to type to set a live check up and follow it. Which checks to run is in `.agents/docs/testing.md`.

- Open a pull request — `gh pr create --repo kkestell/coral-test --base main --head <branch> --title <title> --body <body>`
- Ask for a review — `gh pr comment --repo kkestell/coral-test <number> --body '/coral'`
- Watch the run — `gh run list --repo kkestell/coral-test`
- Read the review — `gh pr view --repo kkestell/coral-test <number> --comments`

### Reading A Conversation By Hand

The conversation fetch is the one piece that pages, and no pull request in the test repository is busy enough to make it. Point it at a public pull request that is, with a token of your own. It reads and writes nothing.

```
GITHUB_TOKEN=$(gh auth token) uv run python -c "
from coral.github.client import GitHub
from coral.github.conversation import bound, fetch_conversation
import os
c = bound(fetch_conversation(GitHub(token=os.environ['GITHUB_TOKEN']), 'cli', 'cli', 10513))
print(c.bound, len(c.threads))
"
```

The log line the fetch writes to stderr says how many queries it took and what they cost, which is the measurement the conversation bound will eventually be settled against.

## Environment

- `OPENROUTER_API_KEY` — the credential for the model provider. Required by `coral review`. In a run it comes from the secret the calling repository passes to the reusable workflow; locally, from `.env`, which is gitignored and is not read by any code. Source it: `set -a; . ./.env; set +a`.
- `OPENROUTER_MANAGEMENT_KEY` — an OpenRouter management key, which mints API keys rather than making completions. Optional locally, and used by the expiry rehearsal in `.agents/docs/testing.md`; source it out of `.env` the same way. In a run it comes from the caller's secret and reaches the resolve job alone.
- `CORAL_MODEL`, `CORAL_REASONING_EFFORT`, `CORAL_TIME_BUDGET_MINUTES` — the model id, the reasoning effort, and the review step's time budget. All three are required by `coral review`; `coral resolve` reads the budget alone. In a run each comes from the matching `workflow_call` input, which is where its default is; locally, set them on the command line. An empty effort sends no reasoning block.
- `GITHUB_TOKEN` — authorizes the API calls that read the pull request and post the review. Required by `coral resolve` and `coral publish`; it never reaches the review step, whose job holds a `contents: read` token that only the checkout uses. Each job's token is scoped by that job's `permissions` block in the reusable workflow and expires when the job ends. Locally, `gh auth token` supplies one.

Both are deliberately kept out of the agent's environment. `coral review` deletes `OPENROUTER_API_KEY` — the one credential its own process has — before it does anything else, so a later reader finds nothing. No tracked file in the repository records either value.

## Gotchas

- `uv sync --frozen` fails rather than re-resolving when `pyproject.toml` and `uv.lock` disagree. The fix is `uv lock`, and the lockfile is committed.
- Add and upgrade dependencies with `uv add`, so the resolver writes the version. A version typed into `pyproject.toml` by hand is a version nothing resolved.
- The composite actions run the console script by absolute path, out of a virtual environment under `RUNNER_TEMP`, and nothing activates it or puts it on `PATH`. A step that ran `coral` bare rather than as `"$CORAL_BIN/coral"` would have to change that, and "The Run" in `.agents/docs/architecture.md` says what it would cost.
- The unit tests need no Docker: `coral/container.py`'s argument builders and output shaping are pure functions, and nothing under `tests/` runs a container. A real run does, and so does rehearsing that module by hand from a Python prompt.
- Running the agent from a developer machine needs Docker up and `/opt/hostedtoolcache` to exist — `sudo mkdir -p /opt/hostedtoolcache` once. `coral/container.py` mounts it and `coral/environment.py` lists it, and empty is fine: the container gets the image's own `PATH` plus whatever `apt-get` installs.
- `ruff format` reformats Python inside Markdown fences, which would rewrite the example code in the documents under `.agents/docs/`. `extend-exclude` in `pyproject.toml` keeps it away from Markdown; leave that setting in place.
