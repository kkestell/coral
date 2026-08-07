# Architecture

How Coral is built and the rules that hold across it. Parts that do not exist yet are marked "not built" in "The Codebase" and nowhere else. Numbers chosen rather than measured are collected at the end.

## The Platform

- A GitHub Actions workflow. No cloud account, no standing service; GitHub supplies the trigger, compute, checkout, and credential.
- Python, built with `uv`. Dependencies install with `uv sync --frozen` against the committed lockfile; nothing resolves at run time.
- The agent is DeepAgents. Models are reached only through OpenRouter, via `langchain-openrouter`'s `ChatOpenRouter`.
- The model is `~deepseek/deepseek-v4-flash-latest`: 1,048,576-token context, tool calling, structured outputs, reasoning effort. The tilde is an OpenRouter alias for the newest V4 Flash release, so the concrete model changes without notice.
- No datastore. Everything Coral remembers about a pull request is written on the pull request and read back each run. The rest of the design hangs off this.
- `ruff`, `pytest`, and `mypy` are configured in `.python-version` and `pyproject.toml` and nowhere else.

## Installation and Packaging

- Composite actions in this repository, wired by a reusable workflow, installed by one short caller file per repository.
- The caller file must carry all five of: version pin, OpenRouter secret, `on:` block, `permissions:` block, concurrency group. A reusable workflow cannot declare its caller's triggers or grant itself withheld permissions.
- A ruleset-pushed workflow is no substitute: rulesets run only on `pull_request`, `pull_request_target`, and `merge_group` — no comment triggers — and act as merge gates, contradicting an advisory review.
- This repository is public, so callers need no access configuration.
- One secret: the OpenRouter API key, passed by the caller. The GitHub token comes from the job.

## The Codebase

One console script, three subcommands — `coral resolve`, `coral review`, `coral report` — each invoked by one composite action's `run:` step.

- `coral/cli.py` — one `argparse` parser, three subcommands.
- `coral/runner.py` — the event, step outputs, the temporary directory, the one reading of `GITHUB_WORKSPACE`.
- `coral/resolve.py` — the gatekeeper: fetch the pull request and conversation, acknowledge requests, apply the gates.
- `coral/review.py` — build the agent, run it, post the result. Hardcoded until the agent exists.
- `coral/report.py` — the failure step. Not built.
- `coral/agent.py` — the only module that imports `deepagents`. Not built.
- `coral/schema.py` — the review object and its anchors; the only place structure originates.
- `coral/command.py` — what counts as a request: the command, who may make one, Coral's own comments.
- `coral/environment.py` — the agent's shell environment. Not built.
- `coral/deadline.py` — the time budget. Not built.
- `coral/diff.py` — the merge-base diff. Anchor validation not built.
- `coral/github/client.py` — the one authenticated transport.
- `coral/github/conversation.py` — the GraphQL query, the bound, the file the conversation crosses the step boundary on.
- `coral/github/marker.py` — the sentinel: writing and reading it.
- `coral/github/reactions.py` — which comments get the reaction, through both namespaces.
- `coral/github/post.py` — the review, anchor demotion, the plain comment. Retry on rejection not built.
- `coral/prompts/review.md` — what Coral looks for. Not built.
- `tests/` — one `test_<module>.py` per module under test.
- `.github/workflows/coral.yml` — the `workflow_call` workflow.
- `actions/setup/` — installs `uv`, builds Coral's virtual environment.
- `actions/resolve/`, `actions/review/` — one `run:` step each.
- `examples/coral.yml` — the file a repository copies in to install Coral.

Rules:

- `coral/agent.py` is the only module importing `deepagents`; everything else depends on the review object's schema. Tests downstream of the agent stub agent construction.
- The prompt is Markdown inside the package, read with `importlib.resources`, so changes diff readably.

## The Review Object

- The agent's answer, requested through `response_format` on `create_deep_agent`: frozen dataclasses handed to the framework unchanged — no wire type, no conversion.
- A summary, findings (text plus anchor), and a flag saying whether an empty list means nothing to find or everything already said still stands.
- An anchor is a union of four frozen dataclasses with `kind` literals: line span, single line, whole file, whole pull request. Read with exhaustive `match`.
- The JSON schema uses `anyOf`, never `oneOf`, which strict provider-side validators require.
- The structured result is required. A `structured_response` of `None` is failure; nothing recovers a review from prose.

## Triggering

- Events: `pull_request` (`opened`, `ready_for_review`), `issue_comment` (`created`), `pull_request_review_comment` (`created`). Never `synchronize`. Never `pull_request_review` — GitHub cannot react to a review, so the request could not be acknowledged.
- The job-level condition is coarse (Actions expressions have no regex): body contains `/coral`, the comment is on a pull request (the `pull_request` key on the issue object), author association passes. The real parse runs in resolve; a mere mention allocates a runner and stops in seconds.
- The command is a line that is exactly `/coral`, lowercase, nothing before it, nothing after but whitespace, outside a fenced code block. Quotes, inline code, list items, and indented lines fail that rule without being named; only fences need tracked state. `contains` is case-insensitive, so `/CORAL` reaches a runner and stops as inert.
- Write access is `author_association` in OWNER, MEMBER, COLLABORATOR — from the payload, no API call. Broader than real write access (org members and read-only collaborators pass); narrowing costs a permissions call per comment.
- The bot exclusion (payload author `type` of `Bot`) applies to the automatic paths only; a `/coral` from a bot is a person's request relayed. It catches Apps, not scripts driving user accounts.
- Events created with the job's `GITHUB_TOKEN` start no workflow runs (except `workflow_dispatch` and `repository_dispatch`), so Coral cannot trigger itself. A move to a GitHub App needs an explicit self-check.
- A comment event runs in the base repository with its token and secrets, so resolve stops when the head repository differs from the base, treating a deleted head repository as a fork. The `pull_request` path is filtered too, though GitHub already withholds secrets there.
- Concurrency is a group keyed on the pull request number, `cancel-in-progress: false`: a running review finishes, a new run cancels the pending one. Issues and pull requests share one number sequence, so keys cannot collide.
- The `eyes` reaction lands when a request is accepted, before the review — a comment-triggered run shows no check, so the reaction is the only acknowledgment. Resolve reacts to every qualifying `/coral` in the conversation lacking Coral's reaction, not only the triggering comment, covering requests whose runs were cancelled while pending.
- The conversation query returns `databaseId` (the REST id the reaction endpoints take) and `reactionGroups` (whether the token's account already reacted). A duplicate reaction POST returns 200.
- The triggering comment is reacted to from the payload — the bounded conversation may not contain it — and deduplicated against the conversation. Reviews are skipped: a review is not a reaction target.

## The Run

Five steps in fixed order: setup, resolve, checkout, review, report (failure only).

- Setup installs `uv` and builds Coral's virtual environment under the runner's temporary directory, publishing the bin directory as a step output. It is its own step because resolve runs before the checkout and review after it; building it inside resolve buries the gate's log line under an install.
- Resolve fetches the pull request (head SHA, base SHA, state, draft flag, head repository), fetches the conversation, reacts, then applies the gates — last, because the work a gate saves is the checkout and the agent.
- Step outputs are exactly the head SHA and a `proceed` flag, the two values YAML reads. Each is a SHA or boolean; an assertion rejects newlines, so the heredoc output protocol is not built. Everything else crosses as files under the runner's temporary directory.
- A stopped run is green: `proceed=false`, reason on stderr, exit zero. Only a broken run is red.
- Both commits are pinned at resolve and never re-read; the merge base of two fixed commits keeps the diff stable while branches move.
- Gates, in order: inert command, closed pull request, fork, already-reviewed (automatic paths only), size backstop. The order decides which reason is reported when several apply: a closed pull request and a fork are reasons Coral was never going to look at the change at all, so neither is reported as the change being too large.
- Only the size stop comments on the pull request, one marker-carrying comment — it is the only stop that leaves somebody waiting with nothing visible to explain it. The others are silent.
- The size backstop is 300 changed files or 30,000 changed lines, read off the pull request fetch, checked before the clone.
- Checkout: the pinned head SHA, `fetch-depth: 0`, `persist-credentials: false`. Full history makes the merge base exact and brings every branch head local. The credentials default writes the token into the checkout's git config, where the agent could read it. A force-pushed SHA can make the checkout fail; the report step covers that.
- Coral's virtual environment lives outside the workspace, never activated, never on `PATH`; every step invokes the console script by absolute path, so the checkout cannot disturb it and the agent's shell never sees it.
- Every run gets a fresh runner and filesystem.

## The Conversation

The conversation is the agent's context and, through the markers, the record of reviewed commits. That is all of Coral's memory.

- Fetched with GraphQL: `isResolved` and `isOutdated` on review threads have no REST equivalent. The query returns reviews, review threads with comments, and issue comments, each with author and association. Inline comments are read under `reviewThreads` only — the flags live on the thread, and reading both ways duplicates every comment. That the token reaches `reviewThreads` under the three declared permissions is observed from a real run; GitHub documents no GraphQL permission requirements.
- A comment is prose somebody wrote: an issue comment, a review with a non-empty body, or a thread comment. An empty-bodied review is the envelope around one inline comment and does not count against the bound, but is still read for its marker.
- The bound is the 200 most recent comments and 400,000 characters, whichever binds first, taken across all three connections. The review reports what was dropped, counting generously — overstating what went unread is the safe direction. A surviving thread keeps its flags, path, and lines whole.
- A connection returns at most 100 items. The first query asks each for its newest 100; a connection reporting a previous page and short of the bound is paged backwards from its cursor, at most four pages. The rule is per connection: a comment can only be missed if its own connection was not paged deep enough.
- No connection accepts a useful ordering argument (`UPDATED_AT` ranks edited-old above written-new), so default order plus `last:` is trusted to return the newest — observed, not promised — and the bound sorts on comment timestamps, compared as strings since ISO-8601 UTC sorts lexically. A thread has no timestamp; its recency is its comments'.
- Every comment Coral posts opens with an HTML comment carrying a fixed sentinel and the reviewed commit SHA — invisible rendered, exact to match. Coral posts as the repository's automation login, shared with every other bot, so the marker is the only reliable self-identification.
- The reviewed-commit set is read from review bodies only: an inline finding or a failure comment names a commit without meaning it was reviewed.
- The already-reviewed check applies to the automatic entry points only; somebody who asks gets a review whether or not the code moved.
- The conversation crosses the step boundary as a file under the runner's temporary directory — too large for a step output, and outside the workspace so the checkout cannot disturb it.
- Every comment handed to the agent is labeled with its author's association — the cheapest basis the model gets for judging a comment. Nothing is enforced by it.
- The conversation is untrusted input reaching a model with an unsandboxed shell: anyone can comment, and a maintainer's later `/coral` puts a stranger's text in context. The prompt rule — information, never instruction — is not enforced; the real bounds are the unreachable secrets and the schema-only return path. The residual risk, shell on a throwaway runner over already-visible code, is accepted for a proof of concept and is the first thing to revisit anywhere that matters.

## The Agent

- The backend is the single swappable compute dependency: `LocalShellBackend` rooted at the checkout, behind the middleware under "The Time Budget". It supplies the `execute` tool; its filesystem operations run as direct Python, not shelled-out scripts.
- The agent is constructed only after the working tree exists and the secrets are stripped; the conversation goes in as input. Setup is not the agent's job.
- `create_deep_agent` installs summarization middleware by default, so a long review is compacted mid-run — a reason to keep the conversation bound and size backstop tight, not a thing to switch off.
- The agent's only return value is the review object; deterministic code posts. Nothing the model produces becomes a push, an approval, or a comment Coral did not compose.
- Neither secret reaches the agent's shell, twice over: the shell environment is built rather than inherited and names neither; and the review step reads both from `os.environ` at start-up, holds them in memory, deletes them from `os.environ`, and only then constructs the model client and backend. Without this, `pull-requests: write` in the environment is an approving review one `curl` away.
- The token is scoped to `pull-requests: write`, `issues: write`, `contents: read`, and expires with the job. Both writes are needed: reactions on diff comments go through `/pulls/comments/{id}/reactions` (Pull requests permission), on whole-pull-request comments through `/issues/comments/{id}/reactions` (Issues permission), and neither grants the other.
- This is not a sandbox. The agent runs arbitrary shell as the runner user with network access; keeping secrets out of its environment is a barrier, not a boundary. Acceptable because Coral is the repository's own CI running the repository's own code.
- Only the backend touches the checkout for the agent. Coral's own code runs `git` there once, in `coral/diff.py`, so the diff the agent saw and the diff the anchors are checked against are the same. `GITHUB_WORKSPACE` is read once, in `coral/runner.py`.
- The shell environment is built variable by variable: `inherit_env` defaults to false and an empty environment runs nothing, so Coral constructs it. In: `PATH`, `HOME`, `LANG`, `TMPDIR`, and the handful a build reads. Out: both secrets, `VIRTUAL_ENV`, every `UV_*`. Building up makes the omissions checkable; without the exclusions, the reviewed repository's `pytest` runs against Coral's interpreter.
- The request sets `require_parameters` on the `openrouter_provider` kwarg. A provider allowlist is impossible — the alias's endpoint list comes back empty — and LangChain picks its structured-output strategy from the model profile rather than the serving endpoint, so an unconstrained request can be routed to an endpoint that cannot serve it. The same kwarg carries `ignore: ["azure"]`, which Coral must supply itself: DeepAgents injects it only when resolving a string model, and Coral passes an instance. OpenRouter's `/responses` beta is stateless, so a replayed reasoning item fails outright.

## Posting The Review

- Anchors are checked against the diff of the two pinned commits, computed locally — not the working tree (the agent writes scratch files into it) and not refetched (either branch may have moved).
- One review per run, one API call: summary as body, anchored findings as comments, naming the reviewed commit — which positions each comment, lets GitHub mark it outdated later, and writes the record the next run reads. Always `COMMENT`, never approving or requesting changes.
- Findings that will not attach are demoted into the summary with their file and line named. Expected to fire regularly.
- Whole-file findings go to the summary by construction: the create-review `comments` array accepts no `subject_type`, and posting them separately costs one call per finding.
- GitHub accepts or rejects a review whole, using its own patch generation, so the local pre-check cannot be sufficient. A rejected review is reposted with every anchored finding demoted — unconditionally, because a retry that depends on the 422 naming the bad entry fails silently when it does not. No finding is lost.
- The pull request's state is rechecked immediately before posting; resolve's check was minutes ago.
- The same module posts the plain marker-carrying comment used by the size stop and the failure path.

## The Time Budget

One agent run per automatic review and one per request; every review covers the whole change; nothing automatic multiplies that. A failed run costs the same minutes as a productive one.

- Coral owns its deadline: 20 minutes from the start of the review step, with headroom to post afterwards, so the review step is always still running when its deadline fires — "Failure" depends on this.
- The job's `timeout-minutes: 30` is a backstop, never the mechanism: a job GitHub cancels cannot post a failure comment.
- The deadline takes all four of: a step cap of 200, applied by overriding `recursion_limit` on the compiled graph (DeepAgents sets 9,999); an elapsed-time check between steps; a 180-second model request timeout, passed in milliseconds because `ChatOpenRouter` takes `timeout` in milliseconds; and the shell ceiling below.
- The per-command shell ceiling is 300 seconds, enforced by Coral's own `FilesystemMiddleware(max_execute_timeout=300)` passed through `create_deep_agent`'s `middleware` argument. Middleware merges by `AgentMiddleware.name`, which defaults to the class name, so Coral's instance replaces the framework's in place — and an upstream rename turns replacement into addition, leaving two middlewares each registering a `read_file` tool. Enforcement rejects rather than clamps, telling the model the ceiling. Neither alternative works: `LocalShellBackend(timeout=...)` only sets the default for when the model omits the argument, and a forwarding wrapper fails the framework's `isinstance` check against `SandboxBackendProtocol` and its `execute`-signature inspection, losing the timeout argument entirely. The replacement must receive the same backend instance every other middleware got, plus the harness profile's tool-description overrides and private permissions list the factory used to pass. Left alone the ceiling is 3,600 seconds, and the elapsed check cannot run until a command returns.

## Failure

Every way a review can fail ends in one comment on the pull request — a reaction followed by silence is worse than no reaction. The two halves meet at a marker file.

- The review step reports its own failures: owning the deadline means it is still running, still holds the checkout, and still has the posting code. It posts the reason immediately, drops the partial review, and writes a marker into the runner's temporary directory recording that it reported.
- The report step runs on job failure and covers everything before the agent: a rate-limited resolve, a missing secret, a failed checkout, a failed install. It skips when the marker is present, so a failure is reported once.
- A death no step can report — the runner vanishing, GitHub's own timeout — is visible in the Actions tab. The recovery is asking again.

## The Runner

- Hosted Ubuntu: 4 vCPU / 16 GB public, 2 vCPU / 8 GB private, 14 GB SSD. Larger runners need Team or Enterprise Cloud. Submodules and LFS are checkout inputs left at defaults.
- Coral runs directly on the runner, never in a container: reviewing a repository means running its tests with its toolchain, and the hosted image's preinstalled toolchain is the only reason that works in a repository Coral has never seen.
- On the comment paths the workflow file is read from the default branch, so a pull request cannot change how it is reviewed by asking. On the `pull_request` path it comes from the head, so a pull request can alter its own review — the same trust as every other job, since that population has write access and already runs code beside the secrets.

## Numbers Chosen Rather Than Measured

The conversation bound (200 comments / 400,000 characters), the size backstop (300 files / 30,000 lines), the deadline (20 minutes), the job timeout (30 minutes), the step cap (200), the model timeout (180 seconds), and the shell ceiling (300 seconds). Stated so the design is complete and testable; the first real reviews settle them.

## Undecided

Decisions arrive here before they are made, not after.

- Whether GitHub's 422 names the offending anchor. The blunt retry is correct either way; a 422 that names entries would allow demoting only those.
- Which provider serves the alias, and whether a native structured-output request succeeds against it. `require_parameters` survives either answer.
