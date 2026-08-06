# Development

THIS FILE MUST BE KEPT UP TO DATE AT ALL TIMES

Everything needed to build, run, and check this project on a working machine. Every command here is a real command from this repository — never a plausible guess.

## Prerequisites

- `uv` — installs the interpreter, resolves the dependencies, and runs every command below.
- Python — the version is pinned in `.python-version`, which is what `uv` reads when it builds the environment, and again as `requires-python` in `pyproject.toml`. `uv` installs a matching interpreter itself, so nothing has to be installed by hand.

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

## Installing Coral Into A Repository

Copy `examples/coral.yml` into the repository as `.github/workflows/coral.yml`, on its default branch, and add an `OPENROUTER_API_KEY` secret. That one file is the whole installation. It carries the triggers, the permissions block, the concurrency group, the version pin, and the secret, because a reusable workflow cannot declare any of those for its caller.

The default branch matters. On the comment paths GitHub always reads the workflow file from there, so a copy that lives only on a branch never runs.

## Environment

- `OPENROUTER_API_KEY` — the credential for the model provider. Required. In a run it comes from the secret the calling repository passes to the reusable workflow; locally, from a key you supply yourself.
- `GITHUB_TOKEN` — authorizes the API calls that read the pull request and post the review. Required. The job supplies it, scoped by the `permissions` block in the calling workflow, and it expires when the job ends.

Both are read once at start-up and are deliberately kept out of the agent's environment. No file in the repository records either value.

## Gotchas

- `uv sync --frozen` fails rather than re-resolving when `pyproject.toml` and `uv.lock` disagree. The fix is `uv lock`, and the lockfile is committed.
- Add and upgrade dependencies with `uv add`, so the resolver writes the version. A version typed into `pyproject.toml` by hand is a version nothing resolved.
- The composite actions run the console script by absolute path, out of a virtual environment under `RUNNER_TEMP`. Nothing activates it and nothing puts it on `PATH`, so a step's own `PATH`, `VIRTUAL_ENV`, and `UV_*` are exactly what the runner set and reveal nothing about Coral. A step that ran `coral` bare rather than as `"$CORAL_BIN/coral"` would have to change that, and would break the property TR-42 rests on.
- `ruff format` reformats Python inside Markdown fences, which would rewrite the example code in the documents under `.agents/docs/`. `extend-exclude` in `pyproject.toml` keeps it away from Markdown; leave that setting in place.
