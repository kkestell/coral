# Skeleton And Contract

Plan: `.agents/docs/plans/2026-08-06-13-28-001-skeleton-and-contract.md`
Roadmap: item `1`, left at `built`.

## What landed

1. **The project skeleton.** `pyproject.toml` with `name = "coral"`, `requires-python = ">=3.14"`, the `coral = "coral.cli:main"` console script, and a `hatchling` build system whose wheel target packages `coral`. `.python-version` holding `3.14`. `.gitignore` covering `.venv/`, `__pycache__/`, `*.pyc`, and the three tool caches. An empty `coral/__init__.py`, written before the first `uv add` so the wheel build had a package to find.

2. **The dependencies, added with `uv`.** `uv add deepagents langchain-openrouter httpx pydantic` then `uv add --dev ruff pytest mypy`. `uv` resolved 67 packages and wrote the versions into `pyproject.toml` — `deepagents>=0.7.5`, `httpx>=0.28.1`, `langchain-openrouter>=0.2.7`, `pydantic>=2.12.5`, and in the dev group `mypy>=2.3.0`, `pytest>=9.1.1`, `ruff>=0.16.1`. `uv.lock` is committed.

3. **The three checks, in `pyproject.toml`.** `[tool.ruff]` with `line-length = 100`, `[tool.ruff.lint]` selecting `E`, `F`, `I`, `UP`, `B`, `[tool.mypy]` with `python_version = "3.14"`, `strict = true`, `files = ["coral", "tests"]`, and `[tool.pytest.ini_options]` with `testpaths = ["tests"]`. One setting the plan did not name is also here: `extend-exclude = ["*.md"]`, under Decisions below.

4. **`coral/schema.py`.** The four frozen anchor dataclasses with their `kind` literals, `Anchor` as their plain union, `Finding` carrying `body` and `anchor`, and `Review` carrying `summary`, `findings`, and `everything_already_said`. `Review`'s docstring is one sentence naming what the object is. `body`, `everything_already_said`, and the three line fields carry descriptions through `Annotated[T, Field(description=...)]`, and `everything_already_said`'s description says it is read only when `findings` is empty and what each of its two values means.

5. **`review_from_result`, in the same module.** It reads `structured_response` out of a `Mapping[str, object]` and raises `RuntimeError` with the message the plan specified when that key is absent or holds `None`. A comment above it records that LangChain sets the key to `None` when the model answers with prose, which is why absence and `None` are one failure. No exception class was defined. A value that is present and is not a `Review` trips an `assert`, which is the internal-invariant break `.agents/docs/code-style.md` asks to crash loudly.

6. **`coral/cli.py`.** `main() -> int` builds one `argparse` parser with a required subcommand, registers `resolve`, `review`, and `report`, and sets each subparser's handler with `set_defaults`. The handler is called on its own line and `0` returned on the next, because an attribute off an `argparse.Namespace` is typed `Any` and returning one directly trips `warn_return_any`. The three handlers raise `NotImplementedError`.

7. **`tests/test_schema.py`.** Fourteen tests. Every one of the four anchor kinds validates into the class that names it; a review with an empty `findings` list validates with `everything_already_said` both true and false; `review_from_result` returns the review it is given and raises on both a missing key and a `None`, with the message asserted exactly. The edge cases the plan named are all there: a half-filled span is rejected rather than validating as a line or file anchor, an undeclared `kind` is rejected, a stray field on a file anchor is dropped rather than refused, and the generated JSON schema contains no `oneOf` and emits the anchor union as four `anyOf` `$ref`s in order. Anchors are validated inside a whole `Review` payload rather than on their own, because that is the shape the model fills.

8. **`.agents/docs/development.md`,** filled in. Prerequisites name `uv` and point at `.python-version` for the interpreter rather than repeating the number. Setup is `uv sync`, with `uv sync --frozen` named as what the runner does. The commands are run, test, lint, format, and type-check, and the document says outright that there is no build step. Environment covers `OPENROUTER_API_KEY` and `GITHUB_TOKEN`, each with where a real value comes from. The "Services and Ports" section is gone. Gotchas cover the `--frozen` failure and its fix, `uv add` as the way to add a dependency, and the Markdown exclusion described under Decisions.

9. **`.agents/docs/testing.md`,** filled in. `pytest` with plain `assert` and no mocking library; `tests/` at the root with one `test_<module>.py` per module; a unit tier and no other, because nothing that reaches GitHub, the model, or the workflow exists; the narrow invocations for one file, one test by name, and shown output; no fixtures, with payloads written inline; and a "Not Covered" section naming the GitHub API, the agent, and the workflow.

10. **A tooling section in `.agents/docs/code-style.md`.** It names `pyproject.toml` as the one place `ruff`, `pytest`, and `mypy` are configured, names `.python-version` and `requires-python` as the two interpreter pins, and points at `.agents/docs/development.md` for the commands. The `Project Rules` section was not touched.

11. **The codebase map in `.agents/docs/architecture.md`.** The Python line in "Tech Stack" now reads 3.14 with both pins named. "Codebase Map" carries every entry from the roadmap's layout, one line each, prefaced by a sentence saying that `coral/schema.py`, `coral/cli.py`, and `tests/` are what exist today; every other entry is marked as not built. The five invariants from the plan are appended to "Invariants".

12. **The roadmap.** Item 1's status is `built`.

## Decisions

**`ruff format` reaches into Markdown, and now does not.** Ruff 0.16 formats Python inside Markdown fences, so the first `uv run ruff format` rewrote the example code in `.agents/docs/code-style.md`, inserting blank lines between the top-level statements in its three fenced blocks. That document is prose and its examples are written for a reader. `extend-exclude = ["*.md"]` in `[tool.ruff]` keeps the formatter to Python, the document was restored to what it said before, and `.agents/docs/development.md` records the setting under Gotchas so it is not removed as clutter later.

**Item 2 was not marked current.** The plan's last task asks for milestone 2 to be marked current. The roadmap has no such marker: status is per-item, and it states that the current item is the lowest-numbered one not yet `verified`. Item 1 is `built` and not yet `verified`, so it is still the current item, and `/review` is what advances it. Only item 1's status changed.

**A non-`Review` under `structured_response` asserts.** The plan specifies the `RuntimeError` for an absent key and for a `None`, and says the function returns the value when it is a `Review`. The remaining case — a key holding something else entirely — is a broken internal invariant rather than a bad model reply, so it trips an `assert` naming the type that arrived.

## Amendments

The plan held. Two observations worth carrying into later items, neither of which changed anything built here:

**`Review`'s docstring reaches the model on one of the two strategy paths, not both.** Pydantic deliberately drops a stdlib dataclass's docstring when generating a JSON schema (`pydantic/json_schema.py:1811-1813` sets the description to `None` for a vanilla dataclass), so the docstring is absent from `TypeAdapter(Review).json_schema()`. LangChain carries it separately: `_SchemaSpec` falls back to the class's `__doc__` (`langchain/agents/structured_output.py:167-170`), and `ToolStrategy` puts that string in the output tool's description, where the model reads it. `ProviderStrategy.to_model_kwargs` sends only the name and the schema (`:290-304`), so on the native path the docstring does not reach the model and only the field descriptions do. Milestone 5 picks the strategy and this is one input to that choice. The field descriptions are in the JSON schema either way.

**Importing `langchain_core` warns on Python 3.14.** `langchain_core/utils/pydantic.py:41` emits `UserWarning: Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater`. Nothing in this milestone imports it — the warning appeared during the manual check below — but it will show up in every run once `coral/agent.py` exists.

## Not landed

Everything the plan promised landed. The plan's `Not doing` list is untouched: no wire type, no Pydantic discriminator, no strategy choice, no `resolve.py`/`review.py`/`report.py`, no severity or confidence on a finding, no `README.md`, and no CI workflow for Coral's own repository.

One suggestion, declined here as out of scope: nothing yet reads an anchor, so the exhaustive `match` the invariant describes has no site and no test. The first one arrives with `coral/github/post.py` in milestone 7, and that is where a missing-case check earns a test.

## Verification

`uv sync --frozen`:

```
Checked 66 packages in 0.51ms
```

`uv run ruff format --check`:

```
4 files already formatted
```

`uv run ruff check`:

```
All checks passed!
```

`uv run mypy`:

```
Success: no issues found in 4 source files
```

`uv run pytest`:

```
collected 14 items

tests/test_schema.py ..............                                      [100%]

============================== 14 passed in 0.01s ==============================
```

The console script resolves, which is what the plan asked the manual check to prove. `uv run coral review` ends in `NotImplementedError` raised from `coral/cli.py:11`, exit code 1, rather than a missing-entry-point error; `resolve` and `report` do the same. `uv run coral` with no subcommand prints the usage line and exits 2, and `uv run coral --help` lists all three subcommands.

The placeholder check, `grep -rn '{[A-Za-z]' .agents/docs/*.md`, returns one line rather than nothing. It is TR-15 in `.agents/docs/technical-requirements.md`, quoting the two GitHub reaction endpoints, whose paths contain `{owner}` and `{repo}`. No template placeholder survives, and the milestone's done condition is met.

One check beyond the plan's list, because the plan's approach rests on it: the review object was handed to LangChain's own structured-output machinery without a model in the loop. `ToolStrategy(schema=Review)` reports `schema_kind: dataclass`, names the tool `Review`, and takes its description from the docstring. `OutputToolBinding.parse` turned a two-finding JSON payload into a real `Review` holding a `SpanAnchor` and a `FileAnchor`, and `review_from_result` accepted the result. The framework validates the model's JSON straight into these dataclasses, with no conversion step in between.
