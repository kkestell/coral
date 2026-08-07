# Structured output on any model

Roadmap: item `13`, `Structured output on any model`.

## What Was Checked

Everything below was read out of the installed `deepagents` and `langchain` packages on 2026-08-07.

- `create_deep_agent` hands `response_format` to `langchain.agents.factory.create_agent` untouched.
- A bare schema — what Coral passes today — is wrapped in `AutoStrategy` and auto-detected: the native structured-output request (`ProviderStrategy`) when the model's profile carries `structured_output`, or when the model's name matches `FALLBACK_MODELS_WITH_STRUCTURED_OUTPUT`, a regex table of GPT, Claude, and Grok names inside LangChain; the synthetic tool (`ToolStrategy`) otherwise.
- Today's arrangement therefore rests on two accidents, not one. The hand profile omits the key, and `openai/gpt-5.6-luna` happens to slip the name table — `gpt-5($|[-/:])` does not match `gpt-5.6`. `openai/gpt-5.5` and Anthropic's Haiku both match the table, so the models this item tests would get the native strategy today with the key already dropped. The name table is the goes-stale lookup the roadmap bans, and it lives upstream where no edit of Coral's reaches it.
- An explicit strategy passed as `response_format` is used as it is; the auto-detection never runs.
- Under `ToolStrategy`, every model call is bound with `tool_choice="any"`: the model cannot answer in plain text, must call a tool each step, and the run ends when it calls the synthetic schema tool. A malformed schema call is handed back as an error message for a retry (`handle_errors=True`, the default).
- `ChatOpenRouter.openrouter_provider` is OpenRouter's provider-routing object passed through whole — `_run` already sends `require_parameters` and `ignore` — so `{"only": [...]}` pins a run to one provider.
- `coral/environment.py` reads `/opt/hostedtoolcache` with `iterdir`, so a developer machine needs that directory to exist — empty is fine — before `container.start` runs.

## Goal

The reviewer's structured object always arrives through the synthetic tool, on every model, because Coral says so — not because a profile key was omitted or a name slipped a table. Settled by running the real reviewer from this machine against DeepSeek on several of its providers, an OpenAI model the name table would have caught, and Anthropic's Haiku.

## Approach

### The arrangement

`_run` in `coral/agent.py` passes `response_format=ToolStrategy(response_format)` explicitly. That bypasses the auto-detection on every path, so the profile's `structured_output` key stops mattering anywhere — which is what makes item 14's fetched profiles safe to carry it. The `MODEL_PROFILE` comment's deliberately-absent paragraph is replaced by one sentence: the strategy is explicit, so no profile key decides it.

`tool_choice="any"` is what buys the agent loop everywhere: a model that can call tools must keep calling them until it answers through the schema tool, and tool calling is already Coral's floor — `require_parameters` keeps requests off endpoints without it.

The strategy does not forbid calling the schema tool on the first step, which is the reviewed-the-diff-alone hazard. Whether each model actually reads files and runs tests first is what the experiment measures; a model observed answering first-call gets a prompt fix, never a branch.

### The experiment

A scratch driver in the scratchpad, never committed, running the real `produce_review`:

- A small local clone with a planted defect; the request rendered with `render_request` over the clone's real diff and an empty conversation; a deadline of about five minutes; the key from `.env`.
- Per model, a temporary local edit of `MODEL` and `MODEL_PROFILE` — the numbers read off OpenRouter's listing — and, for the DeepSeek runs, a temporary `{"only": [<provider>]}` in `_run`'s provider dict. All reverted after; item 14 is what makes the model a parameter.
- The matrix: DeepSeek's current chat model on three of its providers (read off its endpoints listing at run time), `openai/gpt-5.5` — a name the fallback table catches, which is the proof the explicit strategy overrides it — and Anthropic's Haiku.
- Evidence per run, recorded for the item's review artifact: a valid `Review` came back, and the message list shows file and shell tool calls ahead of the schema tool call.

A model that cannot finish under the arrangement — never calls the schema tool, hits the step cap — is recorded as a model Coral does not serve. The arrangement stands; one arrangement was the decision.

### The machine

Docker Desktop running; `sudo mkdir -p /opt/hostedtoolcache` once, since `container.start` mounts it and `environment.py` lists it — empty means the image's own `PATH` plus `apt-get`, which the experiment's small clone is fine with. The driver removes each run's container and copy itself: a developer machine is not a discarded runner VM.

## Related code

- `coral/agent.py` — the explicit `ToolStrategy`, the profile comment shrunk.
- `tests/test_agent.py` — a pin that the response format handed to `create_deep_agent` is the explicit strategy, the way the middleware-name pin works.

## Current state

- `_run` passes the bare schema; the strategy is decided by the auto-detection against the hand profile's omitted key, and `MODEL_PROFILE`'s comment carries the reasoning.
- Nothing has ever run the reviewer on a model other than `openai/gpt-5.6-luna`.

## Test plan

**Key behaviors to verify**

- `_run` hands `create_deep_agent` a `ToolStrategy` wrapping the passed schema — pinned so an upstream or local change back to auto-detection fails a test.

**What NOT to test**

- What each endpoint answers. That is the experiment, and it is the item.

**Live checks**

Added as a group in `.agents/docs/testing.md`:

1. The matrix above, from a developer machine: each model returns a valid `Review` with tool calls ahead of the schema tool call.
2. Open a pull request in `kkestell/coral-test` with a planted defect, on the default model. The review posts a confirmed finding — the unchanged-behavior control.

## Implementation plan

1. **Save this plan** as `.agents/docs/plans/2026-08-07-16-00-013-structured-output-on-any-model.md`.
2. **Change `coral/agent.py`** — the explicit strategy and the comment — and add the pin to `tests/test_agent.py`.
3. **Run** `uv sync --frozen`, `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`, `uv run pytest` — all clean.
4. **Set the machine up** — toolcache directory, Docker, the clone with a planted defect, the scratch driver.
5. **Run the matrix**, capturing each run's evidence; revert every temporary edit.
6. **Live check 2** — the real review in the test repository.
7. **Documentation updates** below; roadmap item 13 to `built`.

## Not doing

- **A branch, profile key, or allowlist per model.** The roadmap's decision, and the point of the explicit strategy.
- **The native strategy anywhere**, even on models where it behaves: it is the first-response hazard and a second arrangement.
- **Parameterizing the model, effort, or provider through the CLI or workflow.** Item 14 owns the knobs; the experiment edits locally and reverts.
- **Committing the driver.** A rehearsal, like `coral/container.py`'s by hand.
- **Validating that a model supports tool calling.** The provider's refusal arrives in its own words through the failure comment.

## Documentation updates

- `.agents/docs/testing.md` (1,497 of 1,500 words — trim first): the two checks above as a group.
- `.agents/docs/development.md`, "Gotchas": running the reviewer from a developer machine needs Docker and an existing `/opt/hostedtoolcache`, empty or not.
- `.agents/docs/architecture.md`: unchanged — the arrangement is a comment in `coral/agent.py`, which is its home.
- `.agents/docs/roadmap.md`: item 13 to `built`.

## Validation

- The five commands, all clean.
- The done condition, mapped: live check 1 is "a valid `Review` from each model tested with tools called before the answer"; live check 2 is "a real review in the test repository still posts confirmed findings".

## Follow-up

- Item 14 lets the caller name the model and fetches profiles from OpenRouter at run time; with the strategy explicit, a fetched profile carrying `structured_output` changes nothing, which is the property item 14 is written against.
