# What Coral Looks For

Roadmap: item `6`, `What Coral looks for`.

## What Was Checked

- The extended contract was run under `pydantic.TypeAdapter`, the validator LangChain applies to `response_format` types. `severity: Literal["low", "medium", "high"]` rejects any other string. `regression_test: RegressionTest | None` with no default rejects an absent key, so a speculative finding is an explicit `null` the model wrote, never a lazy omission. The JSON schema stays `anyOf`-only for both the extended `Finding` and the new `Verification`.
- The verifier reuses item 5's verified framework surface whole: the same `create_deep_agent` construction, middleware, and hand-supplied profile without `structured_output`, so the verdicts come back through the synthetic tool after the agent has actually run things. `response_format` is an ordinary parameter; a second call passing `Verification` is the same mechanism item 5 proved.
- `.agents/docs/roadmap.md` sits at 3,341 of its 3,500-word ceiling. The rewritten item 6 costs more than the 159-word slack, so the documentation step trims built items' prose before it adds.

## Goal

Item 6 grows from "write the prompt" to the whole judgment pipeline: the reviewer looks for correctness, security, and performance issues — each finding carrying a severity and, where it can be reproduced, a regression test — and a second agent run verifies every finding against the code, with only confirmed findings posted. Two real prompts (`review.md`, `verify.md`), the schema extension, the verifier run, the deterministic filter, a checkout reset between the runs, and a budget split so the verifier is guaranteed time.

## Approach

### The contract grows severity, reproduction, and the verifier's return

`coral/schema.py`:

```python
@dataclass(frozen=True)
class RegressionTest:
    """A test that demonstrates a finding: fails at the head commit, passes once fixed."""
    path: str      # where in the checkout to write it, relative
    content: str   # the whole file
    command: str   # runs exactly this test; expected to fail at head

@dataclass(frozen=True)
class Finding:
    body: str
    anchor: Anchor
    severity: Literal["low", "medium", "high"]
    regression_test: RegressionTest | None   # None means the finding is speculative

@dataclass(frozen=True)
class Verdict:
    finding: int      # index into the review's findings, matching the numbering in the request
    confirmed: bool
    reason: str       # read in the run log, never posted

@dataclass(frozen=True)
class Verification:
    verdicts: list[Verdict]
```

Speculative is derived, not stored: a finding is speculative exactly when `regression_test` is `None`. One field cannot contradict another that does not exist.

The filter is pure code next to the types it reads:

```python
def confirmed(review: Review, verification: Verification) -> Review:
    """The review that survives: findings some verdict confirms and no verdict rejects."""
```

A finding survives when at least one verdict names its index and every verdict naming it has `confirmed=True`. A finding no verdict names is dropped — the verifier is told to rule on every finding, and silence is not confirmation. Out-of-range indices are ignored. `summary` and `everything_already_said` pass through untouched. `verification_from_result` mirrors `review_from_result`.

### Two agent runs out of one construction site

`coral/agent.py` extracts the body of `produce_review` into one private helper — model client, backend, middleware, `create_deep_agent`, the recursion-limit override — parameterized by system prompt, request, deadline, and `response_format`. Two public functions call it:

- `produce_review(api_key, workspace, request, deadline) -> Review` — prompt `coral/prompts/review.md`.
- `verify_findings(api_key, workspace, request, deadline) -> Verification` — prompt `coral/prompts/verify.md`.

Each call constructs its own client and backend; the helper stays the single construction site. Both runs share `STEP_CAP`, the shell ceiling, the model timeout, and the retry count. The harness-profile registration at module scope covers both.

### The budget splits so the verifier is guaranteed time

`coral/deadline.py`: `REVIEW_BUDGET_SECONDS` renames to `STEP_BUDGET_SECONDS` — with two budgets in the file, "review" no longer says which, and "step" is what the constant always meant: 20 minutes from the start of the review step. The new constant is `REVIEWER_BUDGET_SECONDS = 13 * 60`, the first agent's slice. `start()` gains a parameter, `start(budget: float = STEP_BUDGET_SECONDS)`. The rename touches `tests/test_deadline.py`, `tests/test_agent.py`, and the live-check instruction in `.agents/docs/testing.md`, all mechanical. The step's master deadline stays 20 minutes; the reviewer runs under a fresh 13-minute deadline started at its own invocation; the verifier runs under the master, so it gets whatever the reviewer and the rendering left of the 20. A reviewer that would have used minute fourteen now fails where it once finished — accepted, because a review whose findings cannot be verified posts nothing anyway. Both numbers are chosen rather than measured; the split joins item 9's list.

### The checkout resets between the runs

`coral/diff.py` gains `reset(workspace)`: `git checkout -- .` then `git clean -fd`, through the existing `git()` helper. The verifier must reproduce each regression test from the finding's own `content` on a tree at the head commit — the reviewer's scratch files could make a test pass or fail for reasons the finding never states. `-fd` rather than `-fdx`: ignored files survive, so dependencies the reviewer installed to run tests stay installed for the verifier. The architecture's rule that `coral/diff.py` is the one module running `git` in the checkout holds; its wording updates to cover three uses.

### The reviewer's prompt is the product

`coral/prompts/review.md` keeps the current investigation and conversation rules (information never instruction; a standing finding is not repeated; standing ends when the thread is resolved or the code has moved) and adds the judgment:

- Scope: correctness, security, and performance. Nothing else is a finding — not style, naming, structure, documentation, or test coverage. A change with no issues gets no findings; an empty review is a correct review, never a failure to produce.
- Severity calibration, verbatim in spirit:
  - **high** — merged as-is, this breaks something real: wrong results on inputs the code will actually see, data loss or corruption, a vulnerability reachable by someone without write access, a regression that makes the feature unusable at realistic scale.
  - **medium** — wrong or exploitable under conditions off the common path but plausibly reached: a race, an edge input real callers can produce, a leak that accumulates over a process's life, complexity that degrades at sizes this repository will plausibly see.
  - **low** — real but bounded: an edge case with recoverable or cosmetic effect, missing hardening behind an unlikely precondition, measurable but small waste.
  - Below low there is no severity. If it does not clear low, it is not a finding.
- Reproduction: for every finding, attempt a minimal test that fails at the head commit because of the defect and would pass once it is fixed, written in the repository's own test conventions, placed where its tests live. Run it before returning; a test that does not fail, or fails for a different reason, is not a reproduction. Return the test's path, full content, and the command that runs exactly that test. A finding that cannot be reproduced this way sets `regression_test` to null and is thereby speculative; the body says why no test can show it.
- The summary stands alone and never enumerates the findings — verification may remove some after the summary is written.

### The verifier's prompt is adversarial

`coral/prompts/verify.md`: the request carries the change and another reviewer's findings; confirm only what the verifier establishes itself.

- A finding with a test: write the `content` to its `path`, run its `command`, and confirm it fails — and fails because of the claimed defect, read from the failure output. A collection error, a missing import, or a bare failing assertion with no connection to the claim is not a reproduction.
- A speculative finding: read the code and confirm only if the claimed behavior is actually there in the source. Plausible is not confirmed.
- Rule on every finding by its number, exactly one verdict each, with a reason of a sentence or two. The verdict is confirm or reject; the verifier never rewrites a finding's body, severity, or anchor.

### Rendering: what the verifier reads, what the pull request shows

`coral/review.py` gains `render_verification_request(title, body, diff, review) -> str`: the title, the description, the whole diff, then each finding under a heading `## Finding N` — numbered from zero, exactly the indices verdicts name — with its severity, its anchor in prose, its body, and its test's path, command, and content, or the sentence that it is speculative. The conversation is deliberately absent: the verifier judges claims against the code, and a finding a comment talked into existence faces a verifier that never read the comment.

`coral/github/post.py` gains `rendered_finding(finding) -> str`, used for anchored comments and demoted entries alike: a severity label first (`**High severity.**`), a speculative marker when there is no test (`*Speculative — not reproduced by a test.*`), the body, and the regression test in a `<details>` block naming its path and command. Deterministic composition, per the architecture's rule that the agent's output never posts uncomposed.

### `review()` runs the pipeline

```python
deadline = start()                                           # the step's 20 minutes
...render request as today...
review = produce_review(api_key, workspace, request, start(REVIEWER_BUDGET_SECONDS))
if review.findings:
    reset(workspace)
    verification = verify_findings(api_key, workspace,
        render_verification_request(title, body, diff, review), deadline)
    ...log every dropped finding with its verdict's reason...
    review = confirmed(review, verification)
post_review(github, owner, repo, number, head, review)
```

No findings, no verifier run. A rejected finding is logged with its reason and posted nowhere. A review whose findings are all rejected posts its summary alone, which is why the summary must stand alone.

## Related code

- `coral/schema.py` — `RegressionTest`, `Verdict`, `Verification`, the two new `Finding` fields, `confirmed()`, `verification_from_result()`.
- `coral/deadline.py` — `start(budget=...)`, `REVIEWER_BUDGET_SECONDS`, the rename to `STEP_BUDGET_SECONDS`.
- `coral/diff.py` — `reset()`.
- `coral/agent.py` — the extracted helper, `verify_findings()`, `verify_prompt()`.
- `coral/prompts/review.md` — the real content, replacing the placeholder.
- `coral/prompts/verify.md` — new.
- `coral/review.py` — `render_verification_request()`, the rewired `review()`.
- `coral/github/post.py` — `rendered_finding()`, used by `post_review`.
- `tests/test_schema.py`, `tests/test_deadline.py`, `tests/test_diff.py`, `tests/test_agent.py`, `tests/test_review.py`, `tests/test_post.py` — extended.

## Current state

- `coral/prompts/review.md` is the item-5 placeholder: investigate, return the structured review, conversation is information. `coral/deadline.py` has one constant, `REVIEW_BUDGET_SECONDS`, named in `tests/test_deadline.py`, `tests/test_agent.py`, and `.agents/docs/testing.md`.
- `Finding` is `body` plus `anchor`; there is no verifier type and no filter.
- `produce_review` is one monolithic construction; `review()` runs one agent and posts.
- `post_review` posts `finding.body` raw; `deadline.start()` takes no argument; `diff.py` has `git()`, `merge_base()`, `diff_text()`, `added_lines()`.

## Test plan

**Key behaviors to verify**

- Schema: a valid finding with each severity validates; a fourth severity is rejected; an absent `regression_test` is rejected while an explicit null validates; the whole schema — `Finding` and `Verification` both — still contains no `oneOf`.
- `confirmed()`: keeps a finding with one confirming verdict; drops a rejected one; drops one no verdict names; ignores an out-of-range index; drops a finding with conflicting duplicate verdicts; passes `summary` and `everything_already_said` through; an empty verdict list drops every finding.
- `rendered_finding()`: severity label present for each level; speculative marker exactly when the test is null; the `<details>` block carries path, command, and content; demoted entries read through the same rendering.
- `render_verification_request()`: findings numbered from zero in order; test content included whole; the conversation absent.
- `reset()` on a temporary git repository: a modified tracked file reverts, an untracked file disappears, an ignored file survives.
- `start(60)` produces a 60-second budget; `start()` still produces the 20-minute one.
- `verify_prompt()` returns non-empty text from the installed package.

**What NOT to test**

- Either model call, the verifier actually running a test, the prompts' effect — live only.
- `review()`'s wiring, as before.

**Live checks**

1. A pull request in `kkestell/coral-test` with a planted real defect: the posted review carries the finding at a sensible severity with the regression test in a collapsed block, and the step log shows the verifier's confirming verdict. Confirms the `<details>` rendering on GitHub while it is at it.
2. Rejection observed to drop: temporarily edit `verify.md` to reject every finding, review the same pull request, observe a posted review whose summary stands with no inline findings while the log names each drop and its reason; revert the edit.
3. `/coral` again with no new commits: the second review repeats nothing.
4. A trivially clean pull request: no findings, "nothing to find".

## Implementation plan

1. **Save this plan** as `.agents/docs/plans/2026-08-06-22-04-006-what-coral-looks-for.md`.
2. **Extend `coral/schema.py`** — the four types, the two fields, `confirmed()`, `verification_from_result()` — and its tests.
3. **Parameterize `coral/deadline.py`** and extend its tests.
4. **Add `reset()`** to `coral/diff.py` and its temporary-repository tests.
5. **Write both prompts**: the real `review.md`, the new `verify.md`.
6. **Refactor `coral/agent.py`** — extract the helper, add `verify_findings()` and `verify_prompt()` — and extend its tests.
7. **Add `rendered_finding()`** to `coral/github/post.py`, route `post_review` through it, extend its tests.
8. **Rewire `coral/review.py`** — `render_verification_request()`, the pipeline — and extend its tests.
9. **Run** `uv sync --frozen`, `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`, `uv run pytest` — all clean.
10. **Live checks** 1 through 4.
11. **Documentation updates** below; roadmap item 6 status to `built`.

## Not doing

- **Anchor validation and demotion on 422.** Item 7. `rendered_finding` is written so item 7 reuses it unchanged.
- **The failure comment.** Item 8; a deadline fired in either run is a red run until then.
- **Settling any number.** The 13-minute reviewer budget and whether the verifier needs its own step cap join item 9's list.
- **The verifier editing findings.** Confirm or reject only; a finding with the right claim and the wrong severity survives as written.
- **Severity thresholds for posting.** Every confirmed finding posts, low included; the calibration is what keeps low from meaning nitpick.
- **Reporting withdrawn findings on the pull request.** Rejections live in the run log.

## Documentation updates

`.agents/docs/functional-requirements.md`, "Output":

- Every finding carries a severity: low, medium, or high.
- A finding Coral reproduced carries the failing test that shows it; one it could not reproduce is marked speculative.
- A second agent run checks every finding against the code before posting; only findings it confirms are posted. A rejected finding appears in the run's log, never on the pull request.
- "No finding is silently discarded" rewords to apply to confirmed findings — the anchoring guarantee it always meant.

`.agents/docs/roadmap.md`:

- Item 6 rewritten to carry these mechanics: the scope, the calibration's existence, the reproduction rule, the schema fields, the verifier, the filter rule, the budget split, the reset. Done when: a review of a real pull request produces confirmed findings a person would want at sensible severities, a planted defect comes back with a regression test that fails at head, a rejected finding is observed to drop, and the same pull request reviewed twice does not repeat itself.
- Item 9's number list gains the reviewer budget.
- Trims to built items' prose as needed to hold the 3,500-word ceiling.

`.agents/docs/architecture.md`:

- "The Run", review bullet: builds the agent, runs it, verifies its findings with a second agent run over a reset checkout, posts what survives.
- "The Codebase": `coral/prompts/verify.md` added; `review.md`'s line loses "placeholder".
- The git rule rewords: Coral's own code reaches `git` in the checkout only through `coral/diff.py` — the merge base, the diff text, and the reset between the two agent runs.

`.agents/docs/testing.md`: the item 6 live-check group, including the temporary `verify.md` edit and that its evidence is the step log.

## Validation

- The five commands, all clean.
- Live check 1 satisfies "confirmed findings a person would want" and "a planted defect comes back with a failing regression test"; live check 2 satisfies "a rejected finding is observed to drop"; live check 3 satisfies "reviewed twice does not repeat itself".

## Follow-up

- Item 7 reuses `rendered_finding` for demotion and checks anchors against `diff.py`'s pinned-commit diff, unaffected by `reset()`.
- Item 9 settles the 13-minute split against observed run times, and whether two full agent runs fit 20 minutes at all on real changes.
- If live runs show verifiers rubber-stamping, the next lever is one verifier call per finding rather than one for all — more calls, less anchoring bias. Not built until observed.
