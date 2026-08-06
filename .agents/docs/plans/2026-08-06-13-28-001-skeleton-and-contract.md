# Skeleton And Contract

Roadmap: item `1`, `Skeleton and contract`.

## Research

- `.agents/docs/research/deepagents-control-points.md` — how `response_format` resolves, and that the parsed object arrives under an optional `structured_response` state key that is set to `None` when the model answers with prose.
- `.agents/docs/research/code-structure.md` — the console-script-plus-composite-steps arrangement this package layout serves.

## Goal

Create the project and write the contract the agent answers with.

The deliverable is a Python package that installs, lints, type-checks, and tests clean; a console script with the three subcommands wired up; and `coral/schema.py` holding the review object of TR-43 and the rule that its absence is a failure. Alongside it, the three template documents (`development.md`, `testing.md`, `code-style.md`) say what now exists, and `.agents/docs/architecture.md` carries the codebase map.

Satisfies TR-2, TR-3, TR-10, TR-13, and TR-43, and gives FR-21, FR-22, and FR-29 a type. The roadmap's done condition is that `uv sync --frozen`, `ruff check`, `mypy`, and `pytest` all run clean, and that no document contains a template placeholder.

## Approach

`coral/schema.py` is written first and stands alone. It imports nothing from Coral and nothing from the agent framework. The review object is a small set of frozen dataclasses, and the anchor of FR-22 is a union of four of them, each carrying a `kind` literal that names which it is.

That union is handed to the framework directly as `response_format`. LangChain accepts a dataclass and validates the model's JSON into it through Pydantic's `TypeAdapter`, so the type the agent returns is already the type the posting code consumes. There is no wire type, no conversion step, and no second place structure originates. Downstream code reads an anchor with an exhaustive `match` on the four classes.

One function beside the dataclasses reads the agent's result state and returns the review, raising when `structured_response` is absent or `None`. That is the whole of the rule: no prose recovery, no regular expression over the reply, no default to an empty review.

`coral/cli.py` is the console script. It parses the three subcommands with `argparse` and dispatches to three functions that raise `NotImplementedError`. Milestone 2 moves those bodies into `resolve.py`, `review.py`, and `report.py`.

The interpreter and every tool are configured in two files: `.python-version` for the interpreter `uv` builds against, and `pyproject.toml` for `ruff`, `pytest`, and `mypy`.

## Related code

Nothing is built yet, so this section names the documents the change answers to rather than existing code.

- `.agents/docs/technical-requirements.md` — TR-43 states what the review object carries and TR-13 states that it is the only thing the agent hands back. TR-3 states the interpreter version, the three checks, and that `code-style.md` names the file configuring each one.
- `.agents/docs/roadmap.md` — the codebase map this layout creates, and the milestone's done condition.
- `.agents/docs/code-style.md` — frozen dataclasses with `match` for tagged unions, validation at the boundary, no custom exception classes, tuning values as module-level `Final` constants.

## Current state

- Relevant existing behavior: none. The repository holds documents and no code.
- Existing patterns to follow: none in code. The conventions come from `.agents/docs/code-style.md`.
- Constraints from the current implementation: the interpreter is 3.14 and dependencies resolve against a committed lockfile, per TR-2 and TR-3. Python 3.14.6 and `uv` 0.12.1 are present on this machine, and the dependency set below resolves on 3.14.

## Test plan

The tests go in `tests/test_schema.py` and exercise the schema through `pydantic.TypeAdapter`, which is the validator LangChain itself uses on this type. They pin the shape of the contract, not Pydantic's behavior.

**Key behaviors to verify**

- Each of the four anchor kinds validates from a JSON-shaped payload into the class that names it: `{"kind": "span", "path": "a.py", "start_line": 1, "end_line": 3}` becomes a `SpanAnchor`, and the equivalents for `line`, `file`, and `pull_request` become `LineAnchor`, `FileAnchor`, and `PullRequestAnchor`.
- A review with an empty `findings` list validates with `everything_already_said` true and with it false. Both are the states FR-29 needs told apart, so both have to be representable.
- `review_from_result` returns the review when `structured_response` holds one.

**Errors and failures**

- `review_from_result` raises `RuntimeError` when `structured_response` is missing from the result mapping, and again when it is present and `None`. The message is exactly: `The agent returned no structured review. Coral does not recover a review from prose.`

**Edge cases**

- An anchor payload with `kind` set to `span` but carrying only `path` and `line` is rejected. This is the case that matters most: the four variants are a plain union rather than a discriminated one, so the test proves a half-filled span does not quietly validate as a `LineAnchor` or a `FileAnchor` instead.
- An anchor payload whose `kind` is a string none of the four declares is rejected.
- An anchor payload with `kind` set to `file` carrying a stray `line` validates as a `FileAnchor`, with the stray field dropped. Extra fields are ignored rather than refused, so the posting code cannot assume a finding's anchor rejected everything it did not ask for. The test records the behavior so that tightening it later is a deliberate change.
- The generated JSON schema — `TypeAdapter(Review).json_schema()` — contains no `oneOf` anywhere. The union emits `anyOf` with `$ref`s, which is the form a strict provider-side validator accepts, and a later edit that introduces a Pydantic discriminator would silently change it to `oneOf`.

**What NOT to test**

- That frozen dataclasses reject attribute assignment. That is a language guarantee.
- That `argparse` parses the three subcommand names. The bodies raise `NotImplementedError` and there is nothing yet to assert.
- Anything about the model, the framework, GitHub, or the workflow. None of it exists yet, and `.agents/docs/testing.md` records the gap.

## Implementation plan

1. **Create the project skeleton.** Write `pyproject.toml` with `name = "coral"`, `requires-python = ">=3.14"`, the console script `coral = "coral.cli:main"`, and a `hatchling` build system whose wheel target packages `coral`. Write `.python-version` holding `3.14`. Write `.gitignore` covering `.venv/`, `__pycache__/`, `*.pyc`, `.mypy_cache/`, `.pytest_cache/`, and `.ruff_cache/`. Create an empty `coral/__init__.py` in this task and not later: `uv add` installs the project itself into the environment, and the build fails when the package the wheel target names is not on disk.

2. **Add the dependencies with `uv`, never by hand.** Run `uv add deepagents langchain-openrouter httpx pydantic`, then `uv add --dev ruff pytest mypy`. `uv` writes the resolved versions into `pyproject.toml` and produces `uv.lock`. Commit the lockfile. `httpx` is here because `coral/github/client.py` is the one authenticated transport and Milestone 3 builds it. `pydantic` is here because `schema.py` imports `Field` for the descriptions the model reads.

3. **Configure the three checks in `pyproject.toml`.** `[tool.ruff]` with `line-length = 100`, and `[tool.ruff.lint]` selecting `E`, `F`, `I`, `UP`, and `B`. `[tool.mypy]` with `python_version = "3.14"`, `strict = true`, and `files = ["coral", "tests"]`. `[tool.pytest.ini_options]` with `testpaths = ["tests"]`.

4. **Write `coral/schema.py`.** Four frozen anchor dataclasses, each with a required `kind` field typed as the `Literal` naming it:

   - `SpanAnchor` — `kind: Literal["span"]`, `path: str`, `start_line: int`, `end_line: int`
   - `LineAnchor` — `kind: Literal["line"]`, `path: str`, `line: int`
   - `FileAnchor` — `kind: Literal["file"]`, `path: str`
   - `PullRequestAnchor` — `kind: Literal["pull_request"]`

   Then `Anchor = SpanAnchor | LineAnchor | FileAnchor | PullRequestAnchor`, a frozen `Finding` carrying `body: str` and `anchor: Anchor`, and a frozen `Review` carrying `summary: str`, `findings: list[Finding]`, and `everything_already_said: bool`.

   `Review`'s docstring becomes the schema description the model is given, so write it as one sentence naming what the object is. Give `body`, `everything_already_said`, and each anchor's line fields a short description through `Annotated[T, Field(description=...)]`; those descriptions are what the model reads at the moment it fills the object. Say in `everything_already_said`'s description that it is read only when `findings` is empty, that true means everything Coral would say is already on this pull request and still stands, and that false means there was nothing to find.

5. **Write `review_from_result` in the same module.** It takes a `Mapping[str, object]`, reads `structured_response`, and returns it when it is a `Review`. When the key is absent or holds `None`, it raises `RuntimeError` with the message in the test plan. Do not define an exception class for it: nothing catches this to recover differently, and Milestone 8 turns it into a comment on the pull request. Above the function, record in a comment that LangChain sets the key to `None` when the model answers with prose, so absence and `None` are the same failure.

6. **Write `coral/cli.py`.** `main() -> int` builds an `argparse` parser with a required subcommand, registers `resolve`, `review`, and `report`, and dispatches to three module-level functions typed `() -> None` that raise `NotImplementedError`. Set each subparser's handler with `set_defaults(handler=...)` so dispatch is a call rather than a chain of comparisons. Call the handler and then `return 0` on its own line rather than returning the call's result: an attribute read off an `argparse.Namespace` is typed `Any`, and returning one directly trips `mypy`'s `warn_return_any`, which `strict` turns on.

7. **Write `tests/test_schema.py`** to the test plan above. Plain `assert`, `pytest.raises` for the two failure cases, payload dictionaries written inline. There are no fixtures yet.

8. **Fill in `.agents/docs/development.md`.** Prerequisites: `uv`, and the interpreter version named by pointing at `.python-version` rather than repeating it. Setup: `uv sync`. Commands: run (`uv run coral <subcommand>`), test (`uv run pytest`), lint (`uv run ruff check`), format (`uv run ruff format`), type-check (`uv run mypy`); there is no build step for a console script, so say so rather than inventing one. Environment: `OPENROUTER_API_KEY`, required, supplied to the workflow as a secret per TR-65; `GITHUB_TOKEN`, required, supplied by the job. Drop the "Services and Ports" section — nothing listens. Gotchas: `uv sync --frozen` fails rather than re-resolving when `pyproject.toml` and `uv.lock` disagree, and the fix is `uv lock`; add and upgrade dependencies with `uv add` so the resolver writes the version.

9. **Fill in `.agents/docs/testing.md`.** Frameworks: `pytest`, plain `assert`, no mocking library. Layout: `tests/` at the repository root, one `test_<module>.py` per module under test. Kinds: unit tests only today — there is no integration tier, because nothing that reaches GitHub, the model, or the workflow has been built. Running tests: one file with `uv run pytest tests/test_schema.py`, one test by name with `uv run pytest -k <name>`, with output shown using `-s`. Fixtures: none yet; test data is written inline as the JSON-shaped dictionaries the model would produce. Writing a new test: what `.agents/docs/code-style.md` asks for — real input over mocks, edge cases over happy paths, and every fixed bug earning a case. Not covered: the GitHub API, the agent, the model, and the workflow, none of which exist yet.

10. **Add a tooling section to `.agents/docs/code-style.md`,** which TR-3 requires. Name `pyproject.toml` as where `ruff`, `pytest`, and `mypy` are configured, name `.python-version` as what pins the interpreter `uv` builds against, and point at `.agents/docs/development.md` for the command that runs each check rather than repeating it.

11. **Write the codebase map into `.agents/docs/architecture.md`.** Fill the Python line in "Tech Stack" — 3.14, pinned by `.python-version` and by `requires-python` in `pyproject.toml`. Replace the "Codebase Map" placeholder with the map from `.agents/docs/roadmap.md`, one line per entry saying what that part does, prefaced by one sentence naming which parts exist today. Append the invariants below to the "Invariants" section.

12. **Update the roadmap's status line** to record Milestone 1 as done and Milestone 2 as current.

## Not doing

- A wire type separate from the domain type — the framework validates the model's JSON straight into the frozen dataclasses, so there is nothing to convert.
- A Pydantic discriminator on the anchor union — it emits `oneOf`, which a strict provider-side validator rejects, and the `kind` literals discriminate without it.
- Choosing between `ToolStrategy` and `ProviderStrategy` — the strategy is Milestone 5's decision, and this schema validates under either.
- `coral/resolve.py`, `coral/review.py`, and `coral/report.py` — the three subcommand bodies live in `cli.py` and raise `NotImplementedError` until Milestone 2 has something to put in them.
- Severity, confidence, or a title on a finding — FR-21 says text and place, and nothing else is asked for.
- A `README.md` — the documents under `.agents/docs/` carry everything, and there is nothing yet to describe to an outside reader.
- A CI workflow running the three checks — Coral's own repository gets one when there is something to guard; the workflow this milestone's documents describe is the one Coral installs elsewhere.

## Documentation updates

Invariants to record in `.agents/docs/architecture.md`:

- The review object is the only place structure originates. It is a set of frozen dataclasses handed to the agent framework unchanged, so the type the model fills is the type the posting code reads.
- A finding's anchor is a union of four frozen dataclasses, each naming itself with a `kind` literal. Reading one is an exhaustive `match` over the four classes, so a fifth kind is a type error at every site rather than a runtime surprise.
- The schema's JSON form uses `anyOf` and no `oneOf`, which is what a strict provider-side validator accepts.
- The agent's structured result is required. Its absence, and a `structured_response` of `None`, are the same failure, and there is no path that recovers a review from prose or substitutes an empty one.
- The interpreter is pinned in `.python-version` and by `requires-python`; `ruff`, `pytest`, and `mypy` are all configured in `pyproject.toml`.

Other documents this change makes wrong:

- `.agents/docs/development.md` — every section is a template placeholder and is filled in by task 8.
- `.agents/docs/testing.md` — same, filled in by task 9.
- `.agents/docs/code-style.md` — names no configuration file, which TR-3 requires; task 10 adds the section.
- `.agents/docs/architecture.md` — the Python version and the codebase map are placeholders; task 11 fills both.
- `.agents/docs/roadmap.md` — the status line says nothing is built; task 12 corrects it.

## Validation

- Tests to write and run: `tests/test_schema.py`, run with `uv run pytest`.
- Commands: `uv sync --frozen`, `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`, `uv run pytest`. All four have to come back clean, which is the milestone's done condition.
- Manual verification: `uv run coral review` exits with `NotImplementedError` rather than a missing-entry-point error, which is what proves the console script resolves. Then run `grep -rn '{[A-Za-z]' .agents/docs/*.md` and confirm it returns nothing, which is what proves no template placeholder survives.

## Follow-up

- Milestone 2 needs a second repository holding a pull request to review. Nothing in this plan creates it.
- Whether a native structured-output request against the serving endpoint succeeds is settled in Milestone 9, against a real run. This schema is written to validate under either strategy so that the question stays open until then.
