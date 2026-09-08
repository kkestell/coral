# Development

Commands and local prerequisites for this repository.

## Prerequisites

- `uv` installs the pinned Python interpreter and dependencies.
- Docker must be running for a real review. Unit tests do not start containers.
- A real review needs `~/.config/coral/settings.json` in the format shown in `README.md`.

## Commands

- Setup: `uv sync`
- Run: `uv run coral [scope]`
- Test: `uv run pytest`
- Lint: `uv run ruff check`
- Format: `uv run ruff format`
- Type-check: `uv run mypy`
- All local checks: `make check`

## Gotchas

- `uv sync --frozen` fails when `pyproject.toml` and `uv.lock` disagree; run `uv lock` after a
  dependency change.
- A real review can install dependencies and execute repository code inside Docker. The container
  has network access but no OpenRouter key or Docker socket.
- Git-ignored files are excluded from agent checkout copies. A dependency present only in an
  ignored directory must be installed inside each container.
- `ruff format` must remain excluded from Markdown in `pyproject.toml`.
