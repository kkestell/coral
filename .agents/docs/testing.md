# Testing

Where the tests live, how to run them, and the live checks. Full-suite commands are in `.agents/docs/development.md`. Coral runs the tests of repositories under review; those are not this project's.

## Frameworks and Tools

- `pytest`, configured in `pyproject.toml`. Plain `assert`; a failure that is the point of the test uses `pytest.raises`.
- No mocking library, and no fake of Coral's own code.

## Layout

- `tests/` at the repository root, one `test_<module>.py` per module under test.

## Kinds of Test

- Unit — one module, real input, no network, no credentials. Everything under `tests/`, the only tier `pytest` runs.
- Live — one real run against a real pull request in `kkestell/coral-test`, started by hand. Mandatory: a live check that is described or deferred instead of run has verified nothing, and an item is not done until it actually ran.

## Running Tests

- One file — `uv run pytest tests/test_schema.py`
- One test by name — `uv run pytest -k <name>`
- With printed output shown — add `-s`

## The Test Repository

`kkestell/coral-test` is public and exists for this and nothing else. Everything in it is disposable. Never point Coral at a repository whose pull requests somebody cares about.

One check runs elsewhere: the conversation bound needs a busy pull request, which `kkestell/coral-test` will never have, so it reads a public one in somebody else's repository — a read-only fetch from a developer machine with a `gh auth token` token.

A live run needs the two credentials under "Environment" in `.agents/docs/development.md`; the `gh` commands that set a check up and follow it are under "Commands" there. Its evidence is on the pull request, read there rather than in what the run printed.

## Fixtures and Test Data

- No fixture directory. A test writes its input inline as JSON-shaped dictionaries, validated through `pydantic.TypeAdapter` — the validator the agent framework itself uses. Schema payloads use the helpers in `tests/test_schema.py`.
- A real API response is captured from a real pull request, trimmed to a few nodes of each kind, and held inline with a comment saying where it came from and when. `tests/test_conversation.py` holds one.

## Writing a New Test

Real input rather than a mock, edge cases rather than another happy path, a case for every bug fixed. A test asserts what the contract promises.

## Not Covered by `pytest`

Each checked live, with unit tests covering only the decisions Coral makes on its own:

- The GitHub API.
- That `git diff` produces the format `coral/diff.py` parses.
- The workflow and the composite actions.
- The model call and which structured-output strategy the framework resolves to.
- The agent's shell on a real runner, and summarization firing mid-run.
- The deadline actually firing; the arithmetic has unit tests, a real firing does not.

### The Live Checks

Run in `kkestell/coral-test`, in order within their group, after pushing to the branch the example file pins. Groups accumulate: an item adds its checks when built, earlier groups stay.

**The walking skeleton**

1. Open a pull request changing one file. A review appears: one inline comment on a changed line, a summary naming the commit.
2. Comment `/coral`. The comment gets the `eyes` reaction and a second review appears — the issues-namespace reaction.
3. Reply `/coral` on the diff. Reaction and a third review — the pulls-namespace reaction.
4. Close a pull request and comment `/coral`. Resolve declines, later steps skip, no review, green run.
5. Open a pull request as a draft: a run is recorded with its job skipped, nothing posted. Mark it ready: a full run.

**Reading the conversation**

1. From a developer machine, fetch the conversation for `cli/cli` 10513 with the command in `.agents/docs/development.md`. Expect 84 threads, a bound reporting dropped comments, and a second page forced on the reviews connection by its 117 reviews.
2. Open a pull request. The review says it read a conversation of nothing — where a token that cannot reach `reviewThreads` goes red.
3. Comment `/coral`. The second review reads the first review's marker, names the commit, and counts the asking comment.
4. Reply to Coral's inline finding, resolve the thread, comment `/coral`. The third review reports the thread resolved and Coral's finding as Coral's.
5. Push a commit changing the line under Coral's finding, comment `/coral`. The review reports that thread outdated — the flag a finding's standing is decided by.

**The gatekeeper**

1. Comment a body carrying `/coral` only fenced, mid-sentence, and blockquoted. A run starts (the job condition is coarse), no reaction, no review, green.
2. Comment `/coral` alone on its own line with prose around it. Reaction and review — the control for the check above.
3. Comment `/coral`, then twice more while that run is going. The second run queues and is cancelled by the third. All three comments get the reaction and two reviews appear.
4. Reply `/coral` on the diff. Reaction in the pulls namespace, and no second reaction from a later run — checks `viewerHasReacted` answers for the token's account.
5. Close the pull request, comment `/coral`. Reaction, decline, no review, green.
6. Let Coral review a pull request, convert to draft, mark ready again: the run declines on the marker. Then comment `/coral` on the same commit and get a review — the automatic-paths-only half of that gate.
7. Open a pull request adding a generated file over 30,000 lines. One comment saying the change exceeds what Coral will read, no review, green.
8. From a fork under another account, open a pull request and comment `/coral`. The run declines on the fork gate. With no second account, the unit test covers it and this check is recorded as not run.

**The agent**

1. Open a pull request with a small real change. A model-written review appears whose summary and findings are about that change — also the evidence that the review object validated.
2. Watch the deadline fire: set `STEP_BUDGET_SECONDS` in `coral/deadline.py` to about 60, push, ask for a review of a change big enough to outlast it, and read the step log for the `RuntimeError` naming the elapsed seconds and the budget. Restore the constant afterwards. See the "Failure" group for what lands on the pull request.

**What Coral looks for**

Two of these read the review step's log rather than the pull request: a rejected finding is posted nowhere.

1. Open a pull request with a planted real defect. The review carries a finding at a sensible severity, its regression test in a collapsed block that renders as one on GitHub, and the log shows the verifier's confirming verdict.
2. Watch a rejection drop a finding: edit `coral/prompts/verify.md` to reject every finding, push, then open a pull request with a fresh defect — one Coral has already reviewed produces no findings to reject. Expect a review whose summary stands alone while the log names each drop and its reason. Revert afterwards.
3. Comment `/coral` on that pull request with no new commits. The second review repeats nothing from the first.
4. Open a pull request with a trivially clean change. No findings, and the review says there was nothing to find.

**Posting**

1. Open a pull request that gives Coral something to find. Inline comments land on the lines the findings name; whatever could not attach is in the summary with its file and line.
2. Force a rejection: edit `attachable` in `coral/diff.py`, shifting every line anchor past the end of its file, push, and review a change with a line finding. Expect one review carrying every finding in its summary, no inline comments, and a step-log warning holding GitHub's 422 body. Revert afterwards.
3. Comment `/coral`, wait for the review step to start, then close the pull request before it finishes. Green run, nothing posted, a log line saying it is no longer open.
4. Ask again on the clean pull request above, no new commits. The second review says everything is already said rather than that there was nothing to find — otherwise it reads as a retraction.

**Failure**

1. Set `STEP_BUDGET_SECONDS` in `coral/deadline.py` to about 60, push, and ask for a review of a change big enough to outlast it. Expect exactly one comment naming the elapsed seconds and the budget inside a fence, a red run, and a report-step log line saying the review step already reported. Restore the constant.
2. Put a `raise RuntimeError("live check")` at the top of `resolve()`, push, and comment `/coral`. Expect one comment saying the run failed with no reason and a link to the run, and a red run. In the same state, comment a mid-sentence mention of `/coral`: a red run and no comment. Revert.
3. Set the test repository's `OPENROUTER_API_KEY` secret to a broken value and ask for a review. Expect one comment carrying the provider's own error inside the fence.
4. A run that succeeds posts its review and nothing else, the report step skipped. The control for the three above.
