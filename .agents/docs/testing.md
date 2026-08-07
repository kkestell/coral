# Testing

Where the tests live, how to run them, what a new test looks like, and the live checks. Full-suite commands are in `.agents/docs/development.md`. Coral runs the tests of repositories under review; those are not this project's tests.

## Frameworks and Tools

- `pytest`, configured in `pyproject.toml`. Plain `assert`; a failure that is the point of the test uses `pytest.raises`.
- No mocking library, and no fake of Coral's own code.

## Layout

- `tests/` at the repository root, one `test_<module>.py` per module under test.

## Kinds of Test

- Unit — one module, real input, no network, no credentials. Everything under `tests/`, and the only tier `pytest` runs.
- Live — one real run against a real pull request in `kkestell/coral-test`, started by hand. Anything crossing into GitHub, the model, or the workflow is checked this way; there is no other way.

## Running Tests

- One file — `uv run pytest tests/test_schema.py`
- One test by name — `uv run pytest -k <name>`
- With printed output shown — add `-s`

## The Test Repository

`kkestell/coral-test` is public and exists for this and nothing else. Everything in it is disposable: set up what the check needs, delete it afterward or not. Use it — never point Coral at a repository whose pull requests somebody cares about, and never describe what a run would do in place of making one.

One live check runs elsewhere: exercising the conversation bound needs a busy pull request, which `kkestell/coral-test` will never have, so that check reads a public pull request in somebody else's repository. Allowed because it is a read-only fetch from a developer machine with a `gh auth token` token.

A live run needs the two credentials under "Environment" in `.agents/docs/development.md`, and its evidence is on the pull request — the review, the reaction, the failure comment. Read it there rather than trusting what the run printed.

`gh` sets a check up and follows it:

- Open a pull request — `gh pr create --repo kkestell/coral-test --base main --head <branch> --title <title> --body <body>`
- Ask for a review — `gh pr comment --repo kkestell/coral-test <number> --body '/coral'`
- Watch the run — `gh run list --repo kkestell/coral-test`
- Read the review — `gh pr view --repo kkestell/coral-test <number> --comments`

## Fixtures and Test Data

- No fixture directory. A test writes its input inline as the JSON-shaped dictionaries the model or API would produce, validated through `pydantic.TypeAdapter` — the validator the agent framework itself uses. Schema tests build payloads with the helpers in `tests/test_schema.py`.
- A real API response is captured from a real pull request, trimmed by hand to a few nodes of each kind, and held inline with a comment saying where it came from and when. `tests/test_conversation.py` holds one.

## Writing a New Test

Real input rather than a mock, edge cases rather than another happy path, and a case for every bug that gets fixed. A test asserts what the contract promises, not what a dependency happens to do; where recording a dependency's behavior is the point, a comment says so, so tightening it later reads as deliberate.

A module that talks to GitHub, the model, or the runner gets both: unit tests over real input for its own decisions, and a live run for whether the far side behaves as assumed. A mock of the far side only confirms what was already believed.

## Not Covered by `pytest`

Each checked live, with unit tests covering only the decisions Coral makes on its own:

- The GitHub API.
- That `git diff` produces the format `coral/diff.py` parses.
- The workflow and the composite actions.
- The agent, the model, and the deadline. Not built.

### The Live Checks

Run in `kkestell/coral-test`, in order within their group, after pushing to the branch the example file pins. Evidence is on the pull request, not the run log. Groups accumulate: an item adds its checks when built, and earlier groups stay.

**The walking skeleton**

1. Open a pull request changing one file. A review appears: one inline comment on a changed line, a summary naming the commit.
2. Comment `/coral`. The comment gets the `eyes` reaction and a second review appears — the issues-namespace reaction.
3. Reply `/coral` on the diff. Reaction and a third review — the pulls-namespace reaction.
4. Close a pull request and comment `/coral`. Resolve declines, later steps skip, no review, green run.
5. Open a pull request as a draft: a run is recorded with its job skipped, nothing posted. Mark it ready: a full run — the control telling a rejected delivery from a dropped one.

**Reading the conversation**

1. From a developer machine, fetch the conversation for `cli/cli` 10513 with the command in `.agents/docs/development.md`. Expect: 84 threads, mostly resolved and outdated, a bound reporting dropped comments, no already-reviewed commits. Its 117 reviews force a second page on the reviews connection.
2. Open a pull request. The review says it read a conversation of nothing — this is where a token that cannot reach `reviewThreads` goes red.
3. Comment `/coral`. The second review reads the first review's marker, names the commit, and counts the asking comment.
4. Reply to Coral's inline finding, resolve the thread, comment `/coral`. The third review reports the thread resolved, the reply as somebody else's, and Coral's finding as Coral's.
5. Push a commit changing the line under Coral's finding, comment `/coral`. The review reports that thread outdated — the flag a finding's standing is decided by.

**The gatekeeper**

1. Comment a body carrying `/coral` only fenced, mid-sentence, and blockquoted. A run starts (the job condition is coarse), no reaction, no review, green.
2. Comment `/coral` alone on its own line with prose around it. Reaction and review — the control for the check above.
3. Comment `/coral`, then twice more while that run is going. The second run queues and is cancelled by the third. All three comments get the reaction, two reviews appear — the reaction pass reaching a request the payload cannot.
4. Reply `/coral` on the diff. Reaction in the pulls namespace, and no second reaction from a later run — checks `viewerHasReacted` answers for the token's account.
5. Close the pull request, comment `/coral`. Reaction, decline, no review, green.
6. Let Coral review a pull request, convert to draft, mark ready again. The run declines on the marker. Then comment `/coral` on the same commit and get a review — the automatic-paths-only half of that gate.
7. Open a pull request adding a generated file over 30,000 lines. One comment saying the change exceeds what Coral will read, no review, green.
8. From a fork under another account, open a pull request and comment `/coral`. The run declines on the fork gate. Where no second account exists, the unit test covers it and this check is recorded as not run.
