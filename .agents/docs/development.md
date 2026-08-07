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

- Run: `uv run coral <subcommand>`, where the subcommand is `resolve`, `review`, or `report`
- Test: `uv run pytest`
- Lint: `uv run ruff check`
- Format: `uv run ruff format`
- Type-check: `uv run mypy`

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

- `OPENROUTER_API_KEY` — the credential for the model provider. Required. In a run it comes from the secret the calling repository passes to the reusable workflow; locally, from `.env`, which is gitignored and is not read by any code. Source it: `set -a; . ./.env; set +a`.
- `GITHUB_TOKEN` — authorizes the API calls that read the pull request and post the review. Required. The job supplies it, scoped by the `permissions` block in the calling workflow, and it expires when the job ends. Locally, `gh auth token` supplies one.

Both are read once at start-up and are deliberately kept out of the agent's environment. `coral review` deletes both from its own process environment before it does anything else, so a later reader finds neither. No tracked file in the repository records either value.

## Gotchas

- `uv sync --frozen` fails rather than re-resolving when `pyproject.toml` and `uv.lock` disagree. The fix is `uv lock`, and the lockfile is committed.
- Add and upgrade dependencies with `uv add`, so the resolver writes the version. A version typed into `pyproject.toml` by hand is a version nothing resolved.
- The composite actions run the console script by absolute path, out of a virtual environment under `RUNNER_TEMP`, and nothing activates it or puts it on `PATH`. A step that ran `coral` bare rather than as `"$CORAL_BIN/coral"` would have to change that, and "The Run" in `.agents/docs/architecture.md` says what it would cost.
- `ruff format` reformats Python inside Markdown fences, which would rewrite the example code in the documents under `.agents/docs/`. `extend-exclude` in `pyproject.toml` keeps it away from Markdown; leave that setting in place.
