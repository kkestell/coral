# Testing

THIS FILE MUST BE KEPT UP TO DATE AT ALL TIMES

How this project tests itself: where the tests live, how to run them, and what a new test is expected to look like. The full-suite commands live in `.agents/docs/development.md`; this document covers everything narrower than that.

Coral runs the tests of the repository under review. Those are not this project's tests, and nothing about them belongs in this document.

## Frameworks and Tools

- `pytest` — the runner, configured in `pyproject.toml`. Assertions are plain `assert`, and a failure that is the point of the test is caught with `pytest.raises`.
- No mocking library, and no fake of Coral's own code.

## Layout

- `tests/` — at the repository root, one `test_<module>.py` per module under test. `tests/test_schema.py` covers `coral/schema.py`.

## Kinds of Test

- **Unit** — one module, real input, no network and no credentials. This is the only tier that exists, because nothing that reaches GitHub, the model, or the workflow has been built yet.

## Running Tests

- One file — `uv run pytest tests/test_schema.py`
- One test by name — `uv run pytest -k <name>`
- With everything the test printed shown — add `-s`

## Fixtures and Test Data

No fixtures yet. A test writes its input inline, as the JSON-shaped dictionaries the model would produce, and validates them through `pydantic.TypeAdapter`, which is the validator the agent framework itself uses on the review object. A test of the schema builds its payloads with the helpers already in `tests/test_schema.py` rather than adding its own.

## Writing a New Test

What `.agents/docs/code-style.md` asks for: real input rather than a mock, edge cases rather than another happy path, and a case for every bug that gets fixed. A test asserts behavior the contract promises and not behavior a dependency happens to have — where recording a dependency's behavior is the point, the test says so in a comment, so tightening it later reads as a deliberate change.

## Not Covered

- The GitHub API — no client exists yet.
- The agent, the model, and the deadline — none of it is built.
- The workflow and the composite actions — they do not exist, and once they do, the only thing that exercises them is a real run against a real pull request.
