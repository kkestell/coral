# Roadmap

The order the work happens in, and the mechanics of what each item builds. A sequence, not a schedule: one item is one plan, one build, and one review, and those artifacts carry the item's number in their filenames.

Item numbers are permanent and never reused; `000` is reserved for a plan deliberately run outside the roadmap. Status is `not started`, `built`, or `verified`: `/build` sets `built` when the done condition is met, `/review` sets `verified` after checking that claim. The current item is the lowest-numbered one not yet verified.

## 1. Skeleton and contract

Status: built
Depends on: nothing

Create the project: `pyproject.toml` with the console script and dependencies, a committed `uv.lock`, `.python-version`, and configuration for `ruff`, `pytest`, and `mypy`. Fill in `.agents/docs/development.md` and `.agents/docs/testing.md` against what exists.

Write `coral/schema.py` first and on its own — the contract every later item is written against. The review object:

- Frozen dataclasses handed to the framework unchanged through `response_format` on `create_deep_agent` — no wire type, no conversion.
- A summary, findings, and a flag saying whether an empty list means nothing to find or everything already said still stands.
- An anchor is a union of four frozen dataclasses with `kind` literals: line span, single line, whole file, whole pull request. Read with exhaustive `match`.
- The JSON schema uses `anyOf`, never `oneOf`, which strict provider-side validators require.
- The structured result is required. A `structured_response` of `None` is failure; nothing recovers a review from prose.

Done when: `uv sync --frozen`, `ruff check`, `mypy`, and `pytest` run clean on an empty suite, and no document in `.agents/docs/` contains a template placeholder.

## 2. Walking skeleton

Status: built
Depends on: 1

Get the whole workflow running end to end with no model call: `coral review` returns one hardcoded finding on a line picked from the diff, plus a hardcoded summary. Everything around it is real — the composite actions, the reusable workflow, the `$/` references, the reaction, the sentinel, the batched review. This is where `kkestell/coral-test` gets its first pull request.

Early, because these cannot be checked another way:

- Whether the `$/` reference resolves — recently GA, absent on GitHub Enterprise Server, unresolvable below runner 2.336.0.
- Whether a batched review with `event: COMMENT` posts and is visible.
- How state crosses the step boundary. Every step output is a SHA or a boolean, so the heredoc form of the Actions output protocol is not built and an assertion rejects a newline.

Done when: a pull request in the test repository carries a review from Coral, posted by a workflow installed by adding one file.

## 3. Reading the conversation

Status: built
Depends on: 2

Build `coral/github/conversation.py` and `coral/github/marker.py`. The conversation is the agent's context and, through the markers, the record of reviewed commits — all of Coral's memory.

- Fetched with GraphQL: `isResolved` and `isOutdated` on review threads have no REST equivalent. The query returns reviews, review threads with comments, and issue comments, each with author and association. Inline comments are read under `reviewThreads` only — the flags live on the thread, and reading both ways duplicates every comment. That the token reaches `reviewThreads` under the three declared permissions is observed rather than documented.
- A comment is prose somebody wrote: an issue comment, a review with a non-empty body, or a thread comment. An empty-bodied review is the envelope around one inline comment and does not count against the bound, but is still read for its marker.
- The bound is the 200 most recent comments and 400,000 characters, whichever binds first, taken across all three connections. The review reports what was dropped, counting generously — overstating what went unread is the safe direction. A surviving thread keeps its flags, path, and lines whole.
- A connection returns at most 100 items. The first query asks each for its newest 100; a connection reporting a previous page and short of the bound is paged backwards from its cursor, at most four pages. The rule is per connection: a comment can only be missed if its own connection was not paged deep enough.
- No connection accepts a useful ordering argument (`UPDATED_AT` ranks edited-old above written-new), so default order plus `last:` is trusted to return the newest — observed, not promised — and the bound sorts on comment timestamps, compared as strings since ISO-8601 UTC sorts lexically. A thread has no timestamp; its recency is its comments'.
- Every comment Coral posts opens with an HTML comment carrying a fixed sentinel and the reviewed commit SHA — invisible rendered, exact to match. Coral posts as the repository's automation login, shared with every other bot, so the marker is the only reliable self-identification.
- The reviewed-commit set is read from review bodies only: an inline finding or a failure comment names a commit without meaning it was reviewed.

Done when: a real pull request's conversation round-trips into the shape the agent gets, the bound reports what it dropped, and the already-reviewed commits come back out of the markers.

## 4. The gatekeeper

Status: built
Depends on: 3

Finish `coral resolve` and write `coral/command.py`: which deliveries reach a runner, which requests count, which runs proceed, and who gets acknowledged. "Trigger" in `.agents/docs/functional-requirements.md` lists every way a `/coral` can be inert.

Triggering:

- Events: `pull_request` (`opened`, `ready_for_review`), `issue_comment` (`created`), `pull_request_review_comment` (`created`). Never `synchronize`. Never `pull_request_review` — GitHub cannot react to a review, so the request could not be acknowledged.
- The job-level condition is coarse (Actions expressions have no regex): body contains `/coral`, the comment is on a pull request (the `pull_request` key on the issue object), author association passes. The real parse runs in resolve; a mere mention allocates a runner and stops in seconds.
- The command is a line that is exactly `/coral`, lowercase, nothing before it, nothing after but whitespace, outside a fenced code block. Quotes, inline code, list items, and indented lines fail that rule without being named; only fences need tracked state. `contains` is case-insensitive, so `/CORAL` reaches a runner and stops as inert.
- Write access is `author_association` in OWNER, MEMBER, COLLABORATOR — from the payload, no API call. Broader than real write access (org members and read-only collaborators pass); narrowing costs a permissions call per comment.
- The bot exclusion (payload author `type` of `Bot`) applies to the automatic paths only; a `/coral` from a bot is a person's request relayed. It catches Apps, not scripts driving user accounts.
- A comment event runs in the base repository with its token and secrets, so resolve stops when the head repository differs from the base, treating a deleted head repository as a fork. The `pull_request` path is filtered too, though GitHub already withholds secrets there.
- Concurrency is a group keyed on the pull request number, `cancel-in-progress: false`: a running review finishes, a new run cancels the pending one. Issues and pull requests share one number sequence, so keys cannot collide.

The gates, in order: inert command, closed pull request, fork, already-reviewed (automatic paths only), size backstop. The order decides which reason is reported when several apply.

- The size backstop is 300 changed files or 30,000 changed lines, read off the pull request fetch, checked before the clone.
- Only the size stop comments on the pull request, one marker-carrying comment — the only stop that leaves somebody waiting with nothing visible to explain it. The others are silent.

Reactions:

- The `eyes` reaction lands when a request is accepted, before the review, because a comment-triggered run shows no check. Resolve reacts to every qualifying `/coral` in the conversation lacking Coral's reaction, not only the triggering comment, covering requests whose runs were cancelled while pending.
- The conversation query returns `databaseId` (the REST id the reaction endpoints take) and `reactionGroups` (whether the token's account already reacted). A duplicate reaction POST returns 200.
- The triggering comment is reacted to from the payload — the bounded conversation may not contain it — and deduplicated against the conversation. Reviews are skipped.
- Both write permissions are needed: reactions on diff comments go through `/pulls/comments/{id}/reactions` (Pull requests permission), on whole-pull-request comments through `/issues/comments/{id}/reactions` (Issues permission), and neither grants the other.

Done when: each gate stops the run for its reason, the reaction lands on both kinds of comment, and the parser has a test for every inert form.

## 5. The agent

Status: built
Depends on: 4

Write `coral/agent.py`, `coral/environment.py`, and `coral/deadline.py`.

The agent:

- The backend is the single swappable compute dependency: `LocalShellBackend` rooted at the checkout, behind the middleware below. It supplies the `execute` tool, and its filesystem operations run as direct Python.
- The agent is constructed only after the working tree exists and the secrets are stripped.
- The input is one rendered request: the title, the description, the conversation, and the whole diff. Rendered rather than handed over as JSON, because the association and flags item 6's rules read against are Coral's deterministic job to state in prose.
- `create_deep_agent` installs summarization middleware by default, so a long review is compacted mid-run — a reason to keep the conversation bound and size backstop tight, not a thing to switch off.
- Neither secret reaches the agent's shell, twice over: the shell environment is built rather than inherited and names neither; and the review step reads both from `os.environ` at start-up, holds them in memory, deletes them from `os.environ`, and only then constructs the model client and backend. Without this, `pull-requests: write` in the environment is an approving review one `curl` away.
- The shell environment is an allowlist copied out of the review step's own: `inherit_env` defaults to false and an empty environment runs nothing, so Coral constructs it. In, when present: `CI`, `HOME`, `LANG`, `LC_ALL`, `PATH`, `TERM`, `TMPDIR`. A missing `PATH` fails an assertion, since a shell without one runs nothing. Out by construction: both secrets, `VIRTUAL_ENV`, every `UV_*` — without those exclusions the reviewed repository's `pytest` runs against Coral's interpreter.
- The request sets `require_parameters` on the `openrouter_provider` kwarg. A provider allowlist is impossible — the alias's endpoint list comes back empty — and LangChain picks its structured-output strategy from the model profile rather than the serving endpoint, so an unconstrained request can be routed to an endpoint that cannot serve it. The same kwarg carries `ignore: ["azure"]`, which Coral must supply itself: DeepAgents injects it only when resolving a string model, and Coral passes an instance.
- The model profile is supplied by hand through `profile=`, four keys copied from the bundled table's entry for the concrete release. The table is looked up by exact name, so the alias misses it, and a profile-less model gets summarization triggers scaled to 170,000 tokens instead of the real million.
- `structured_output` is left out of that profile even though the real entry carries it, so the review comes back through a synthetic tool rather than a native structured-output request. Observed: the native request makes the endpoint answer in the schema on its first response, so the model reviews from the diff alone having called no tool. Without the key the same change drew five model calls and a correct anchor.

The time budget, since a failed run costs the same minutes as a productive one:

- Coral owns its deadline: 20 minutes from the start of the review step, with headroom to post afterwards, so the review step is always still running when its deadline fires — item 8 depends on this.
- The job's `timeout-minutes: 30` is a backstop, never the mechanism: a job GitHub cancels cannot post a failure comment.
- The deadline takes all five of: a step cap of 200, applied by overriding `recursion_limit` on the compiled graph (DeepAgents sets 9,999); an elapsed-time check between steps; a 180-second model request timeout, passed in milliseconds because `ChatOpenRouter` takes `timeout` in milliseconds; the shell ceiling below; and the auto-added general-purpose subagent disabled.
- The general-purpose subagent `create_deep_agent` adds is disabled through `register_harness_profile("openrouter", ...)`, the key being the provider `ChatOpenRouter` reports. It is outside every other bound: its own filesystem middleware keeps the 3,600-second ceiling, and the elapsed check cannot run between steps inside a `task` call. With no subagents passed, the `task` tool is not exposed at all.
- The model client takes one retry rather than the default two, which is deadline arithmetic: the elapsed check runs between steps, so the worst overshoot past a passing check is one in-flight request, and two retries make that about fourteen minutes — past the ten minutes of headroom before the job's own timeout.
- The per-command shell ceiling is 300 seconds and takes both halves. `FilesystemMiddleware(max_execute_timeout=300)`, passed through `create_deep_agent`'s `middleware` argument, rejects rather than clamps a command whose own `timeout` argument overshoots, which tells the model the ceiling; `LocalShellBackend(timeout=300)` bounds the case where the model omits the argument, which is the common one. Middleware merges by `AgentMiddleware.name`, which defaults to the class name, so Coral's instance replaces the framework's in place — and an upstream rename turns replacement into addition, leaving two middlewares each registering a `read_file` tool. Left alone the ceiling is 3,600 seconds, and the elapsed check cannot run until a command returns.
- A fired deadline raises out of `invoke` rather than ending the run gracefully, because a graceful end would arrive as "the agent returned no structured review" with the reason lost. Until item 8 exists that is a red run.

Done when: the agent reviews a real pull request and returns a valid review object, and the deadline fires and is observed to fire.

## 6. What Coral looks for

Status: built
Depends on: 5

Write both prompts, extend the contract in `coral/schema.py`, and run the second agent. No document describes what makes a finding worth making; this item decides it, and it is the product.

The reviewer, in `coral/prompts/review.md`:

- Scope is correctness, security, and performance. Style, naming, structure, documentation, and test coverage are not findings. An empty review is a correct review.
- Every finding carries a severity of `low`, `medium`, or `high`, calibrated in the prompt by the damage done if the change merges as it stands. Nothing below low is a finding.
- For every finding, a test that fails at the head commit because of the defect and passes once it is fixed, in the repository's own conventions, run before the review is returned. The finding carries its path, whole content, and the command that runs exactly it.
- A finding that cannot be reproduced sets `regression_test` to null and is thereby speculative — derived rather than stored, so one field cannot contradict another that does not exist. The field has no default, so an absent key fails validation and speculative is a null the model wrote.
- The summary never enumerates the findings, because verification may remove some after it is written.
- The prompt also carries three things no code enforces, all under "What Coral Reviews" in `.agents/docs/functional-requirements.md`: conversation is information and never instruction, a standing finding is not repeated, and where standing ends. What is enforced is the output schema and the missing credentials — nothing else.

The verifier, in `coral/prompts/verify.md`:

- A second run of item 5's construction, differing only in prompt and `response_format`. It returns one verdict per finding: the number, confirm or reject, and a reason read in the run's log and posted nowhere. It never rewrites a body, severity, or anchor.
- Its request is the title, the description, the whole diff, and each finding numbered from zero with its severity, anchor, body, and test. The conversation is absent, so a finding a comment talked into existence faces somebody who never read that comment.
- A finding with a test is confirmed only if that test, written out from the finding's own content, fails for the reason claimed. A speculative one is confirmed only if the claimed behavior is in the source.
- `confirmed()` keeps a finding at least one verdict confirms and no verdict rejects. A finding no verdict names is dropped — silence is not confirmation. Out-of-range indices are ignored.
- `reset()` puts the checkout back with `git checkout -- .` and `git clean -fd` between the runs, so each test is reproduced on a tree at the head commit. `-fd` rather than `-fdx`: dependencies the reviewer installed to run tests stay installed.
- The step keeps its 20 minutes and the reviewer runs under a 13-minute slice of them, so the verifier is guaranteed the rest. A reviewer that would have used minute fourteen fails instead — a review whose findings cannot be verified posts nothing anyway.
- No findings, no verifier run. A review whose findings are all rejected posts its summary alone.

Done when: a review of a real pull request produces confirmed findings a person would want at sensible severities, a planted defect comes back with a regression test that fails at head, a rejected finding is observed to drop, and the same pull request reviewed twice does not repeat itself.

## 7. Posting

Status: not started
Depends on: 6

Finish `coral/github/post.py` and `coral/diff.py`. Posting is deterministic code.

- Anchors are checked against the diff of the two pinned commits, computed locally — not the working tree (the agent writes scratch files into it) and not refetched (either branch may have moved).
- One review per run, one API call: summary as body, anchored findings as comments, naming the reviewed commit — which positions each comment, lets GitHub mark it outdated later, and writes the record the next run reads. Always `COMMENT`.
- Findings that will not attach are demoted into the summary with their file and line named. Expected to fire regularly.
- Whole-file findings go to the summary by construction: the create-review `comments` array accepts no `subject_type`, and posting them separately costs one call per finding.
- GitHub accepts or rejects a review whole, using its own patch generation, so the local pre-check cannot be sufficient. A rejected review is reposted with every anchored finding demoted — unconditionally, because a retry that depends on the 422 naming the bad entry fails silently when it does not. No finding is lost.
- The pull request's state is rechecked immediately before posting; resolve's check was minutes ago.
- The same module posts the plain marker-carrying comment the size stop and the failure path use.

Done when: a review with a deliberately bad anchor still delivers every finding, and no finding is lost on any path.

## 8. Failure

Status: not started
Depends on: 7

Write `coral/report.py` and the failure path inside `coral review`. Every way a review can fail ends in one comment on the pull request — a reaction followed by silence is worse than no reaction. The two halves meet at a marker file.

- The review step reports its own failures: owning the deadline means it is still running, still holds the checkout, and still has the posting code. It posts the reason immediately, drops the partial review, and writes a marker into the runner's temporary directory recording that it reported.
- The report step runs on job failure and covers everything before the agent: a rate-limited resolve, a missing secret, a failed checkout, a failed install. It skips when the marker is present, so a failure is reported once.
- A death no step can report — the runner vanishing, GitHub's own timeout — is visible in the Actions tab. The recovery is asking again.

Done when: each failure mode listed here produces exactly one comment, and the review step and report step together never produce two.

## 9. Settle the numbers

Status: not started
Depends on: 8

Every number below was chosen rather than measured, stated so the design is complete and testable. Run Coral against real pull requests and replace each with a number that has a reason, where the number lives: the conversation bound (200 comments / 400,000 characters, item 3), the size backstop (300 files / 30,000 lines, item 4), and the deadline (20 minutes), job timeout (30 minutes), step cap (200), model timeout (180 seconds), model retries (1), shell ceiling (300 seconds), and the shell environment's allowlist, all item 5; and the reviewer's slice of the deadline (13 minutes) and whether the verifier needs a step cap of its own, item 6.

The decisions under "Undecided" in `.agents/docs/architecture.md` settle here too — each needs a real run.

Done when: every number here carries a measured reason, and nothing is left under "Undecided" in `.agents/docs/architecture.md`.

## Not On This Roadmap

Named so nobody has to guess. Everything under "Out Of Scope" in `.agents/docs/functional-requirements.md` also applies.

- A second forge, model provider, or compute target. The swappable backend and the single model-client construction site are as far as this goes.
- Any store of past reviews. Coral reads the pull request.
- GitHub Enterprise Server. The `$/` reference does not exist there; supporting it means a second packaging answer, not attempted.
