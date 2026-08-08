# Testing

Where the tests live, how to run them, and the live checks.

## Layout

- `tests/` at the repository root, one `test_<module>.py` per module under test.
- A unit test is one module, real input, no network, no credentials, no container, and no model call; the deadline and the cap have tests of their arithmetic alone. A failure the test is about uses `pytest.raises`.
- No fixture directory, and no test imports another. A test writes its input inline as JSON-shaped dictionaries validated through `pydantic.TypeAdapter`, with schema payloads from the helpers in `tests/test_schema.py`. A real API response is trimmed to a few nodes of each kind, commented with its source and date.
- A new test prefers edge cases to another happy path, and asserts what the contract promises.

## Running A Subset

- One file — `uv run pytest tests/test_schema.py`
- One test by name — `uv run pytest -k <name>`
- Printed output shown — add `-s`

## The Live Checks

One real run in `kkestell/coral-test`, started by hand, in order within a group, after pushing to the branch the example file pins.

**Reading the conversation**

1. Fetch `cli/cli` 10513 with the command in `.agents/docs/development.md`. Expect 84 threads, a bound reporting dropped comments, and its 117 reviews forcing a second page on that connection.
2. Comment `/coral`. The second review reads the first review's marker, names the commit, and counts the asking comment.
3. Reply to Coral's inline finding, resolve the thread, comment `/coral`. The third review reports the thread resolved and Coral's finding as Coral's.
4. Push a commit changing the line under Coral's finding, comment `/coral`. The review reports that thread outdated.

**The gatekeeper**

1. Comment a body carrying `/coral` only fenced, mid-sentence, and blockquoted. A run starts (the job condition is coarse), no reaction, no review, green.
2. Comment `/coral` alone on its own line with prose around it. Reaction and review — the control for the check above.
3. Comment `/coral` twice more while that run is going. The second run queues and is cancelled by the third; all three comments get the reaction and two reviews appear.
4. Reply `/coral` on the diff. Reaction in the pulls namespace, and no second reaction from a later run — `viewerHasReacted` answers for the token's account.
5. Close the pull request, comment `/coral`. Reaction, decline, no review, green.
6. Let Coral review a pull request, convert to draft, mark ready again: the run declines on the marker. Ask on the same commit and get a review.
7. Open a pull request adding a generated file over 30,000 lines. One comment saying the change exceeds what Coral will read, no review, green.

**What Coral looks for**

1. Open a pull request with a planted defect. The review carries a finding at a sensible severity, its regression test in a collapsed block that renders as one on GitHub, and the log shows the verifier's confirming verdict.
2. Edit `coral/prompts/verify.md` to reject every finding, push, then open a pull request with a fresh defect — one already reviewed produces no findings to reject. Expect a summary standing alone, and the log naming each drop and its reason. Revert.
3. Comment `/coral` with no new commits, on that pull request and on the clean one below. Neither second review repeats the first, and the clean one says everything is already said rather than nothing found.
4. Open a pull request with a trivially clean change. No findings, and the review says there was nothing to find.

**Posting**

1. Open a pull request that gives Coral something to find. Inline comments land on the lines the findings name; whatever could not attach is in the summary with its file and line.
2. Comment `/coral`, then close the pull request before the review job finishes. Green run, nothing posted, a log line saying it is no longer open.

**Failure**

1. Set the caller's `time_budget_minutes` to 1 and ask for a review of a change big enough to outlast it. Expect one comment naming the elapsed seconds and the budget inside a fence, the same `RuntimeError` in the review step's log, and a red run.
2. Put a `raise RuntimeError("live check")` at the top of `resolve()`, push, and comment `/coral`. Expect a red run and one comment saying the run failed with no reason, linking the run. In the same state, a mid-sentence mention of `/coral`: red run, no comment. Revert.
3. Set the test repository's `OPENROUTER_API_KEY` secret to a broken value and ask for a review. Expect one comment carrying the provider's own error inside the fence.
4. A run that succeeds posts its review and nothing else. The control for the three above.

**Shrink what a compromised agent gets**

1. Open a pull request that gives Coral something to find. Three jobs run, the review appears as before, and the review job's "GITHUB_TOKEN Permissions" log block lists `Contents: read` alone.
2. Add a step to the review job that posts a comment with `${{ github.token }}`, push, and ask for a review. Expect 403 and a red run; remove the step.
3. Replace the review job's `timeout-minutes` expression with 1, push, and ask for a review. GitHub kills the job mid-agent, no reason file crosses, and the publishing job's comment says the run failed with no reason. Revert.
4. Edit `attachable` in `coral/diff.py` to shift every line anchor past its file's end, push, and review a change with a line finding. Expect the 422: one review carrying every finding in its summary, no inline comments, and the warning in the publishing log. Revert.

**A key per run**

The secrets swap in `kkestell/coral-test`'s Actions secrets and its caller file.

1. Pass-through, the control: `OPENROUTER_API_KEY` set, the caller passing only `openrouter_api_key`. Open a pull request: a review appears, green run.
2. Minting: remove that secret, set `OPENROUTER_MANAGEMENT_KEY`, point the caller at `openrouter_management_key`, open a pull request. A review appears, green run. The key is in the clear only in the masking step's header, `***` in every later echo, and `GET /api/v1/keys` lists it named for the run, capped and expiring.
3. Expiry: a run's own key is unrecoverable, so rehearse by hand. Call `mint` from a developer machine with a short TTL, watch a completion succeed before `expires_at` and answer 401 after, then delete the key.
4. Misconfiguration: set both secrets and comment `/coral`. Red run, one comment saying to pass exactly one. Then a broken management key with no API key: red run, one comment carrying OpenRouter's own error.

**Take the agent out of the runner user**

Each of the first two needs a project of that language with a planted defect.

1. Python: open a pull request. The review carries the finding with its failing regression test, and the log's confirming verdict quotes its failure output. Coral logs no command text.
2. The same on a Node project with an `npm test` suite, then on a Go module with a `go test` suite.
3. The escape probe: patch `coral/review.py` to run `ps -e`, `ls /home/runner`, `cat /proc/1/comm`, `touch /opt/hostedtoolcache/probe`, and `docker ps` through the agent's backend. Expect the container's own processes alone, no `/home/runner`, an init as PID 1, a read-only refusal, and no `docker`. Revert.

**Structured output on any model**

1. From a developer machine, review a local clone with a planted defect on DeepSeek across three providers, `openai/gpt-5.5`, and `anthropic/claude-haiku-4.5`. Each returns a valid `Review`, tool calls ahead of the schema tool call.
2. A pull request with a planted defect on the default model still posts a confirmed finding.

**Configuration knobs**

The knobs swap in the caller file.

1. Name all three — a model the group above tested, an explicit effort, `time_budget_minutes: 10`. A review posts green, the review step's log carries the budget and the fetched profile, and the review job's timeout is 20 minutes.
2. Remove the `with:` block. A review posts as before, and the logged profile is a million-token window, 128,000 out, no temperature.
3. Set `model` to `~openai/gpt-mini-latest`. Red run, one comment refusing the alias and saying to name the model exactly.
4. Set `time_budget_minutes` to 355. Red run, one comment carrying the ceiling.
5. Set `model` to a name OpenRouter does not list. Red run, one comment saying so.

**A spend ceiling**

1. Pass-through mode, `spend_cap_dollars: "0.0005"` in the caller file, on a change big enough to take several steps. Red run, one comment naming what the review spent against the cap, and the same `RuntimeError` in the review step's log.
2. Minting mode, same cap. Red run, one comment — Coral's own total against the cap, or OpenRouter's refusal of the key if its accounting caught up first. `GET /api/v1/keys` shows the key minted at `0.0005`.
3. Remove the line. A review posts, nothing beside it, and the log carries the run's total.

**What a review cost**

1. Open a pull request on `kkestell/coral`. Its review's last line names what it cost, matching the review step's logged total.
