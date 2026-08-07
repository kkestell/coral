# Configuration knobs

Roadmap: item `14`, `Configuration knobs`.

Item 13 is planned (`.agents/docs/plans/2026-08-07-16-00-013-structured-output-on-any-model.md`) and not yet built; this item builds only after it lands. That plan makes the structured-output strategy explicit in `coral/agent.py`, so the profile fetched below never sets `structured_output` and nothing reads it — and the model named in live check 1 should be one item 13's matrix exercised.

## What Was Checked

Everything about OpenRouter below was read out of its live API on 2026-08-07; everything about `ChatOpenRouter` out of the installed package the same day; the Actions facts out of GitHub's contexts-availability documentation.

- `ChatOpenRouter` carries a `reasoning: dict[str, Any] | None` field, OpenRouter's own reasoning block, so effort is passed as `reasoning={"effort": ...}` and omitted by passing nothing.
- `GET /api/v1/models` needs no authentication and returns every model (400 today, about 650 KB). For `openai/gpt-5.6-luna` it carries `context_length` 1,050,000, `top_provider.max_completion_tokens` 128,000, and a `supported_parameters` list without `temperature` — exactly the facts `MODEL_PROFILE` in `coral/agent.py` copies by hand. A profile built from the listing reproduces today's profile at the default model, which is what keeps an unconfigured install unchanged.
- Alias ids appear in that listing with the `~` prefix (`~x-ai/grok-latest`, `~anthropic/claude-haiku-latest`, …), and the per-model route answers 200 for them. Absence from the listing does not catch an alias, so the `~` refusal must be Coral's own check.
- A model OpenRouter does not carry is absent from the listing and 404 on the per-model route.
- GitHub Actions expressions have no arithmetic, and `jobs.<job_id>.timeout-minutes` accepts the `needs` context. Budget plus headroom is therefore computed in Python in the resolve job and crosses as a job output.
- A hosted job's execution ceiling is 360 minutes.

## Goal

The caller file names the model, the reasoning effort, and the time budget as `workflow_call` inputs, each defaulted so an install naming none of them reviews exactly as it does today. The model's profile comes from OpenRouter's listing at run time, retiring the hand-copied constant that pins Coral to one model's numbers.

## Approach

### The inputs

Three `workflow_call` inputs in `.github/workflows/coral.yml`, and their defaults live there and nowhere else:

- `model` — string, default `openai/gpt-5.6-luna`.
- `reasoning_effort` — string, default empty. Empty sends no reasoning block, which is today's request; a value is passed through to the provider unvalidated.
- `time_budget_minutes` — number, default 20, which is `STEP_BUDGET_SECONDS` today.

They reach the composite actions as action inputs and the console script as environment variables, the same road the secrets travel: `CORAL_TIME_BUDGET_MINUTES` to the resolve action, all three (`CORAL_MODEL`, `CORAL_REASONING_EFFORT`, `CORAL_TIME_BUDGET_MINUTES`) to the review action. Configuration comes only from the caller's workflow file; the roadmap owns why the reviewed repository gets no say.

### The budget

`coral/deadline.py` keeps owning the time arithmetic, still stdlib-only:

- `HEADROOM_MINUTES = 10` — today's gap between the 20-minute budget and the job's `timeout-minutes: 30`, keeping the existing reason: the review step must still be running when its deadline fires, because it writes the reason the failure comment carries.
- A function that takes the budget input's string, validates it — an integer, at least one, and budget plus headroom at most GitHub's 360-minute ceiling — and returns the job's timeout in minutes. A value outside that raises with the bound in the words.
- `REVIEWER_BUDGET_SECONDS` becomes a fraction, 0.65 of the step budget — 13 of 20 minutes today, so the default is unchanged — keeping its reason: whatever the reviewer leaves is the only time the verifier is guaranteed.
- `start()` loses its default budget. The default is the input's default; a second copy in Python is the disagreement "Where Things Go" bans.

`coral/resolve.py` validates the budget inside `reported(...)`, beside the key-mode check and before the fetch, so a misconfigured install is loud on every triggered run: red, with one comment carrying the words. On proceed it writes the timeout as a `timeout-minutes` job output, and the review job reads it: `timeout-minutes: ${{ fromJSON(needs.resolve.outputs.timeout-minutes) }}`.

The minted key's TTL derives from the same number: `KEY_TTL_SECONDS` retires and `mint` takes a TTL of twice the job timeout in seconds, keeping its reason — the slack covers the runner queue time between the two jobs, which GitHub does not bound.

`coral/review.py` reads `CORAL_TIME_BUDGET_MINUTES` and starts the step deadline from it; the reviewer's slice is the fraction of that budget.

### The model and its profile

`coral/openrouter.py` grows the listing fetch and its docstring widens to what is now true: the only module that speaks to OpenRouter's HTTP API, completions excepted.

- A name carrying `~` is refused before any request, naming the exact-model rule: OpenRouter would resolve the alias, so the check has to be Coral's.
- `GET /api/v1/models`, once per run. The named id absent means a `RuntimeError` saying OpenRouter does not list that model; present, the function returns a small frozen dataclass of the facts the profile needs — context length, max completion tokens, supported parameters — keeping LangChain types out of this module.

`coral/agent.py` retires `MODEL` and `MODEL_PROFILE`. `_run`, `produce_review`, and `verify_findings` take the model name, the effort, and the listing facts; the profile is mapped there — `tool_calling` from `"tools"` in the supported parameters, `reasoning_output` from `"reasoning"`, `temperature` likewise, the two token counts straight through, and `structured_output` never set, because item 13 made the strategy explicit and nothing consults the key. `ChatOpenRouter` gains `reasoning={"effort": ...}` only when the effort is non-empty.

`coral/review.py` fetches the listing once, before the reviewer, and both agent runs share it.

### What is deliberately not validated

The effort goes to the provider as given, and a model whose endpoints cannot serve tools is caught by `require_parameters` on the provider's side. Either refusal arrives as the provider's own words in the failure comment — the path a broken key already takes, and the roadmap's decision.

## Related code

- `.github/workflows/coral.yml` — the three inputs, the input wiring to both actions, the review job's derived `timeout-minutes`.
- `actions/resolve/action.yml`, `actions/review/action.yml` — the new inputs into `env`.
- `coral/deadline.py` — headroom, the ceiling, the budget validation and timeout derivation, the reviewer fraction.
- `coral/resolve.py` — validating the budget, the `timeout-minutes` output, the TTL handed to `mint`.
- `coral/openrouter.py` — the alias refusal and the listing fetch; `mint` taking a TTL.
- `coral/agent.py` — the constants retired, the parameters added, the profile mapping, the reasoning block.
- `coral/review.py` — the environment variables, one fetch shared by both runs.
- `examples/coral.yml` — a commented `with:` block.
- `tests/test_deadline.py`, `tests/test_openrouter.py`, `tests/test_agent.py`, `tests/test_resolve.py`, `tests/test_review.py` — updated.

## Current state

- The model, its profile, and both budget numbers are constants: `MODEL` and `MODEL_PROFILE` in `coral/agent.py`, `STEP_BUDGET_SECONDS` and `REVIEWER_BUDGET_SECONDS` in `coral/deadline.py`, `KEY_TTL_SECONDS` in `coral/openrouter.py`, `timeout-minutes: 30` in the workflow.
- The reusable workflow declares secrets and no inputs; the composite actions carry no configuration.
- No reasoning block is sent; the provider applies its own default effort.

## Test plan

**Key behaviors to verify**

- `deadline.py`: the derivation adds the headroom; a non-integer, a zero, and a budget past the ceiling each raise with the bound in the words; the fraction at the default budget is today's 13 minutes.
- `openrouter.py`: a `~` name is refused without a request; the listing parse, against a real response trimmed to a few models, returns the right facts for a present id and raises naming an absent one; `key_request` carries the TTL it is passed.
- `agent.py`: the profile mapped from the default model's listing facts equals the retired constant; the reasoning block is present exactly when an effort is.
- `resolve.py`: an invalid budget fails inside `reported`, so the reason file is written; a proceeding run writes the `timeout-minutes` output.

**What NOT to test**

- That OpenRouter's listing is truthful, that GitHub enforces `timeout-minutes`, or what a provider refuses. The live checks and the provider's own words cover those.
- The YAML expression plumbing; live check 1 observes it.

**Live checks**

Added as a group in `.agents/docs/testing.md`. The knobs swap in `kkestell/coral-test`'s caller file.

1. Name all three in the caller's `with:` block — a model item 13 tested, an explicit effort, a 10-minute budget. A review posts, the run is green, and the run's log shows the budget and the fetched profile numbers.
2. Remove the `with:` block. A review posts as before, and the log's profile numbers are the retired constant's — the unchanged-install half of the done condition.
3. Set `model` to `~openai/gpt-mini-latest`. Red run, one comment refusing the alias and saying to name the model exactly.
4. Set `time_budget_minutes` to 355. Red run, one comment carrying the ceiling.
5. Set `model` to a name OpenRouter does not list. Red run, one comment saying so.

## Implementation plan

1. **Save this plan** as `.agents/docs/plans/2026-08-07-16-10-014-configuration-knobs.md`.
2. **Change `coral/deadline.py`** — headroom, ceiling, validation, derivation, fraction — and `tests/test_deadline.py`.
3. **Change `coral/openrouter.py`** — the alias refusal, the listing fetch, `mint`'s TTL parameter — and `tests/test_openrouter.py`, trimming a real listing response into the tests.
4. **Change `coral/agent.py`** — retire the constants, add the parameters, map the profile, pass the reasoning block — and `tests/test_agent.py`.
5. **Change `coral/resolve.py` and `coral/review.py`** — validation and outputs, the environment variables, the shared fetch — and their tests.
6. **Change the YAML** — the workflow's inputs and derived timeout, both actions, the example file's commented `with:` block.
7. **Run** `uv sync --frozen`, `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`, `uv run pytest` — all clean.
8. **Live checks** 1 through 5.
9. **Documentation updates** below; roadmap item 14 status to `built`.

## Not doing

- **Validating the model or the effort ahead of the review job.** The roadmap decided: the provider's refusal, in its own words, through the failure comment.
- **An allowlist of efforts.** The listing carries `supported_efforts`, and reading it would be a second validator for a value the provider already rules on.
- **Per-endpoint window arithmetic.** The listing's model-level numbers are the ones today's profile carries; choosing a minimum or maximum across endpoints is a policy with no measurement behind it.
- **Taking the timeout as the input and deriving the budget.** The roadmap names the budget as the input and the timeout as derived.
- **Scaling the minted key's spend cap with the budget.** Item 15 owns spend.
- **Caching the listing.** One unauthenticated 650 KB request per run.
- **A `configuration.py`.** Each value lands where its subject already lives.

## Documentation updates

`.agents/docs/architecture.md` (1,488 of 1,500 — trim first):

- "The Platform": the fixed-model bullet becomes: the model, effort, and time budget are `workflow_call` inputs defaulted in the reusable workflow; the model is named exactly, `~` aliases refused; its profile is fetched from OpenRouter's listing at run time.
- "The Run": resolve's bullet gains the budget validation and the derived timeout output; the review job's bullet notes its `timeout-minutes` comes from that output.
- "Installation and Packaging": the caller file's list of what it carries gains "any configuration", still exactly one home.

`.agents/docs/development.md`: "Environment" gains the three `CORAL_` variables `coral review` and `coral resolve` read, with their run-time source being the workflow inputs.

`.agents/docs/testing.md` (1,497 of 1,500 — trim first): the five checks above as a group.

`README.md`: the workflow-file section documents the three `with:` inputs and their defaults.

`.agents/docs/roadmap.md`: item 14 to `built`.

## Validation

- The five commands, all clean.
- The done condition, mapped: live check 1 is "a model, an effort, and a budget the caller named"; check 2 is "an install naming none of them is unchanged"; checks 3 and 4 are the alias and the over-ceiling budget stopping with the reason said.

## Follow-up

- Item 15 adds the spend cap beside these inputs and reads each response's cost; the budget plumbing built here — one input, validated in resolve, driving a mint parameter — is the shape it repeats.
- `VALIDATION_TODO.md` still owes item 10 its "Posting" and "Failure" re-runs; this item does not absorb them.
