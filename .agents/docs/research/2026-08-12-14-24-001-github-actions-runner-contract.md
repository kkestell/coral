# GitHub Actions runner contract

Research record dated 2026-08-12. It consolidates platform facts established by earlier source reading and live checks in an installed test repository; it introduces no newly browsed platform claim.

## Workflow Revision Selection

- **Documented contract.** A `pull_request` run uses the pull request merge ref and therefore workflow code containing the proposed change, while `pull_request_target` runs in the base repository's context from its default branch. GitHub's secure-use guide, read 2026-08-08, warns that `pull_request_target` must not execute untrusted pull-request code with privileged access. A `pull_request` automatic path is replaceable by any same-repository branch, so automatic delivery must use `pull_request_target`, and only once untrusted file and shell access is isolated.
- **Documented contract.** `pull_request_target` runs in the privileged base context, so its token and secrets are not protected by the fork restrictions applied to `pull_request`. A caller-level same-repository condition must prevent a fork event from invoking the credentialed reusable job at all.
- **Documented contract.** `issue_comment` and `pull_request_review_comment` workflows run only when the workflow file exists on the default branch; the comment paths consequently use that branch's workflow revision. The pull-request event references were read from the GitHub Docs source during the 2026-08-06 triggering investigation.
- **Documented contract.** A `push` workflow is selected from the pushed ref. A branch deletion has an all-zero after SHA, and a new branch has an all-zero before SHA; neither supplies the two existing commits a range review needs.
- **Documented contract.** A reusable workflow runs at the repository and ref in the caller's `uses:` value. Inside it, the `github` context remains the caller's event context, while `job.workflow_repository` and `job.workflow_sha` identify the called workflow file. The reusable-workflow and contexts sources were read at `github/docs` commit `738593aef7b8d80183a376d5c692feefc0e8a5ff` on 2026-08-06.
- **Documented contract.** A `./` local-action reference resolves beneath `GITHUB_WORKSPACE`, which contains the repository checked out by the job, not automatically the reusable workflow's repository. A `$/` reference resolves to the repository and exact workflow or enclosing action commit where it appears. Runner `2.336.0` implements this rewrite in `ActionManager`; the feature became generally available on 2026-07-30 and was absent from GitHub Enterprise Server when read.
- **Coral conclusion.** The caller must pin the reusable workflow, and every action used by that workflow must resolve to the same immutable source or its own immutable SHA. The exact pull-request head SHA is data to checkout only after fork and event validation; a head branch name or merge ref is not an authority boundary.
- **Drift-sensitive fact.** `$/` availability, runner support, and GitHub Enterprise Server support must be revalidated before packaging depends on it. The retained evidence is runner `2.336.0`, not a permanent promise about older or non-hosted runners.

## Caller And Reusable Workflow Ownership

- **Documented contract.** The caller owns event triggers because the called workflow's event is `workflow_call`. The caller also owns the version pin and the initial `permissions` grant. A called workflow may narrow that grant per job but cannot elevate it.
- **Documented contract.** A called workflow may declare inputs, accepted secrets, job permissions, jobs, and job conditions. A caller passes secrets by declared name or, within the documented organization or enterprise boundary, by `secrets: inherit`; secrets do not automatically propagate through another reusable-workflow hop.
- **Documented contract.** Composite actions cannot read the `secrets` context. A workflow must pass a secret explicitly as an action input or invoking-step environment value. This is enforced by the runner's composite action schema, not merely recommended.
- **Documented contract.** Concurrency in a called workflow can cancel its caller when both use the same group, because the called workflow's `${{ github.workflow }}` names the caller. The retained packaging research therefore placed the per-pull-request concurrency group in the caller alone.
- **Coral conclusion.** Installation configuration belongs in the default-branch caller, alongside triggers, permissions, concurrency, secrets, and the version pin. Configuration in the checkout would let the change under review choose its reviewer.

## Job Boundaries And State Transfer

- **Documented contract.** Each GitHub-hosted job is assigned a fresh runner environment. `needs` orders jobs and exposes declared scalar outputs; files, processes, ordinary environment variables, `GITHUB_WORKSPACE`, and `RUNNER_TEMP` do not cross the boundary.
- **Observed behavior.** Live checks on 2026-08-07, with the workflow split into resolve, review, and publish jobs, observed ordered jobs, scalar outputs, artifact round trips, a read-only review token, publication after a killed review job, and full anchor fallback across the boundary.
- **Documented contract.** Job outputs are UTF-8 text intended for small values consumed by workflow expressions. GitHub's secret scanner may refuse an output that appears to contain a secret. Artifacts are retained server-side files and are the supported same-run channel for larger structured state.
- **Observed behavior.** With `actions/download-artifact` v8.0.1 at `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c`, a missing artifact requested by `name` fails, while an empty `pattern` match succeeds. Same-run downloads used the runner artifact token without adding `actions: read`; this was inspected on 2026-08-07 and exercised by the job-split live checks.
- **Coral conclusion.** Use outputs only for small control values that YAML must read, such as a decision, commit SHA, timeout, or authenticated ciphertext. Use short-retention artifacts for bounded conversation, subject, context, publication bodies, and failure details. Treat every artifact from an agent job as untrusted: a later privileged job revalidates the event, target commit, and allowed publication operation.
- **Coral conclusion.** Do not share an executable dependency cache from an agent job with a privileged job. A compromised review could seed code that a later resolve or publish job executes; independent installs are the price of the permission boundary.
- **Unresolved.** No surviving investigation established the complete cache key, version, branch-scope, eviction, and restore ordering contract. A clean build must revalidate those rules before using a cache for anything beyond disposable performance data, and must not let an agent-writable cache become privileged executable input.

## `GITHUB_TOKEN` And Permissions

- **Documented contract.** A job receives its own `GITHUB_TOKEN`; different jobs do not share one. The token is limited by the intersection of caller/repository policy and job `permissions`, and expires when the job ends. Once any explicit permissions are listed, unspecified permissions become `none`; `write` includes `read` for that permission.
- **Documented contract.** Events created with a repository's `GITHUB_TOKEN` do not start another workflow, except `workflow_dispatch` and `repository_dispatch`. This prevents self-triggering only while Coral posts with that token; a future GitHub App or personal token would require an explicit self-check.
- **Documented contract.** The REST permission data and rendered references read on 2026-08-06 establish these minimum operations: pull-request fetch uses `contents: read` or `pull-requests: read`; batched review creation uses `pull-requests: write`; issue-comment reaction uses `issues: write`; diff-comment reaction uses `pull-requests: write`; issue creation and label creation use `issues: write`. Reading and searching issues uses `issues: read`. The GraphQL conversation query's minimum fine-grained permission was not independently established; `pull-requests: read` is the conservative unresolved requirement.
- **Observed behavior.** A walking-skeleton live check on 2026-08-06 exercised both reaction namespaces and batched review creation. A write probe on 2026-08-07 confirmed that the separated review job could not write with its narrowed token.
- **Coral conclusion.** Resolve needs only the reads and acknowledgments it performs; review needs repository reads and, for main duplicate evidence, issue reads; publish alone needs review, issue, and label writes. No agent container receives any job token.

## Checkout, Workspace, Actions, And Caches

- **Documented contract.** `GITHUB_WORKSPACE` is the job's default working directory and is where checkout places the caller repository. `RUNNER_TEMP` is job-local temporary storage and is removed with the runner. `GITHUB_ACTION_PATH` names the installed directory of the currently running action; it is the reliable way for a composite action to reach files beside itself.
- **Documented contract.** `actions/checkout` persists its token in local Git configuration by default. `persist-credentials: false` prevents that credential from remaining readable in `.git/config`. `fetch-depth: 0` fetches full history; a merge-base review cannot rely on a shallow depth containing the required ancestry.
- **Coral conclusion.** Checkout only a commit SHA pinned and validated before checkout, never the pull request's branch name. Keep framework/runtime installation outside `GITHUB_WORKSPACE`, and keep transfer artifacts outside it, so checkout and untrusted workspace changes cannot replace either.
- **Documented contract.** A reusable workflow does not automatically checkout its own repository. Remote actions are downloaded beneath the runner action directory; relative actions resolve in the workspace; `$/` actions resolve at the enclosing workflow/action commit.
- **Drift-sensitive fact.** Hosted toolcache contents and paths are image observations, not stable dependencies. On 2026-08-07 `ubuntu-24.04` exposed `/opt/hostedtoolcache/<tool>/<version>/x64/bin` with Python, Node, and Go versions sufficient for the live fixtures. A rebuild must inspect the current image before relying on a particular tool or version.

## Concurrency And Cancellation

- **Documented contract.** A concurrency group permits at most one running and one pending run. With `cancel-in-progress: false`, a running run finishes; a newly queued run replaces the existing pending run. Pending order is not guaranteed.
- **Observed behavior.** Per-pull-request grouping supported serialized request handling in live review checks through 2026-08-08. Conversation scanning and reaction attribution allowed the surviving pending run to acknowledge requests whose own run was replaced.
- **Coral conclusion.** One pull request uses one group, with cancellation of the running review disabled. The one pending run represents all accumulated requests, so resolve must acknowledge every unacknowledged authorized request visible to it rather than only the event comment.
- **Coral conclusion.** Main pushes cannot share one repository-wide concurrency group: replacing a pending run would violate the requirement to review every pushed range. Keying main runs by pushed SHA permits concurrent publication and accepts a narrow duplicate-issue race.

## Container Isolation On A Hosted Runner

- **Coral conclusion.** A Docker container without `--privileged`, added host capabilities, or the Docker socket is expected to isolate processes and mounts while exposing only deliberate bind mounts. Live probes below, rather than a retained upstream-source citation, are the evidence this build used for that boundary.
- **Coral conclusion.** A container is not a separate machine. The Docker daemon is host authority: mounting its socket or using privileged mode defeats the boundary. The checkout copy is the only read-write host mount, and the hosted toolcache is read-only. Credentials and runner environment values are not container inputs.
- **Coral conclusion.** Repository code and agent shell commands run as root inside the container. Coral's orchestration and model client remain runner processes outside it, so only operations explicitly routed through the container gain its process, filesystem, resource, and credential boundary.
- **Observed behavior.** Isolation live checks on 2026-08-07 ran Python, Node, and Go tests and probed the container: no `Runner.Worker`, no runner home, an isolated PID 1, a read-only toolcache, and no Docker client path.
- **Observed behavior.** The complete file-tool boundary was probed and verified on 2026-08-08. Reads, writes, edits, searches, and commands shared the container filesystem; an over-memory read died inside the container rather than exhausting the runner process.
- **Coral conclusion.** Every agent-controlled file operation must cross the same container boundary as shell execution. Host-side convenience file APIs reopen the runner memory and filesystem surface even when shell commands are isolated.
- **Coral conclusion.** Enforce command time twice: an in-container timeout kills the command and its children, and a slightly longer runner-side backstop prevents a hung Docker client from blocking forever. Bound both stdout and stderr while draining them; truncating after an unbounded capture does not bound runner memory.
- **Coral conclusion.** Agent file tools need their own per-operation size limits even inside the container, and the runner-side transfer protocol needs a larger finite cap. A file tool that reads a whole file before paging it can still exhaust container memory; the resource limit contains that failure but does not make the operation useful.
- **Drift-sensitive fact.** The hosted image's Docker version, preloaded images, toolcache contents, CPU, memory, and disk change. On 2026-08-07 the inspected `ubuntu-24.04` image had Docker 28.0.4 and no preloaded Ubuntu image; these are revalidation inputs, not design constants.

## Timeouts, Failures, Artifacts, And Publication

- **Documented contract.** A hosted job's configured `timeout-minutes` ceiling was 360 minutes when read on 2026-08-07. Job timeout kills the job; no later step in that job can report after it. Step conditions implicitly require success unless a status function such as `always()` or `!cancelled()` changes that.
- **Observed behavior.** A live check on 2026-08-07 forced a one-minute job timeout; the later publish job ran without a review artifact and posted failure through the already-separated job boundary. Failure live checks the same day observed exactly one report for agent, resolve, checkout, and setup failures that left publication possible.
- **Documented contract.** An artifact upload guarded by `!cancelled()` may still run after an earlier failed step, but not after cancellation. A cancelled workflow therefore cannot promise a publication artifact or a reporting job.
- **Coral conclusion.** The application deadline must expire before the job timeout, leaving time to write a bounded failure reason and upload it. A later privileged publish job handles both ordinary payloads and the absence of an artifact from a job killed whole.
- **Coral conclusion.** A decline is a successful run with later work skipped; a broken review is a failed run. Publication must use a positive condition over the resolve decision plus `!cancelled()`, because implicit `success()` would skip the reporter after the failure it exists to report.
- **Observed behavior.** Forced anchor failures on 2026-08-07 observed GitHub's 422 body as `"errors":["Line could not be resolved"]`, with no offending array index. The safe retry demotes every inline finding and republishes one whole review.
- **Coral conclusion.** Build and byte-validate complete publication payloads before crossing the job boundary. Never publish a partial agent result, a truncated finding, or only the subset created before a later failure.

## Revalidation Checklist

- Revalidate the current GitHub-hosted image, runner version, `$/` support, job timeout ceiling, toolcache, Docker version, and action major versions.
- Revalidate undocumented connection ordering before relying on `last:` for recent review threads.
- Revalidate `pull_request_target` event payload fields and fork-secret behavior with a credential-free probe before exposing installation secrets.
- Revalidate same-run artifact missing-name and empty-pattern behavior when changing artifact action versions.

## Sources

- GitHub Docs source at `738593aef7b8d80183a376d5c692feefc0e8a5ff`, read 2026-08-06: workflow syntax, metadata syntax, contexts, reusable workflow configuration and calling syntax, secret passing, repository Actions access, concurrency, variables, token permissions, and hosted runners. Repository: https://github.com/github/docs
- GitHub's secure-use guide for `pull_request_target`, read 2026-08-08: https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target
- GitHub runner at `2009b20729fdf49c50a88e0ca368906c16a3129c`, version `2.336.0`, read 2026-08-06: https://github.com/actions/runner
- GitHub REST description at `e50419c4bb8f2d1d34735044bb3b410863dc0a10`, API description version `1.1.4`, and GitHub Docs permission data at `0b11cf08b8d4328a404753313d0dcd7f14bd97c6`, read 2026-08-06: https://github.com/github/rest-api-description and https://github.com/github/docs
- GitHub REST API version `2022-11-28` pages for reactions, issue comments, pull-request reviews, pull requests, issues, labels, and search; GitHub GraphQL schema and rate-limit documentation, read or queried 2026-08-06 through 2026-08-08.
- `actions/checkout` v7.0.1 at `3d3c42e5aac5ba805825da76410c181273ba90b1`, `actions/upload-artifact` v7.0.1 at `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`, and `actions/download-artifact` v8.0.1 at `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c`, inspected 2026-08-06 through 2026-08-07.
- GitHub-hosted runner image `Ubuntu2404-Readme.md` on `actions/runner-images` `main`, read 2026-08-07: https://github.com/actions/runner-images
