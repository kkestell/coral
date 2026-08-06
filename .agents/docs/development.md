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

## Environment

- `OPENROUTER_API_KEY` — the credential for the model provider. Required. In a run it comes from the secret the calling repository passes to the reusable workflow; locally, from a key you supply yourself.
- `GITHUB_TOKEN` — authorizes the API calls that read the pull request and post the review. Required. The job supplies it, scoped by the `permissions` block in the calling workflow, and it expires when the job ends.

Both are read once at start-up and are deliberately kept out of the agent's environment. No file in the repository records either value.

## Gotchas

- `uv sync --frozen` fails rather than re-resolving when `pyproject.toml` and `uv.lock` disagree. The fix is `uv lock`, and the lockfile is committed.
- Add and upgrade dependencies with `uv add`, so the resolver writes the version. A version typed into `pyproject.toml` by hand is a version nothing resolved.
- `ruff format` reformats Python inside Markdown fences, which would rewrite the example code in the documents under `.agents/docs/`. `extend-exclude` in `pyproject.toml` keeps it away from Markdown; leave that setting in place.
