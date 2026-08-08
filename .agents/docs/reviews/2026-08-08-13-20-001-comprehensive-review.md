# Review: correctness, security, and complexity

A read of every module under `coral/`, the reusable workflow, composite actions, prompts, and
tests, against the requirements and architecture. The unit suite, `ruff check`, `ruff format
--check`, and `mypy` pass. This review does not treat an existing requirement as a reason to keep
code whose security or complexity is not justified.

Each finding carries a severity and a disposition. “Trivially fixable” means the intended behavior
is already specified. “Needs a decision” means the fix changes an accepted tradeoff or has more
than one reasonable shape.

## 2. Agent file tools run on the review runner, outside the container's limits

Severity: high

Disposition: needs a decision. The recommended direction is an execute-only tool backed by the
container.

`ContainerBackend` subclasses DeepAgents’ `LocalShellBackend` and overrides only `execute`.
`FilesystemMiddleware` therefore performs `read_file`, `glob`, `grep`, `write_file`, `edit_file`,
and `delete` in Coral's Python process on the runner. They operate on the checkout copy, so they do
not normally expose runner files. They do not use the container's memory, CPU, process, or command
time limits.

In particular, the inherited `read_file` reads a complete file before it slices the requested
lines. A model that reads a large tracked file can exhaust the review runner's memory. This violates
the architecture claim that every agent operation is bounded by the container. It also makes the
container backend more complicated than it needs to be.

Remove the inherited filesystem backend from the agent boundary. A small `execute` tool can call
`container.execute`, and the model can use normal shell commands inside the container for reads,
writes, searches, and scratch tests. That removes the host-side file path and avoids maintaining a
subclass whose safety depends on DeepAgents internals. Keeping file tools instead requires a
container-backed filesystem implementation with equivalent size and time limits.

## 3. A same-repository pull request can replace the workflow that receives secrets

Severity: high

Disposition: needs a decision. It depends on item 2 if the review still executes pull-request code.

`.github/workflows/review.yml` uses `pull_request`, and the reusable workflow receives the
OpenRouter secret and a write-scoped GitHub token. GitHub runs `pull_request` workflow code from
the pull request's merge branch. A user who can create a same-repository branch but cannot change
the default-branch workflow can change `review.yml` and run arbitrary steps with those credentials.
The current fork gate does not help, because this is a same-repository branch.

The architecture records this fact but accepts a much larger authority boundary than Coral's
container design suggests. GitHub documents the distinction in its guide on
[`pull_request_target`](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target):
that event runs the workflow from the default branch, while a `pull_request` event runs it from the
pull request's merge branch.

Move automatic pull-request delivery to default-branch workflow code, then pass the event's pinned
head SHA into the isolated review path. `pull_request_target` is one possible mechanism. It is safe
only after item 2, because checking out the head and executing it outside the container would create
a privileged pull-request execution path. Keeping the current behavior is an explicit decision to
give every same-repository branch writer the repository's Action secrets.

## 5. Input and publication text have no end-to-end size limit

Severity: medium

Disposition: needs a decision.

The pull-request gate limits changed lines and files, but not diff bytes. One changed very long line
or a large binary file can pass the gate. `diff_text` captures the complete `git diff` in memory and
`render_request` adds it to the model input. The review body, finding bodies, regression-test
content, and issue titles also have no schema limits before they reach GitHub.

The result can exceed runner memory, a selected model's context window, or GitHub's comment and
issue limits. An oversized anchored review gets a 422 and retries with the same oversized summary.
An oversized main-push issue fails publishing after the review has completed. The model listing is
used to choose a framework profile, but no code compares the assembled request with that model's
context limit.

Choose one byte budget for the diff and whole agent request, then make the pull-request size gate
and `git` capture enforce it. Choose publication limits that leave room for Coral's generated text,
and validate the structured model output before artifacts are written. This requires deciding
whether an oversized change is declined, summarized deterministically, or rejected for only models
with insufficient context.

## 7. Concurrent main-push reviews can create duplicate issues

Severity: medium

Disposition: needs a decision.

The caller's concurrency key includes `github.sha`, so two pushes to `main` run at the same time.
Each review performs its duplicate search before either publishing job creates an issue. If both
confirm the same existing defect, both searches find nothing and both publishing jobs file it.

Changing the group to one repository-wide main-push group is not sufficient. GitHub Actions keeps
only one pending run in a concurrency group, which would drop a main push that the requirements say
must be reviewed. A publish-time recheck narrows but does not eliminate the race.

Choose whether a short duplicate window is acceptable or whether main-push publication needs a
serialized, durable coordination mechanism. The answer constrains the no-datastore design rather
than a local function.

## Holds up

The prior fixes for diff headers, useful git failures, reaction failures, exact collaborator
permissions, and forged-marker attribution are present. The current conversation parser correctly
uses `viewerDidAuthor` when rendering authorship. The encrypted management-key handoff keeps the
minted key out of job outputs in cleartext. The main-push verifier exposes bounded issue-reading
tools rather than a GitHub credential. The post step still stamps the pull-request commit and event
itself, so the review job cannot approve or retarget a review.

