# Testing

How Coral is checked: the unit suite, and the real runs that are the only proof it works.

## The Unit Suite

- `tests/` at the repository root, one `test_<module>.py` per module under test. `coral/rehearse.py`
  is person-driven glue covered by rehearsal itself, so it has no `tests/test_rehearse.py`.
- A unit test is one module, real input, no network, no credentials, no container, and no model call. A failure the test is about uses `pytest.raises`.
- No fixture directory, and no test imports another. A test writes its input inline as JSON-shaped dictionaries validated through `pydantic.TypeAdapter`, with schema payloads from the helpers in `tests/test_schema.py`. A real API response is trimmed to a few nodes of each kind, commented with its source and date.
- A new test prefers edge cases to another happy path, and asserts what the contract promises.
- One file — `uv run pytest tests/test_schema.py`. One test by name — `uv run pytest -k <name>`. Printed output shown — add `-s`.

## A Green Suite Is Not Evidence

The suite covers pure functions over inputs written by hand. Almost everything Coral is happens outside it: what the model answers, what GitHub accepts, what Docker isolates, what the runner's environment holds, and how Actions wires the three jobs together. A change to any of that passes every test and is still broken. Never call work done because `pytest` is green.

## The Test Repository

`kkestell/coral-test` is where real runs happen. Coral is installed there as `.github/workflows/coral.yml`, pinned at `@main`, and it carries `python-fixture`, `node-fixture`, and `go-fixture` — one small project per language, each with its own test suite. Branches, pull requests, fixture code, the caller file, and the repository's Actions secrets are all yours to change.

- GitHub reads the caller file from the default branch, so push to the ref it pins before checking, and the Coral that answers a `/coral` comment is always the default branch's.
- Reviewing a pull request on `kkestell/coral` itself exercises the default branch's Coral against the proposed change. Use `coral rehearse` or pin `kkestell/coral-test` to the proposed commit to exercise changed Coral code before it reaches `main`.

## Live Checks

A live check is one real run, started by hand, read off the pull request, the run's log, or its artifacts. `.agents/docs/development.md` has the commands for opening a pull request, asking for a review, and following the run.

- Run one for every claim an item's done condition in `.agents/docs/roadmap.md` makes. Nothing is done until the run happened and its evidence was read; describing what a run would show is not a check.
- Check as you build, not once at the end. A run takes a few minutes and costs a fraction of a cent, and a failure found against one change is a failure you can attribute.
- Force the path you want. Editing a prompt, a constant, a step, or a secret to make a failure happen — then reverting — is how the failure paths get checked at all.
- For the main-push mode, push a planted defect to `main` in the test repository. Read the created issues and confirm no pull-request review exists; then revert the defect and close the issues.
- Rehearsing locally with `coral rehearse` is faster and cheaper than a run, and it is what a prompt change is judged by. It reaches no pull request and exercises no workflow, so it never stands in for a live check.
- The one thing the test repository cannot show is the conversation fetch paging, which needs a public pull request busier than any of its own. `.agents/docs/development.md` has that command; it reads and writes nothing.

Local runs need the credentials in `.env`, which `.agents/docs/development.md` lists.
