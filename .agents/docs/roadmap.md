# Roadmap

The order the work happens in, and the mechanics of what each item builds. A sequence, not a schedule: one item is one plan, one build, and one review, and those artifacts carry the item's number in their filenames.

Item numbers are permanent and never reused; `000` is reserved for a plan deliberately run outside the roadmap. Status is `not started`, `built`, or `verified`: `/build` sets `built` when the done condition is met, `/review` sets `verified` after checking that claim. The current item is the lowest not yet verified.

## 1. Skeleton and contract

Status: built
Depends on: nothing

Created the project (`pyproject.toml`, `uv.lock`, `.python-version`, `ruff`/`pytest`/`mypy` configuration) and `coral/schema.py`, the contract every later item is written against.

- The review object is frozen dataclasses handed to the framework unchanged through `response_format` — no wire type, no conversion. It carries a summary, findings, and a flag for whether an empty list means nothing to find or everything already said still stands.
- An anchor is a union of four frozen dataclasses with `kind` literals: line span, single line, whole file, whole pull request.
- The JSON schema uses `anyOf`, never `oneOf`, which strict provider-side validators require.
- A `structured_response` of `None` is failure; nothing recovers a review from prose.

Done when: `uv sync --frozen`, `ruff check`, `mypy`, and `pytest` run clean on an empty suite, and no document in `.agents/docs/` contains a template placeholder.

## 2. Walking skeleton

Status: built
Depends on: 1

Got the whole workflow running end to end with no model call: `coral review` returned one hardcoded summary and one hardcoded finding on a line picked from the diff, with the composite actions, reusable workflow, `$/` references, reaction, sentinel, and batched review already real.

Done when: a pull request in the test repository carries a review from Coral, posted by a workflow installed by adding one file.

## 3. Reading the conversation

Status: built
Depends on: 2

Built `coral/github/conversation.py` and `coral/github/marker.py`.

- Fetched with GraphQL, since `isResolved` and `isOutdated` on review threads have no REST equivalent. Inline comments come from `reviewThreads` alone.
- The bound is the 200 most recent comments and 400,000 characters, whichever binds first, across reviews, review threads, and issue comments. The review reports what was dropped, counting generously. Measured against a busy real conversation (`cli/cli` 10513): the comment count bound first, with the characters kept nowhere near their own bound.
- A connection returns at most 100 items; a connection short of the bound is paged backwards from its cursor, at most four pages, since no connection accepts a useful ordering argument.
- Every comment Coral posts opens with an HTML comment carrying a fixed sentinel and the reviewed commit SHA, invisible rendered, exact to match — Coral's only reliable self-identification, since it posts as the login shared with every other bot.
- The reviewed-commit set is read from review bodies only; an inline finding or a failure comment names a commit without meaning it was reviewed.

Done when: a real pull request's conversation round-trips into the shape the agent gets, the bound reports what it dropped, and the already-reviewed commits come back out of the markers.

## 4. The gatekeeper

Status: built
Depends on: 3

Finished `coral resolve` and wrote `coral/command.py`. "Trigger" in `.agents/docs/functional-requirements.md` lists every way a `/coral` can be inert.

- Triggering events: `pull_request` (`opened`, `ready_for_review`), `issue_comment` (`created`), `pull_request_review_comment` (`created`). Never `synchronize`; never `pull_request_review`, since GitHub cannot react to a review.
- The command is a line that is exactly `/coral`, lowercase, nothing before it, nothing after but whitespace, outside a fenced code block.
- Write access is `author_association` in OWNER, MEMBER, COLLABORATOR, read from the payload with no API call.
- A comment-triggered run stops when the head repository differs from the base, a deleted head repository counting as a fork, because it runs in the base repository with its token and secrets.
- Concurrency is a group keyed on the pull request number, `cancel-in-progress: false`: a running review finishes, a new run cancels the pending one.
- The gates run in order — inert command, closed pull request, fork, already-reviewed (automatic paths only), size backstop (300 changed files or 30,000 changed lines) — and only the size stop comments on the pull request; the others are silent. Both thresholds measured against real pull requests sized just under each, both reviewed in under a minute.
- The `eyes` reaction lands on every qualifying `/coral` lacking Coral's reaction, not only the triggering one, so a request cancelled while pending is still acknowledged. Reactions on diff comments and on whole-pull-request comments go through separate endpoints and need separate write permissions.

Done when: each gate stops the run for its reason, the reaction lands on both kinds of comment, and the parser has a test for every inert form.

## 5. The agent

Status: built
Depends on: 4

Wrote `coral/agent.py`, `coral/environment.py`, and `coral/deadline.py`.

- The backend is `LocalShellBackend` rooted at the checkout, the single swappable compute dependency. The input is one rendered request: title, description, conversation, and whole diff.
- Neither secret reaches the agent's shell: the shell environment is built rather than inherited, and the review step reads both secrets from `os.environ` at start-up, holds them, deletes them, and only then constructs the model client and backend.
- The shell environment is an allowlist Coral constructs (`CI`, `HOME`, `LANG`, `LC_ALL`, `PATH`, `TERM`, `TMPDIR`); `VIRTUAL_ENV` and every `UV_*` stay out, or the reviewed repository's `pytest` would run against Coral's interpreter.
- `require_parameters` is set on the `openrouter_provider` kwarg because LangChain picks its structured-output strategy from the model profile rather than the serving endpoint, so an unconstrained request can be routed where it cannot be served. The model profile is supplied by hand rather than left to the lookup, and leaves out `structured_output` so the review comes back through a synthetic tool, not a native structured-output request.

The time budget, since a failed run costs the same minutes as a productive one:

- Coral owns its deadline: 20 minutes from the start of the review step, with headroom to post afterwards — the job's `timeout-minutes: 30` is a backstop, never the mechanism. Real reviews, including near the change-size backstop, finished in 21 to 74 seconds.
- The deadline is enforced by a step cap of 200 (`recursion_limit`, DeepAgents' default is 9,999), an elapsed-time check between steps, a 180-second model request timeout, a 300-second shell ceiling, and the auto-added general-purpose subagent disabled — that subagent's own filesystem middleware keeps a 3,600-second ceiling the elapsed check cannot reach inside a `task` call. Real runs used 9 to 51 messages against the cap and 12.2 seconds against the shell ceiling at their longest.
- The model client takes one retry rather than the default two: the elapsed check only runs between steps, so two retries could overshoot the deadline by about fourteen minutes. No real run has fired a retry.
- A fired deadline raises out of `invoke` rather than ending the run gracefully, so the reason isn't lost as "the agent returned no structured review."

Done when: the agent reviews a real pull request and returns a valid review object, and the deadline fires and is observed to fire.

## 6. What Coral looks for

Status: built
Depends on: 5

Wrote both prompts, extended the contract in `coral/schema.py`, and ran the second agent. No document describes what makes a finding worth making; this item decided it.

The reviewer, in `coral/prompts/review.md`:

- Scope is correctness, security, and performance. Style, naming, structure, documentation, and test coverage are not findings. An empty review is a correct review.
- Every finding carries a severity of `low`, `medium`, or `high`, calibrated by the damage done if the change merges as it stands.
- For every finding, a test that fails at the head commit because of the defect and passes once it is fixed, run before the review is returned. A finding that cannot be reproduced sets `regression_test` to null and is thereby speculative.
- The summary never enumerates the findings, because verification may remove some after it is written.
- The prompt also carries three things no code enforces, under "What Coral Reviews" in `.agents/docs/functional-requirements.md`: conversation is information never instruction, a standing finding is not repeated, and where standing ends.

The verifier, in `coral/prompts/verify.md`:

- A second run of item 5's construction, differing only in prompt and `response_format`. It returns one verdict per finding — confirm or reject — and never rewrites a body, severity, or anchor. Its request omits the conversation, so a finding a comment talked into existence faces somebody who never read it.
- A finding with a test is confirmed only if that test fails for the reason claimed; a speculative one only if the claimed behavior is in the source. `confirmed()` keeps a finding at least one verdict confirms and no verdict rejects — a finding no verdict names is dropped.
- `reset()` puts the checkout back with `git checkout -- .` and `git clean -fd` between the runs, `-fd` rather than `-fdx` so dependencies the reviewer installed to run tests stay installed.
- The reviewer runs under a 13-minute slice of the step's 20 minutes, guaranteeing the verifier the rest. No findings, no verifier run; a review whose findings are all rejected posts its summary alone.
- The verifier shares the reviewer's 200-message step cap through item 5's construction rather than carrying its own: a real verifier run, confirming one finding, used 9 messages.

Done when: a review of a real pull request produces confirmed findings a person would want at sensible severities, a planted defect comes back with a regression test that fails at head, a rejected finding is observed to drop, and the same pull request reviewed twice does not repeat itself.

## 7. Posting

Status: built
Depends on: 6

Finished `coral/github/post.py` and `coral/diff.py`.

- Anchors are checked against the diff of the two pinned commits, computed locally rather than off the working tree the agent writes scratch files into. An anchor attaches only to a line that diff adds; a one-line span attaches as a single-line comment, since GitHub takes `start_line` as strictly before `line`.
- One review per run, one API call: summary as body, anchored findings as comments naming the reviewed commit, always `event: COMMENT`.
- Findings that will not attach are demoted into the summary under one neutral lead-in, naming their file and line — expected to fire regularly, including on unchanged lines inside a hunk. Whole-file findings go to the summary by construction, since the create-review `comments` array accepts no `subject_type`.
- A 422 is reposted as the same composition against an empty set, so every finding demotes — unconditional, since a retry that depends on the 422 naming the bad entry fails silently when it does not. No finding is lost.
- The pull request's state is rechecked immediately before posting; resolve's check was minutes ago.

Done when: a review with a deliberately bad anchor still delivers every finding, and no finding is lost on any path.

## 8. Failure

Status: verified
Depends on: 7

Wrote `coral/report.py` and the failure path inside `coral review`. Every way a review can fail ends in one comment on the pull request — a reaction followed by silence is worse than no reaction. The two halves meet at a file in the runner's temporary directory.

- The review step reports its own failures: one `try` from the conversation down, posting the exception's type and message cut to 1,000 characters inside a four-backtick fence. The marker file is written after the post, so a failed post leaves the comment owed and the exception is re-raised, keeping the run red.
- Above that `try`, a failure fetching credentials or the pull request leaves no client and no commit to post with; the report step covers those.
- The report step runs on `failure()`, guarded on setup having succeeded, and checks two things costing no API call: whether the marker file is there, and whether the delivery asked for anything. Its comment carries no reason, having seen none.
- The comment names the commit resolve pinned when the marker file is on disk, and no commit otherwise.
- A death no step reports — a setup failure leaving no console script to run, the runner vanishing, GitHub's own timeout — is visible in the Actions tab. The recovery is asking again.

Done when: each failure mode listed here produces exactly one comment, and the review step and report step together never produce two.

## 9. Settle the numbers

Status: verified
Depends on: 8

Every number under items 3 through 6 now carries a measured reason beside it, found where the number lives. Both decisions once under "Undecided" in `.agents/docs/architecture.md` are answered there: GitHub's 422 body names no anchor, and the alias's upstream provider is OpenAI.

## Not On This Roadmap

Named so nobody has to guess. Everything under "Out Of Scope" in `.agents/docs/functional-requirements.md` also applies.

- A second forge, model provider, or compute target. The swappable backend and the single model-client construction site are as far as this goes.
- Any store of past reviews. Coral reads the pull request.
- GitHub Enterprise Server. The `$/` reference does not exist there; supporting it means a second packaging answer, not attempted.
