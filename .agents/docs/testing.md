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

- **Unit** — one module, real input, no network and no credentials. Everything under `tests/` is this tier, and it is the only tier `pytest` runs.
- **Live** — one real run against one real pull request in `kkestell/coral-test`. Anything that crosses into GitHub, the model, or the workflow is checked this way, because there is no other way to check it. A live run is started by hand and is not part of `uv run pytest`.

## Running Tests

- One file — `uv run pytest tests/test_schema.py`
- One test by name — `uv run pytest -k <name>`
- With everything the test printed shown — add `-s`

## The Test Repository

`kkestell/coral-test` is a public repository that exists for this and nothing else. Everything in it is disposable. Its branches, commits, and pull requests are worth nothing, so set one up to suit the check you are making and delete it afterward or leave it, whichever is less work.

Use it. Do not point Coral at a repository whose pull requests somebody cares about, and do not describe what a run would do in place of making one.

The two credentials under "Environment" in `.agents/docs/development.md` are what a live run needs, and a live run leaves its evidence on the pull request: the review Coral posted, the reaction it left on the request, the comment it left when it failed. That evidence is the result. Read it there rather than trusting what the run printed.

`gh` sets the check up and follows it:

- Open the pull request under review — `gh pr create --repo kkestell/coral-test --base main --head <branch> --title <title> --body <body>`
- Ask for a review — `gh pr comment --repo kkestell/coral-test <number> --body '/coral'`
- Watch what the request started — `gh run list --repo kkestell/coral-test`
- Read what Coral said — `gh pr view --repo kkestell/coral-test <number> --comments`

## Fixtures and Test Data

No fixtures yet. A test writes its input inline, as the JSON-shaped dictionaries the model would produce, and validates them through `pydantic.TypeAdapter`, which is the validator the agent framework itself uses on the review object. A test of the schema builds its payloads with the helpers already in `tests/test_schema.py` rather than adding its own.

## Writing a New Test

What `.agents/docs/code-style.md` asks for: real input rather than a mock, edge cases rather than another happy path, and a case for every bug that gets fixed. A test asserts behavior the contract promises and not behavior a dependency happens to have — where recording a dependency's behavior is the point, the test says so in a comment, so tightening it later reads as a deliberate change.

A module that talks to GitHub, the model, or the runner gets two things rather than one. Its own decisions — which gate stops a run, which anchor survives, which comment carries a command — are unit tests over real input. Whether the thing on the other side behaves as the code assumes is a live run against `kkestell/coral-test`. Neither substitutes for the other, and a mock of the far side is not an option here: a mock only ever confirms what was already believed, and every open question in `.agents/docs/roadmap.md` about the platform is a question about a belief that has never been checked.

## Not Covered by `pytest`

None of the following is built. Each one is checked live against `kkestell/coral-test` as it lands, and a unit test covers only the decisions it makes on its own.

- The GitHub API — no client exists yet.
- The agent, the model, and the deadline.
- The workflow and the composite actions. A real run is the only thing that exercises these at all.
