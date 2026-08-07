# Testing

Where the tests live, how to run them, and the live checks. Full-suite commands are in `.agents/docs/development.md`. Coral runs the tests of repositories under review; those are not this project's.

## Frameworks and Tools

- `pytest`, configured in `pyproject.toml`. A failure that is the point of the test uses `pytest.raises`.

## Layout

- `tests/` at the repository root, one `test_<module>.py` per module under test.

## Kinds of Test

- Unit — one module, real input, no network, no credentials. Everything under `tests/`.
- Live — one real run in `kkestell/coral-test`, started by hand.

## Running Tests

- One file — `uv run pytest tests/test_schema.py`
- One test by name — `uv run pytest -k <name>`
- Printed output shown — add `-s`

## The Test Repository

`kkestell/coral-test` is public, disposable, and exists for this alone. Never point Coral at a repository whose pull requests somebody cares about.

A live run needs the credentials under "Environment" in `.agents/docs/development.md`, and the `gh` commands are under "Commands" there. Evidence is on the pull request, not in what the run printed.

## Fixtures and Test Data

- No fixture directory. A test writes its input inline as JSON-shaped dictionaries, validated through `pydantic.TypeAdapter`. Schema payloads use the helpers in `tests/test_schema.py`.
- A real API response is trimmed to a few nodes of each kind and held inline with a comment saying where it came from and when.

## Writing a New Test

Real input rather than a mock, edge cases rather than another happy path, a case for every bug fixed. A test asserts what the contract promises.

## Not Covered by `pytest`

Each checked live; unit tests cover only the decisions Coral makes on its own:

- The GitHub API.
- That `git diff` produces the format `coral/diff.py` parses.
- The workflow and the composite actions.
- The model call and which structured-output strategy the framework resolves to.
- The agent's shell on a real runner, and summarization firing mid-run.
- The deadline firing; only its arithmetic has unit tests.

### The Live Checks

Run in `kkestell/coral-test`, in order within their group, after pushing to the branch the example file pins. Groups accumulate as items are built.

**The walking skeleton**

1. Open a pull request as a draft: a run is recorded with its jobs skipped, nothing posted. Mark it ready: a full run.

**Reading the conversation**

1. From a developer machine, fetch `cli/cli` 10513 with the command in `.agents/docs/development.md`. Expect 84 threads, a bound reporting dropped comments, and a second page forced on the reviews connection by its 117 reviews.
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
6. Let Coral review a pull request, convert to draft, mark ready again: the run declines on the marker. Comment `/coral` on the same commit and get a review — the automatic-paths-only half of that gate.
7. Open a pull request adding a generated file over 30,000 lines. One comment saying the change exceeds what Coral will read, no review, green.
8. From a fork under another account, open a pull request and comment `/coral`. The run declines on the fork gate. With no second account, recorded as not run; the unit test covers it.

**The agent**

1. Open a pull request with a small real change. A model-written review appears about that change — the evidence the review object validated.
2. Watch the deadline fire, on the run "Failure" 1 sets up: the step log holds the `RuntimeError` naming the elapsed seconds and the budget.

**What Coral looks for**

Two of these read the review step's log rather than the pull request: a rejected finding is posted nowhere.

1. Open a pull request with a planted real defect. The review carries a finding at a sensible severity, its regression test in a collapsed block that renders as one on GitHub, and the log shows the verifier's confirming verdict.
2. Watch a rejection drop a finding: edit `coral/prompts/verify.md` to reject every finding, push, then open a pull request with a fresh defect — one already reviewed produces no findings to reject. Expect a summary standing alone, and the log naming each drop and its reason. Revert.
3. Comment `/coral` on that pull request with no new commits. The second review repeats nothing from the first.
4. Open a pull request with a trivially clean change. No findings, and the review says there was nothing to find.

**Posting**

1. Open a pull request that gives Coral something to find. Inline comments land on the lines the findings name; whatever could not attach is in the summary with its file and line.
2. Comment `/coral`, wait for the review job to start, then close the pull request before it finishes. Green run, nothing posted, a log line saying it is no longer open.
3. Ask again on the clean pull request above, no new commits. The second review says everything is already said rather than that there was nothing to find; otherwise it reads as a retraction.

**Failure**

1. Set `STEP_BUDGET_SECONDS` in `coral/deadline.py` to about 60, push, and ask for a review of a change big enough to outlast it. Expect exactly one comment naming the elapsed seconds and the budget inside a fence, and a red run. Restore the constant.
2. Put a `raise RuntimeError("live check")` at the top of `resolve()`, push, and comment `/coral`. Expect a red run and one comment saying the run failed with no reason, linking the run. In the same state, a mid-sentence mention of `/coral`: red run, no comment. Revert.
3. Set the test repository's `OPENROUTER_API_KEY` secret to a broken value and ask for a review. Expect one comment carrying the provider's own error inside the fence.
4. A run that succeeds posts its review and nothing else. The control for the three above.

**Shrink what a compromised agent gets**

1. Open a pull request that gives Coral something to find. Three jobs run, the review appears as before, and the review job's "GITHUB_TOKEN Permissions" log block lists `Contents: read` and nothing else.
2. Add a step to the review job that posts a comment with `${{ github.token }}`, push, and ask for a review. Expect 403 and a red run; remove the step.
3. Set the review job's `timeout-minutes` to 1, push, and ask for a review. GitHub kills the job mid-agent, no reason file crosses, and the publishing job's comment says the run failed with no reason. Restore it.
4. Force the 422: edit `attachable` in `coral/diff.py` to shift every line anchor past its file's end, push, and review a change with a line finding. One review carries every finding in its summary, no inline comments, and the publishing job's log holds the 422 warning. Revert.

**A key per run**

The secrets swap in `kkestell/coral-test`'s Actions secrets and its caller file.

1. Pass-through, the control: `OPENROUTER_API_KEY` set, the caller passing only `openrouter_api_key`. Open a pull request: a review appears, green run.
2. Minting: remove that secret, set `OPENROUTER_MANAGEMENT_KEY`, point the caller at `openrouter_management_key`, open a pull request. A review appears, green run. The key shows in the clear once, in the masking step's own header, and `***` in every later echo — the residue `.agents/docs/architecture.md` accounts for. Under the management key, `GET /api/v1/keys` lists a key named for the run, capped and expiring as `coral/openrouter.py` sets.
3. Expiry: a run's own key is unrecoverable by design, so rehearse the path by hand. Call `mint` from a developer machine with a short TTL patched in, watch a completion succeed before `expires_at` and answer 401 after, then delete the key.
4. Misconfiguration: set both secrets and comment `/coral`. Red run, one comment saying to pass exactly one. Then a broken management key with no API key: red run, one comment carrying OpenRouter's own error.
