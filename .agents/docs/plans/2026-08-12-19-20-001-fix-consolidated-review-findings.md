# Fix the consolidated review findings

## Goal

Close the actionable findings in
`.agents/docs/reviews/2026-08-12-19-15-001-consolidated-review.md` without changing Coral's
architecture or adding speculative abstractions. Put routine tests around the paging, publishing,
and run-steering decisions that currently rely on no check; remove the duplication and dead code
the disposition refactor exposed; and make the remaining boundary messages, prose, comments, and
tests tell the truth.

This is maintenance before roadmap item 23. It does not add a roadmap item or change a roadmap done
condition.

## 1. Pin the conversation paging walk

Extend `tests/test_conversation.py` with a small `GitHub` subclass whose `graphql` answers from
prepared first and older pages. Build every node with the file's existing `comment_node`,
`review_node`, and `thread_node` helpers and pass the results through `fetch_conversation`; do not
mock a parser or the paging predicate.

Cover the behavior the isolated `wants_another_page` tests cannot show:

- The first query is followed by separate backwards walks for reviews, threads, and issue comments,
  and each later request carries that connection's preceding `startCursor` as `before`.
- Older nodes are prepended, leaving each returned connection in ascending order.
- Empty review bodies do not spend the review connection's comment bound, while every comment in a
  thread spends the thread connection's bound and each issue comment spends the issue-comment
  connection's bound.
- A connection that continues to report older pages stops after `MAX_PAGES`; the fake records the
  number of requests so the cap is asserted at the walk rather than only at the predicate.
- `Fetched.unfetched`, `reviewed_commits`, and the accumulated rate-limit accounting still come from
  the full set of pages the walk accepted.

Keep the existing predicate tests. They document the stop rule independently, while the new tests
pin how `fetch_conversation` applies it.

## 2. Pin review publication recovery

Import `post_review` in `tests/test_post.py` and replace the module docstring's stale explanation of
why it is untested. Add `GitHub` subclasses at the transport seam, following the existing
`Recording`, `Refusing`, and `Forbidding` pattern.

- On the first 422, record both posts and assert that the retry occurs exactly once at the same
  endpoint, with the pinned `commit_id` and `COMMENT` event, using `Payloads.demoted` rather than
  the anchored body.
- On a non-422 such as 403, assert with `pytest.raises` that the original `ApiError` propagates and
  that no second post occurs.

Do not broaden the retry policy or inspect GitHub's rejection text. Status 422 remains the sole
recovery condition required by the functional requirements.

## 3. Consolidate resolve's credential handoff

Extract the repeated management-key validation, encryption-key validation, mint, mask, and encrypt
sequence in `coral/resolve.py` into one helper taking the already validated job timeout and spend
cap. The helper returns the encrypted key or `None`; each accepted event path writes the output
when a value is returned. It reads the same environment values and uses the same run URL, TTL,
`reported` boundary, and masking order as the current copies.

Call the helper only after the push or pull-request gates pass and before any success output is
written. This preserves the two placement guarantees: declined work mints nothing, and a mint or
encryption failure cannot leave `proceed=true`.

The existing unit tests continue to pin key selection, handoff validation, TTL, cap, encryption,
and reported failures. The live checks in the final section cover the wiring that chooses this
helper from both accepted paths.

## 4. Make review-mode decisions explicit and tested

In `coral/review.py`, use exhaustive `match` for every `Subject` dispatch:

- Build the optional pull-request conversation section in `render_review_request` with `match`.
- Build the optional main-push duplicate-check instructions in `render_verification_request` with
  `match`.
- Replace `review()`'s `main_push` boolean and its three downstream branches with `match` at the
  credential check, duplicate-evidence construction, and payload-writing decisions.

Extract only the smallest helper needed to make main-push duplicate-evidence construction directly
testable. It takes the subject, GitHub token, and finding count; a pull-request subject yields no
evidence, while a push subject enforces `MAX_SEARCHES`, reads the staged event for repository
coordinates, and returns `IssueEvidence`. Interpolate `MAX_SEARCHES` in the failure message rather
than spelling `10` a second time.

Add tests in `tests/test_review.py` that:

- Stage a push artifact under `RUNNER_TEMP` and assert `read_subject` returns the exact
  `PushSubject` range without reading pull-request artifacts.
- Stage a small real Git repository, pull-request artifact, and conversation artifact and assert
  `read_subject` returns the `PullRequestSubject` with the merge base, title, body, and conversation.
- Exercise duplicate-evidence construction at `MAX_SEARCHES` and one finding past it, asserting the
  former succeeds and the latter raises before any `IssueEvidence` is built.
- Assert a pull-request subject needs neither a GitHub token nor duplicate evidence.

Keep the reviewer/verifier deadline behavior unchanged. Expand the comment beside the reviewer
deadline to state the seam precisely: the reviewer receives a fresh deadline for 65% of the step
budget, while the verifier receives the overall deadline whose clock began near the top of the
step. Do not add a wiring abstraction solely to test that arithmetic; `coral/deadline.py` owns and
already tests the calculation.

## 5. Remove the unused composed schema path

Delete `confirmed` from `coral/schema.py` and its imports. Retarget its cases in
`tests/test_schema.py` through `finding_dispositions` followed by `apply_dispositions`, the two
functions production uses. Preserve assertions for a confirmed main-push finding, a viewed
duplicate, an unchecked finding, unrelated or unviewed duplicate numbers, and conflicting
duplicate numbers.

The existing disposition-reason parameterization remains the direct test of why each finding is
kept or removed. No replacement convenience wrapper is added.

## 6. Describe a main push as the range Coral reviews

Use the existing `PushSubject.common` and `PushSubject.head` values to name a main-push range in the
reviewer and verifier requests. Change the heading and description from a single commit to the
range from the prior main tip through the pushed head. Keep the checkout description accurate: the
checkout is still at the pushed head.

Extend `issue_payloads` to receive both ends of the range and name that range in every issue body.
Update its production call and the tests in `tests/test_post.py`. Update the main-push rendering
assertions in `tests/test_review.py` and change `coral/prompts/verify.md` from "main commit" to
"main range."

Keep current documentation true in the same change:

- In `.agents/docs/functional-requirements.md`, say that a main-review issue body names the
  reviewed range.
- In `README.md`, describe a push as one reviewed range, including a multi-commit push, without
  disturbing the user's existing diagram additions.
- In `.agents/docs/development.md`, name the live-check command as reviewing a main range.

Do not change marker semantics: the pushed head remains the commit recorded by the marker and the
workflow's pinned output.

## 7. Remove small misleading shapes and harden one external boundary

Make these independent, local edits with their tests:

- Rename `IssueEvidence._open_issue` to `_is_open_issue`, return `bool`, and keep both callers
  reading the original validated dictionary. Adjust `tests/test_issues.py` only if a direct helper
  assertion is useful; the existing search and view cases already exercise ordinary issues,
  pull-request results, closed issues, and malformed entries.
- Rewrite `Ledger`'s docstring to say it is the mutable spend state shared by the two agent runs,
  rather than the only mutable object passed between modules.
- Validate the fields `facts_of` consumes from the selected OpenRouter model entry. A missing or
  malformed `top_provider`, context length, completion ceiling, or supported-parameter list raises
  one concise `RuntimeError` naming the model and the unreadable listing entry, rather than leaking
  `KeyError` or `TypeError`. Add malformed selected-entry cases to `tests/test_openrouter.py`; do
  not validate entries for models Coral did not select.
- Add a comment on the `Built` fake in `tests/test_agent.py` stating that its `with_config` and
  `invoke` methods intentionally mirror the LangChain object `_run` uses. Keep the fake small.

## 8. Exercise the remaining cheap control-flow seams

### Container execution

Add a minimal `Popen` stand-in in `tests/test_container.py` with in-memory stdout and stderr. Use
the real `ThreadPoolExecutor` and `drained` function, and intercept only `subprocess.Popen`.

- Assert a normal process result is drained and shaped with its exit code.
- Assert exit code 124 becomes Coral's timeout result.
- Assert runner-side `TimeoutExpired` kills and reaps the client before returning the same timeout
  result.

These tests do not claim Docker isolation or in-container process termination; those remain live
territory.

### CLI dispatch and logging

In `tests/test_cli.py`, add parameterized dispatch tests for `resolve`, `review`, `publish`, and
`rehearse`, intercepting the four handlers and driving `main()` through `sys.argv`. Assert each
subcommand invokes only its handler and that `main()` returns zero.

Replace the exact `logging.basicConfig` keyword-dictionary assertion with a behavior assertion that
Coral's info message reaches stderr while an `httpx` info message does not. Isolate and restore the
root and `httpx` logger state so the test does not disturb pytest's logging capture.

### Rehearsal exception

Amend `.agents/docs/testing.md` where it states the one-test-file-per-module convention: name
`coral/rehearse.py` as person-driven glue covered by rehearsal itself rather than by a
`tests/test_rehearse.py` file. Do not create a test file whose only purpose is satisfying the
convention.

## Explicit non-changes

- Keep the three accepted dependency pins and their tests unchanged.
- Keep duplicated test-data helpers local to each test module; no fifth copy is introduced here.
- Do not replace `_run`'s positional parameters with a dataclass. It still has two callers and no
  new caller is part of this work.
- Do not change the budget split, retry policy, conversation bounds, review payload schema, or
  agent capabilities.
- Do not chase a coverage percentage. The purpose of the added tests is to cover named decisions
  that currently have no routine evidence.

## Implementation order

1. Add the paging and review-post retry tests, then make only corrections those tests expose.
2. Extract the resolve credential handoff and perform the review-mode dispatch cleanup with the
   `read_subject` and finding-cap tests.
3. Remove `confirmed`, simplify issue validation, and correct the main-range prose and owned
   documentation.
4. Add the OpenRouter boundary, container execution, CLI, fake-contract, ledger-docstring, and
   rehearsal-documentation fixes.
5. Run the complete local checks, then exercise both credential-handoff paths live.

Keep each implementation slice with its tests. If commits are made, these five steps are suitable
commit boundaries, except documentation that must remain true should travel with the code it
describes.

## Validation

Run targeted tests while each slice is built:

```text
uv run pytest tests/test_conversation.py
uv run pytest tests/test_post.py
uv run pytest tests/test_review.py tests/test_schema.py tests/test_issues.py
uv run pytest tests/test_openrouter.py tests/test_container.py tests/test_cli.py tests/test_agent.py
```

Then run every routine local check:

```text
uv run pytest
uv run ruff format --check
uv run ruff check
uv run mypy
git diff --check
```

Inspect the final diff for stale single-commit main-push prose and hard-coded finding-cap text:

```text
rg -n "Main commit|This commit was pushed|main commit|more than 10 findings" \
  README.md .agents/docs coral tests
```

The remaining matches must describe a genuinely single commit, historical immutable artifacts, or
the marker's head-commit semantics. Do not edit the consolidated review or earlier plan/research
records.

Run the conversation paging command in `.agents/docs/development.md` against `cli/cli` 10513 and
confirm the bounded conversation still parses and the paging log is plausible. This is a read-only
live check of GitHub's current GraphQL shape, not a substitute for the new fake-driven walk tests.

For the credential-handoff extraction, run one real pull-request review and one planted-defect main
push in `kkestell/coral-test` with management-key mode enabled. Read the Actions logs and published
result for each: resolve mints and masks one key after its gates, review decrypts it, the pull
request posts a review, and the main push files its expected issue with the reviewed range. Revert
the planted defect and close its issue after reading the evidence.

The work is complete when all local checks pass, the read-only paging check succeeds, both live
review modes cross the consolidated credential handoff successfully, the main-push output names the
actual range, and every actionable finding above is either removed or covered by the routine test
that the review requested.
