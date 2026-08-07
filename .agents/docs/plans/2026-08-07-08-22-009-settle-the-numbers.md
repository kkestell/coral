# Settle the Numbers

Roadmap: item `9`, `Settle the numbers`.

## What Was Checked

- Every number item 9 lists is a module-level `Final` in the module that owns it, each with a comment reading some form of "chosen rather than measured; item 9 settles it": `coral/github/conversation.py` (`MAX_COMMENTS`, `MAX_CHARACTERS`), `coral/resolve.py` (`MAX_CHANGED_FILES`, `MAX_CHANGED_LINES`), `coral/deadline.py` (`STEP_BUDGET_SECONDS`, `REVIEWER_BUDGET_SECONDS`), `coral/agent.py` (`MODEL_TIMEOUT_MILLISECONDS`, `STEP_CAP`, `SHELL_CEILING_SECONDS`, `MODEL_RETRIES`), `coral/environment.py` (`KEEP`). None of this needs a new abstraction; every number stays exactly where it is and keeps its type. Only the comment above each one changes, from "chosen rather than measured" to the reason.
- What a live run already surfaces in its own log, unprompted: `coral/github/conversation.py:499` logs query count, GraphQL point cost, and points remaining after a fetch — enough to see how far a real conversation is from the 200-comment/400,000-character bound, but not whether the bound itself is right, since `bound()` never logs what it dropped in the same line. `coral/agent.py:205` and `:207` log the workspace and the elapsed seconds a run took, nothing about how many steps it used. `coral/github/post.py:178` logs a 422's full body on rejection.
- Nothing today logs how many steps a run took, how long any one shell command inside it ran, or which upstream provider answered a model call. `STEP_CAP`, `SHELL_CEILING_SECONDS`, and the "which provider serves the alias" bullet under "Undecided" in `.agents/docs/architecture.md` are unmeasurable as the code stands; every other number already has a real number to look at once a live run happens, just not one anybody recorded.
- `coral/agent.py`'s `caught` wraps every tool function `FilesystemMiddleware` registers (`read_file`, `write_file`, `ls`, `execute`, and the rest) to hand a tool's own exception back to the model as a string instead of ending the run. It is the one place already sitting between every tool call and the model, which makes it the cheap place to add a timing log too, one line, no new wrapper.
- `_run` in `coral/agent.py` returns the whole final state as `result: dict[str, Any]`, including `result["messages"]`, the full transcript LangGraph built. `len(result["messages"])` is not the same number `STEP_CAP` bounds — `recursion_limit` counts graph super-steps, and one super-step can add more than one message — but it moves the same direction a real run's step count would, and a `Final` this generous does not need more precision than that to settle.
- `langchain_openrouter`'s `ChatOpenRouter` stamps `response_metadata["model_provider"] = "openrouter"` on every response — OpenRouter's own name for itself, not the upstream provider (Fireworks, Together, whoever actually served the request) the "Undecided" bullet asks about. What it does carry is `response_metadata["id"]`, OpenRouter's generation id, which OpenRouter's own activity dashboard looks up by account. No field in `langchain_openrouter` names the upstream provider directly; reading it is a browser action against the dashboard, not a log line Coral can print.
- `coral/github/post.py`'s 422 retry already logs the full rejection body (`log.warning("GitHub rejected the anchored review: %s", rejection.body)`), unchanged since item 7. Item 7's own plan called this the moment that would answer "whether GitHub's 422 names the offending anchor," but `.agents/docs/architecture.md`'s "Undecided" section still carries that bullet — the live check that forced a 422 ran, but nobody read the logged body back into the document afterward. Settling it here costs one more forced rejection and one line in this document, not new code.
- `kkestell/coral-test` carries one language's test suite (Python, per `.agents/docs/testing.md` and `.agents/docs/development.md`); every live check to date has run Coral's shell against `pytest`. The shell environment allowlist (`CI`, `HOME`, `LANG`, `LC_ALL`, `PATH`, `TERM`, `TMPDIR`) has a measured reason for a Python test suite and none yet for anything else the "real pull requests" in item 9's own wording implies. `AGENTS.md` allows editing `kkestell/coral-test` freely; adding one small Node file and one small Go file to it, each with a trivial failing test, is within that.
- `.agents/docs/roadmap.md` is 3,498 words of its 3,500 ceiling; `.agents/docs/testing.md` is 1,499 of 1,500. Both are effectively full. Item 9's own paragraph (`roadmap.md` lines 179–188) is about 130 words describing what is not yet measured; once measured, that whole paragraph collapses to a one-line status pointing at the items that carry the real numbers, which is where the room for this item's edits to items 3–6 comes from. `testing.md` gains nothing: item 9 checks no new behavior, only retunes constants an existing behavior already exercises, so it adds no live-check group of its own.
- `.agents/docs/architecture.md` is 1,409 of 1,500, with two bullets under "Undecided." Both get answered here (the 422 body, the provider), which empties the section rather than shrinking it by one line.

## Goal

Every number named in item 9 carries a reason a reader can check, written where the number already lives. Both bullets under "Undecided" in `.agents/docs/architecture.md` are answered, and the section is empty. No constant moves unless a real run shows the current value wrong; most of this item is discovering that the chosen values already hold and saying why, not raising or lowering them.

## Approach

### Three log lines, nowhere else

`coral/agent.py`:

- `caught` gains a start time and one more `log.info` call, logging the tool's name and elapsed seconds after it returns, success or caught failure alike. This is what a live run needs to answer whether `SHELL_CEILING_SECONDS` (300) is close to a real command's worst case, and it is a permanent line — the same kind of visibility the elapsed-seconds line for the whole run already gives, not a debug print to delete afterward.
- The existing `log.info("The agent finished after %.0f seconds.", deadline.elapsed())` in `_run` gains the transcript length: `"...after %.0f seconds and %d messages."` One number, appended to a line already there, answering how far a real run sits from `STEP_CAP` (200) without claiming to be the exact count `recursion_limit` bounds.

Nothing else in the source changes before the live runs. `MAX_COMMENTS`, `MAX_CHARACTERS`, `MAX_CHANGED_FILES`, `MAX_CHANGED_LINES`, `STEP_BUDGET_SECONDS`, `REVIEWER_BUDGET_SECONDS`, `MODEL_TIMEOUT_MILLISECONDS`, `MODEL_RETRIES`, and `KEEP` are read against what a live run shows and changed only if a run shows the current value is wrong.

### What each number is checked against

- **Conversation bound** (`MAX_COMMENTS` 200, `MAX_CHARACTERS` 400,000) — the existing "Reading A Conversation By Hand" command in `.agents/docs/development.md` against a real busy pull request, reading the logged query count, point cost, and points remaining. `kkestell/coral-test` will never be busy enough on its own, which is why that command already reads someone else's public repository instead.
- **Size backstop** (`MAX_CHANGED_FILES` 300, `MAX_CHANGED_LINES` 30,000) — a pull request in `kkestell/coral-test` near each threshold, not just past it (item 4's live check already covers well past it), read against how large a change Coral's own runs handle without the deadline or the shell ceiling becoming the real limit first.
- **Step budget and reviewer's slice** (`STEP_BUDGET_SECONDS` 20 minutes, `REVIEWER_BUDGET_SECONDS` 13 minutes) — elapsed seconds and message count off a handful of real reviews spanning trivial to near the size backstop, read against how much of the 20 minutes and the 13-minute reviewer slice each actually used.
- **Step cap** (`STEP_CAP` 200) — message counts from the same runs, read against how close any of them came to 200.
- **Model timeout and retries** (`MODEL_TIMEOUT_MILLISECONDS` 180,000, `MODEL_RETRIES` 1) — no real run is expected to hit either; the reason on record is already the arithmetic in `coral/agent.py`'s comment (one retry keeps the worst in-flight overshoot at about eight and a half minutes, inside the ten minutes of headroom before the job's own 30-minute timeout) and a real run either confirms that arithmetic held or shows a retry actually firing, which the model client would surface as a longer elapsed time with no other explanation.
- **Shell ceiling** (`SHELL_CEILING_SECONDS` 300) — the new per-tool-call timing line, read for the longest single command across the same runs, including the Node and Go fixtures added to `kkestell/coral-test` for this item.
- **Shell environment allowlist** (`KEEP`) — the same Node and Go runs, read for whether their test runners fail for a missing environment variable the allowlist does not carry. `CI`, `HOME`, `LANG`, `LC_ALL`, `PATH`, `TERM`, and `TMPDIR` is the hypothesis; a real failure is what would add a name to it, and none is added speculatively.
- **The 422 body** — item 7's forced-rejection live check, run again, reading `coral/github/post.py`'s already-logged warning for whether GitHub's body names the anchor it rejected.
- **Which provider serves the alias** — one live review, read afterward on OpenRouter's own activity dashboard for the account the API key belongs to, which names the upstream provider per request. No code carries this; the dashboard is the only place it is visible.

## Related code

- `coral/agent.py` — the timing line in `caught`, the message count appended to `_run`'s existing log line, the comment above `MODEL_TIMEOUT_MILLISECONDS`/`STEP_CAP`/`SHELL_CEILING_SECONDS`/`MODEL_RETRIES` rewritten with the measured reason.
- `coral/github/conversation.py`, `coral/resolve.py`, `coral/deadline.py`, `coral/environment.py` — the comment above each `Final` rewritten the same way; no code changes expected unless a run shows a value wrong.
- No test file changes are expected; item 9 adds no unit-testable behavior.

## Current state

- Every number item 9 lists is in place and working, each justified in its own comment by the arithmetic or judgment that chose it, none by a measurement.
- `.agents/docs/architecture.md`'s "Undecided" section carries both bullets unanswered.
- `kkestell/coral-test` holds only Python fixtures.
- Nothing in the source logs a run's step count, a single command's duration, or which provider served a model call.

## Test plan

**Key behaviors to verify**

None. This item changes no code path a unit test exercises — two log lines and a run of comments — so nothing here is new to `pytest`.

**What NOT to test**

- The timing and message-count log lines. Reading them on a live run is the whole point; asserting their format in `pytest` would test a log message, not a behavior.

**Live checks**

Run in `kkestell/coral-test` and, for the conversation bound, against the public pull request `.agents/docs/development.md` already names.

1. Fetch the conversation for `cli/cli` 10513 as `.agents/docs/development.md` already documents. Read the logged query count, point cost, and comment/character totals against the 200/400,000 bound.
2. Open pull requests in `kkestell/coral-test` sized trivial, small-real-change, and near each size-backstop threshold (300 files, 30,000 lines) without exceeding it. For each, read the review step's log for elapsed seconds, message count, and the longest single tool-call duration.
3. Add a small Node fixture and a small Go fixture to `kkestell/coral-test`, each with one failing test, and ask for a review of each. Read whether either test runner fails for a missing environment variable.
4. Repeat item 7's forced-422 live check (temporarily shifting every line anchor past the end of its file in `coral/diff.py`, reviewing a change with a line finding, reverting afterward) and read the logged rejection body for whether it names the anchor GitHub rejected.
5. Take any one of the reviews from check 2 and look up its request on OpenRouter's activity dashboard for the account the API key belongs to, reading which upstream provider served it.

## Implementation plan

1. **Save this plan** as `.agents/docs/plans/2026-08-07-08-22-009-settle-the-numbers.md`.
2. **Add the two log lines** in `coral/agent.py` — the per-tool-call timing in `caught`, the message count appended to `_run`'s finishing line.
3. **Run** `uv sync --frozen`, `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`, `uv run pytest` — all clean.
4. **Add the Node and Go fixtures** to `kkestell/coral-test`.
5. **Live checks** 1 through 5, recording what each one shows.
6. **Decide each number** against what the checks showed: keep, or change and say why, one at a time.
7. **Documentation updates** below; roadmap item 9 status to `verified`.

## Not doing

- **Raising or lowering a number with no live run behind it.** Every change here traces to one of the five live checks; a number nothing contradicted stays exactly where it is.
- **A permanent log line for the OpenRouter generation id or provider.** The dashboard already shows it per request; Coral logging an id nothing else reads is a line bought for a one-time question.
- **Widening the shell environment allowlist speculatively.** Only a real failure in check 3 adds a name; Node's and Go's own toolchains are the test, not a guess at what they might need.
- **A new `pytest` corpus for any of this.** Item 9 retunes constants an existing test suite already exercises through the behavior each number bounds; nothing here is new logic to cover.
- **Adding a live-check group for item 9 in `.agents/docs/testing.md`.** Every check above reruns an existing group's check or reuses an existing command in `.agents/docs/development.md`; item 9 verifies no new behavior for a future item to regress.

## Documentation updates

`.agents/docs/roadmap.md`:

- Item 9's paragraph shrinks to a sentence: every number under items 3–6 carries a measured reason now, and the "Undecided" bullets in `.agents/docs/architecture.md` are answered. Status `verified`.
- Items 3, 4, 5, and 6 each gain the measured reason beside the number they already name, replacing nothing but adding a clause where a bare number sits today. The word budget for this comes from item 9's own paragraph shrinking first.

`.agents/docs/architecture.md`: "Undecided" loses both bullets; the section is removed if nothing else is added to it, or left as a heading with nothing under it if a bare heading reads as an outstanding decision either way — decided when the edit is made, against how it reads.

`.agents/docs/testing.md`: no change. No new behavior, no new group.

`.agents/docs/development.md`: no change. The commands and fixtures this item uses are already documented or are one-off additions to `kkestell/coral-test` itself, not a new local command.

`.agents/docs/functional-requirements.md`: no change.

## Validation

- The four commands, all clean.
- Every number under items 3–6 in `.agents/docs/roadmap.md` reads a reason, not a bare figure. `.agents/docs/architecture.md` has nothing under "Undecided."

## Follow-up

None. Item 9 is the last item on the roadmap; once it is verified, "the current item" in `.agents/docs/roadmap.md`'s own definition has nothing left to name.
