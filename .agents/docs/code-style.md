# Code Style

## "Just Enough" Python

This is an experimentation project. Optimize for **cheap to change**, not robust to operate. The value of this code is how fast it can be rewritten tomorrow, so minimize committed surface area. When in doubt, do **less**.

Note the split of concerns: the *domain* — the rules, the semantics, the thing being modeled — deserves care and fidelity to its source of truth. The *Python* implementing it should stay as thin and boring as possible.

## North star

Separate two things "quality" bundles together:

- **Correctness** — the code does what it says. Python doesn't give this for free, so buy the cheap version once: type hints on every function signature, a strict type checker, and a linter in CI. That's the safety net that lets the rest of this file be aggressive.
- **Robustness** — defending against inputs and states that may never occur: exception taxonomies, retries, fallback paths, swappable backends, config layers. Spend almost nothing here. Defensive code bets that the current design is right, and this design is *expected* to change.
- **Boundary sanity is not defensive programming.** Malformed external input — a truncated file, a bad request, a missing field — is ordinary input, not a bug. It must produce a clear message and a nonzero exit, never a traceback and never a quietly wrong answer. Broken *internal* invariants should crash loudly and immediately. The boundary is where data enters; everything past validation is our own invariant to keep.

Default to the simplest thing that runs and reveals whether the idea works. Prefer leaving a `# TODO:` over building the hardened version speculatively. A module that handles half the cases and `raise NotImplementedError`s the rest is the expected intermediate state.

## Keep — this is still real, modern Python

- **Type hints everywhere**, checked strictly. Built-in generics (`list[str]`, `X | None`), no `typing.List`, no bare `Any` as an escape hatch.
- **The expressive core stays:** comprehensions, generators, `dataclasses`, `enum`, `pathlib`, f-strings, context managers, `itertools`.
- **Frozen dataclasses + `match` for structured data.** This is the one place a rich type is the *simplest* thing: exhaustive `match` over a tagged union is how a missing case gets found by the checker instead of at runtime. Don't erase that into dicts of `Any`.
- **Abstractions the code has *earned* by repeating.** Discovered: yes. Imposed up front: no. Idiomatic ≠ enterprise.

## Errors

Two kinds of failure, handled differently:

**Reportable problems** — the user's input is wrong. If these are the real output, they get one small frozen dataclass (position/source + message), collected in a list so several can be reported per run, sorted before printing so the list reads in a sensible order. That is not a taxonomy: no class per rule, no error codes, no registry. The message is a `str`, written for a human.

**Everything else** — plumbing. Let exceptions propagate. Catch only where you'd genuinely do something different, and let the top level print one clean message.

- `assert` and `raise AssertionError` are fine and often *preferred* for internal invariants: a loud crash points at the broken stage. Treat them as executable assertions, and don't run with `-O`.
- Do **not** use quiet fallbacks — `dict.get(k, default)`, `except Exception: pass`, `or 0` — around results that should exist. A missing value is a bug upstream; substituting one hides it until the output is silently wrong.
- Do **not** define custom exception classes unless you actually `except` on them to recover differently. An error that is only ever printed doesn't need a type.

```python
# Don't — a taxonomy for something only ever printed
class ValidationError(Exception): ...
class MissingField(ValidationError): ...
class TypeMismatch(ValidationError): ...
# ...forty more...

# Do
@dataclass(frozen=True)
class Problem:
    where: str
    msg: str
```

## Data & mutation

- **Copy freely.** Prefer plain owned data: `list`, `dict`, frozen dataclasses. Share by passing the object.
- **Prefer immutable by default** — `@dataclass(frozen=True)`, return new values instead of mutating arguments. Mutation is fine locally inside a function; it's the shared mutable state across modules that ossifies a design.
- **Name the shape instead of nesting containers.** One level of container is fine: `list[Finding]`, `dict[str, Path]`. Past that, the type stops describing anything. A signature like `dict[str, list[tuple[str, int, str]]]` forces every reader to reconstruct the meaning from call sites, the checker can't tell the three `str`s apart, and adding a fourth element to the tuple breaks unpacking everywhere silently.
- Tuples are for genuinely positional pairs that are read on the next line, not for records. The moment a tuple element needs a name to be understood, it wanted a dataclass.

```python
# Don't — the reader has to guess what any of these mean
def group(rows: list[tuple[str, int, str]]) -> dict[str, list[tuple[str, int, str]]]: ...

# Do
@dataclass(frozen=True)
class Comment:
    path: str
    line: int
    body: str

def group(comments: list[Comment]) -> dict[str, list[Comment]]: ...
```
- Don't micro-optimize: no `__slots__`, no lazy generators for a thousand rows, no caching until something is measurably slow. Clear and correct beats clever, and it'll still be fast enough.

## Abstraction

- **Concrete types until the rule of three** (two real implementations plus a third in sight). No `Protocol`, no ABC, no generics for a single caller.
- No factories, no plugin registries, no dependency injection, no config objects threaded through everything. A visitor class is the same mistake: write a plain recursive function that `match`es.

```python
# Don't — speculative generality for one implementation
class Backend(Protocol):
    def emit(self, node: Node) -> None: ...

def lower(tree: Tree, backend: Backend) -> None: ...

# Do
def lower(tree: Tree, out: list[str]) -> None: ...
```

## Structure & config

- **One module, one concern.** The pipeline stages are the top-level seams and each gets a module. A long module that is one coherent walk is fine; the aim is cohesion, not short files. A stage with genuinely distinct parts can use a shallow package without exposing its internals.
- Stay flat otherwise: no deep package trees, no `utils.py` junk drawer, few dependencies. Reach for the standard library first.
- **Hardcode tuning values as module-level `Final` constants** until knobs are actually requested — paths, sizes, limits, names. A constant takes a second to change; a speculative config layer takes an afternoon to remove.
- Use `uv` (or one lockfile-producing tool) and commit the lock. Ship one entry point; `argparse` is enough.

## Tests, comments, tooling

- **The real test is end-to-end:** run the thing on real input, compare the output. Prefer a small corpus of input files with expected output over unit-testing internal APIs that are still moving. Unit tests earn their keep for things with tricky, stable rules.
- Every bug that gets fixed earns a case in the corpus.
- `pytest`, plain `assert`, no mocking of your own code. If a test needs heavy mocks, the seam is wrong.
- Use `logging` for internals; logs go to **stderr** and stay filterable. Keep stdout for actual requested output.
- `ruff format` and `ruff check`. Don't argue with the formatter.

## Where the tooling is configured

- `pyproject.toml` — `ruff` for lint and format, `pytest`, and `mypy`. All three are configured in that one file and nowhere else, so there is no separate `ruff.toml`, `mypy.ini`, or `pytest.ini` to look for. `ruff` is set to a 100-character line and to Markdown being none of its business; `mypy` runs strict over `coral` and `tests`.
- `.python-version` — the interpreter `uv` builds the environment against. `requires-python` in `pyproject.toml` pins the same version a second time, so an install on an older interpreter fails outright.
- The command that runs each of these is in `.agents/docs/development.md`.

## When to graduate

When the experiment has stuck and the code is going to live, **then** harden — against the failures actually observed, not imagined ones: typed exceptions where recovery genuinely matters, caching where a profile says so, the abstractions that actually recurred, and a test corpus grown around now-stable behaviour. Until then, stay lean.