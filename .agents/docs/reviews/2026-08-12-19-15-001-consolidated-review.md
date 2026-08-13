# Review: maintainability, simplicity, elegance, and test quality (consolidated)

This document consolidates the four reviews taken on 2026-08-12 at 18:44, 18:49, 18:52, and 19:10, deduplicated and re-verified against HEAD 2b78524 ("Finish review disposition refactor") plus an uncommitted README.md edit. On that tree `uv run pytest` passes 415 tests in under a second; `uv run ruff check`, `uv run ruff format --check`, and `uv run mypy` (strict, over coral and tests) are all clean; line coverage measured with pytest-cov is 80% of the package's 1,598 statements.

The tree changed under the earlier reviews as the day's refactor landed, and several of their findings were fixed before this consolidation. Resolved and not repeated below: the half-applied disposition refactor (`review()` now computes dispositions once and logs from them, finished in 2b78524); the three doc sentences left untrue by the `pull_request_target` move; the untested disposition reasons (now pinned by `test_each_finding_disposition_names_the_filtering_decision`); the `read_file`/`write_file` vocabulary in `tests/test_agent.py` narrating removed tools; the byte-identical `checkout` expression duplicated across both arms of `change_description`; and `check.yml` running unfrozen `uv run` commands after `uv sync --frozen`.

Priorities describe maintenance cost, not Coral finding severity.

## 1. The conversation paging loop is verified by nothing routine

Priority: high

Disposition: add a unit test with a fake `GitHub`; the fakes already exist in three test modules.

`fetch_conversation` in [coral/github/conversation.py](coral/github/conversation.py#L541-L587) is the most intricate function in the codebase that no test exercises: coverage reports lines 541-587 unexecuted. It walks three connections backwards from cursors, prepends older nodes to keep ascending order, and drives each connection with a different comment-counting callback. `wants_another_page` is tested in isolation, which is the predicate but not the walk.

`.agents/docs/testing.md` states that the paging is also the one thing the test repository cannot show, because it needs a public pull request busier than any of its own, and points at a manual command against `cli/cli`. So the loop has neither a unit test nor a routine live check — it is the one piece of logic with no routine check of any kind.

Nothing about it needs the network. `tests/test_publish.py`, `tests/test_resolve.py`, and `tests/test_post.py` each already subclass `GitHub` to answer from a table. A `GitHub` whose `graphql` returns two prepared pages per connection would pin the cursor threading, the older-nodes-in-front ordering, the per-connection counters, and `MAX_PAGES` — the four things the manual check is for.

## 2. `resolve()` builds the credential handoff twice

Priority: medium

Disposition: one function taking the timeout and cap, called from both paths.

The management-key validation, encryption-key validation, mint, mask, and encrypt sequence appears once on the push path ([coral/resolve.py](coral/resolve.py#L218-L237)) and again on the pull-request path ([coral/resolve.py](coral/resolve.py#L291-L307)), about fifteen lines each and identical in intent. The push copy alone needs a `key = encryption` rebinding ([coral/resolve.py](coral/resolve.py#L232)) to satisfy the checker, so the two copies have already diverged in form while meaning the same thing. The comments justifying placement — after the gates, before the outputs — are likewise split across both. Extracting the sequence removes the divergence risk and reunites the reasoning.

## 3. The anchored-review retry has no test, and the reason given for that is now stale

Priority: medium

Disposition: add the case; the fake it needs is twenty lines above it.

`post_review` in [coral/github/post.py](coral/github/post.py#L326-L333) is uncovered. It is a stated behavior in `.agents/docs/functional-requirements.md`: "If GitHub rejects an anchored review, Coral retries once with every finding in the body and no inline comments."

`tests/test_post.py` explains the omission in its docstring: recovering from a 422 needs a `GitHub` that fails, and the demoted body the retry would send is tested. The second half holds. The first half no longer does — the same file defines `Recording`, `Refusing`, and `Forbidding` subclasses of `GitHub` for `create_labels`, and `Refusing` raises exactly the `ApiError("POST", path, 422, ...)` this needs.

What is untested is the control flow: that a 422 retries once and posts the demoted payload, and that any other status re-raises rather than silently demoting. The second half is the one worth pinning, because a retry that swallowed a 403 would publish a review with every finding stripped out of the diff and look like success.

## 4. The decisions that steer a whole run sit in untested wiring

Priority: medium

Disposition: two small tests in the pattern the suite already uses; document the budget-split seam when it is next touched.

`read_subject` in [coral/review.py](coral/review.py#L260-L267) is entirely uncovered. It decides which of the two review modes the run takes, on `runner.push_path().exists()`, and every difference between a pull-request review and a main-push review follows from its return type. It makes no network call; `tests/test_runner.py` and `tests/test_publish.py` already stage `RUNNER_TEMP` in `tmp_path`.

The main-push finding-count guard ([coral/review.py](coral/review.py#L368-L377)) is also uncovered. It implements a stated requirement — a `main` review proposing more findings than Coral can duplicate-check fails without creating any issue — and it is the one place where exceeding `MAX_SEARCHES` must raise before an `IssueEvidence` is built. It is a comparison, not live territory.

The rest of `review()`, `resolve()`, and `publish()` is wiring by design, sitting at about 60% coverage, and the extraction of their decision logic into tested pure functions is what keeps the untested wiring honest. Two seams there are subtle enough to be a bug waiting for a typo: the budget split, where the reviewer is handed a fresh deadline of 65% of the step budget while the verifier runs under the step's own deadline started earlier; and the three separate `isinstance(subject, PushSubject)` decisions in `review()` that a future cross-cutting context block will be threaded through. The suite already demonstrates the technique that could cover these cheaply — `tests/test_publish.py` drives `publish()`'s main-push branch through the runner protocol, and `tests/test_agent.py`'s `run_against` intercepts the framework — but a live run remains the honest test of the wiring itself.

## 5. `confirmed()` is now dead in production code

Priority: low

Disposition: either `confirmed` goes and its cases retarget the two functions that compose it, or the module docstring says why the composed form stays.

After the disposition refactor, `review()` calls `finding_dispositions` and then `apply_dispositions`, because it needs the dispositions themselves for logging. Nothing under `coral/` calls `confirmed` ([coral/schema.py](coral/schema.py#L218)); only `tests/test_schema.py` does. A function kept alive by its tests is the tests pinning a path production never takes.

## 6. The `Subject` union is dispatched two different ways in one module

Priority: low

Disposition: pick `match`, since the union exists to make the checker find a missing case.

`heading`, `description`, and `change_description` dispatch on `Subject` with `match`. `render_review_request` and `render_verification_request` dispatch on the same union with `isinstance` ([coral/review.py](coral/review.py#L189), [coral/review.py](coral/review.py#L237)), and `review()` reduces it to a `main_push` boolean it then branches on three times. `.agents/docs/code-style.md` gives the reason to prefer one: exhaustive `match` over a tagged union is how a missing case gets found by the checker instead of at runtime. A third subject kind would leave both renderers silently taking the pull-request path. Cosmetic today with two members, and the seam the next review mode arrives through.

## 7. `_open_issue` builds a value every caller throws away

Priority: low

Disposition: return `bool`, or use what it returns.

`IssueEvidence._open_issue` in [coral/github/issues.py](coral/github/issues.py#L148) documents itself as "An ordinary open issue result, reduced to the two fields tools may return," and returns `{"number": number, "title": title}`. Both call sites use it only for truth: `search_open_issues` filters with it and then reads `candidate["number"]` and `candidate["title"]` off the original unreduced dict, and `view_issue` calls it as a guard and then reads off the raw answer. The reduction is real work that nothing consumes, and the docstring describes a containment property the code does not provide.

## 8. A multi-commit main push is described to the model as a single commit

Priority: low

Disposition: change the prose; the range is already correct.

`.agents/docs/functional-requirements.md` is explicit that a push to `main` is reviewed as one range and that a multi-commit push is one review, not one review per commit. The range Coral computes is right. The prose it wraps around it is not: `heading` renders `f"Main commit {head}"` ([coral/review.py](coral/review.py#L150)), `description` says "This commit was pushed directly to main" ([coral/review.py](coral/review.py#L161)), and `issue_payloads` files each finding as found "in main commit `{commit}`". For a five-commit push, the model is told it is looking at one commit when the diff spans five. Naming the range costs a sentence, and roadmap item 23 will need the range's commit messages anyway.

## 9. Smaller observations

Priority: low

- The finding-count guard checks `len(review.findings) > MAX_SEARCHES` but its message hardcodes the number: "A main-push review proposed more than 10 findings" ([coral/review.py](coral/review.py#L370)). A changed constant makes the message lie; the message should read the constant.
- `Ledger`'s docstring claims to be "the one mutable object Coral passes between modules" ([coral/spend.py](coral/spend.py#L19)). `Access` in `coral/command.py` caches permission lookups mutably and is shared across resolve, reactions, and publish, and `IssueEvidence` accumulates search state across the verifier's tool calls. The sentence should either name the company or say what distinguishes the ledger.
- `facts_of` indexes `model["top_provider"]["max_completion_tokens"]` ([coral/openrouter.py](coral/openrouter.py#L105)); a listing entry missing `top_provider` dies as a bare `KeyError` rather than the one-line boundary message the code style asks for at external inputs.
- `container.execute`'s subprocess body ([coral/container.py](coral/container.py#L227-L250)) is uncovered: the `TimeoutExpired` → kill → `timed_out` path and the in-container 124 mapping are branch decisions Coral makes, and could be pinned with a stubbed `Popen`. The argument builders and `drained` on either side of it are tested.
- `coral/rehearse.py` is the sole module with no test file, and `testing.md` states the one-test-per-module convention without naming the exception. It is person-driven glue by design; name the exception rather than test it.
- `tests/test_cli.py` asserts the keyword arguments passed to `logging.basicConfig` — implementation rather than behavior — and nothing checks that the four subcommands dispatch to their handlers. The weakest file in the suite, and also the lowest-stakes.
- The `Built` fake in `tests/test_agent.py` must mirror `create_agent`'s `with_config`/`invoke` contract, and it is the one place a LangChain upgrade will break a test for a reason that has nothing to do with Coral's domain. It is a large improvement over the backend class it replaced; flag it with a comment where the mirror lives, don't engineer it away.
- `_run` in `coral/agent.py` threads eleven positional parameters, forwarded twice. Contained and shared by exactly two callers, so it has not earned a dataclass yet; worth remembering if a third caller or twelfth parameter appears.

## Accepted costs

Three deliberate dependency pins survive the refactor, each commented at its source: `ToolStrategy(response_format)` named rather than detected, because auto-detection lets a model answer in the schema from the diff alone; `recursion_limit` set through a second `with_config`, because the graph has no constructor parameter for it; and the JSON-schema `anyOf`/`oneOf` contract in `tests/test_schema.py`, because a Pydantic discriminator silently emits `oneOf` where a strict provider validator takes only `anyOf`. Each is a real, measured dependency behavior and each is the price of a property Coral wants.

The helper duplication across test files — `comment_node`, `review_node`, `thread_node`, and the `access` builder each written four times — is the documented price of "no test imports another" and is currently worth paying. If a fifth copy appears, that rule is where the conversation should happen.

## The test suite

The suite is the strongest part of the codebase, and better than its coverage number suggests. 415 tests run in under a second with no network, no container, and no model. Every pure decision module — command, deadline, environment, handoff, marker, reactions, schema, spend — sits at 100%, and the uncovered remainder is almost entirely the live-boundary code the testing doc names as live-check territory, declared in each module's docstring rather than left to be discovered.

What makes it good:

- Fixtures are captured reality, dated and sourced: the conversation tests parse a trimmed real GraphQL response from `cli/cli` 10513; the OpenRouter tests use trimmed real listing and key-creation answers; the diff tests use captured `git diff --unified=0` output. Input is validated through the real parsers rather than hand-built dataclasses, so a change to what a comment holds reaches the renderer tests.
- Adversarial cases are the norm: every inert `/coral` form including fence-inside-fence, forged and quoted markers, NaN and negative and infinite costs, header-shaped diff content, paths with spaces, deleted authors, unsubmitted reviews, booleans masquerading as issue numbers.
- The fakes are at the real seams: `GitHub` subclasses answering from tables rather than wholesale mocks, the runner's own env-var protocol driven through `tmp_path`, and `create_agent` intercepted in `tests/test_agent.py` so everything `_run` decides is observable without a request. `monkeypatch` is reserved for seams and environment.
- Doubt is recorded where it lives: the stray-field test in `tests/test_schema.py` is marked "recorded rather than desired", so a future tightening is a deliberate change rather than a surprise.
- Several tests are load-bearing in a way unit tests usually are not. `test_the_structured_output_strategy_is_named_rather_than_detected` pins a framework behavior whose silent change would produce reviews written from the diff alone. `test_the_json_schema_uses_anyof_and_never_oneof` pins a provider-side validator's requirement no type annotation expresses. `test_a_failed_search_leaves_the_finding_unchecked` pins the exact coupling that stops Coral filing an issue it never duplicate-checked.

The gaps worth closing are findings 1, 3, and 4 above: the places where the suite's own stated boundary — wiring is live territory — has outrun its reasoning, because the code is pure decision logic and the fakes already exist in the same files.

## What holds up

The refactor this tree went through today is exactly the subtraction the 17:11 review asked for, and it is done well. The tagged-union `Subject` replaces four near-duplicate render functions and the exact-string-replacement hack. The single `execute` tool removes the backend class, the filesystem middleware, the six named file tools, the upload/download byte bridge, and the `forgiving` wrapper together — the largest maintainability liability in the tree, gone. The `finding_dispositions` extraction makes the filter's decision single-sourced.

The module layout matches the pipeline one-to-one, and the `github/` subpackage earns its shallowness. The code-style rules are kept rather than aspirational: frozen dataclasses with exhaustive `match`, `Final` constants carrying measured justifications with sources and dates, no exception taxonomy (`ApiError` exists because the 422 retry recovers on its status, exactly the rule's condition), no mocks of Coral's own code. Bounds are enforced where data arrives rather than where it is used: the streamed 16 MB response ceiling, the per-body trim applied during paging, the conversation count and character bound, the drained container output, the issue-evidence caps, the shell ceiling enforced inside the container. The security posture is structural and consistently so: schema-only agent returns, two-factor attribution of Coral's own comments, `commit_id` and `event` stamped by the publishing job, the fork check by repository id, no credential in any container, the review process popping its credentials before the framework is imported. The comments are the unusual strength — they record why a number is what it is and what would invalidate it, which is what keeps a tuning-laden system changeable.

The overall recommendation: add the paging-walk test, extract the `resolve()` credential handoff, pin the 422 retry's control flow, test `read_subject` and the finding-count guard, and decide `confirmed()`'s fate; the rest is polish. Nothing here calls for redesign.
