# Reusable Workflow And Composite Action Packaging

Status: Living document (last updated 2026-08-06)

## Question

A project wants to publish a pull request review job that other repositories install by adding one short file. The job needs several steps, a third-party API key, a write-scoped token, and a version somebody else can pin. The publishing repository holds both the `workflow_call` workflow and the composite actions the workflow's steps run.

Three things about that arrangement are not obvious, and each has a different answer than the naive reading suggests. A step inside the called workflow runs on a runner whose workspace belongs to the *calling* repository, so a path-relative action reference does not find the publisher's own tree. A secret named in the calling repository has to travel into a workflow file the caller does not own, and then into a composite action, which is a second boundary with different rules. And a private publishing repository is reachable by other repositories only under conditions GitHub sets rather than the publisher.

The question this document answers: how do projects reference an action that lives beside their reusable workflow, how do they move an API key across both boundaries, and what does a private publishing repository cost.

## Summary

GitHub added a syntax for the first problem on 2026-07-30 and made it the documented recommendation. A `uses:` value beginning with `$/` resolves to the repository holding the file the reference appears in, at the commit that file is running from. Before that, the field had three incompatible workarounds, and every one of them is still visible in shipped code. Two of the repositories read here adopted `$/` within the last week.

The second problem has a settled answer with a real trap in it. A reusable workflow's job can read the `secrets` context, either from secrets the caller passed by name or from `secrets: inherit`. A composite action cannot read the `secrets` context at all, and that is enforced by the schema rather than by convention. The key has to cross into the composite action as an input or as an environment variable set on the step that calls it.

The third problem has a hard answer. A private publishing repository is reachable only from private repositories, only within the same account or organization, and only after somebody changes a setting on the publishing repository.

Where the field splits is on the first problem, and the split turns on how much the publisher is willing to spend to make the version the caller pinned propagate to the actions the workflow runs. The four surviving approaches range from hardcoding a mutable branch name to running a JavaScript action that reads the run's own OIDC token to discover which commit it is.

## What the platform decides

These are the platform's rules rather than any project's choice. Documentation citations are to the `github/docs` sources at commit `738593aef7b8d80183a376d5c692feefc0e8a5ff`. Runner citations are to `actions/runner` at commit `2009b20729fdf49c50a88e0ca368906c16a3129c`, which carries version `2.336.0` in `src/runnerversion`.

### A relative action reference resolves against the workspace, not the repository

The workflow syntax reference states it plainly for `./path/to/dir`: "You must check out your repository before using the action, and the `./` path resolves against the runner's workspace rather than the repository of the running workflow. For most cases, use the `$/` syntax shown above instead." Its comparison table describes `./path/to/action` as resolving to "A path in the runner's checked-out workspace, relative to the default working directory", and gives its recommended use as "Edge cases only". (`docs/content/actions/reference/workflows-and-actions/workflow-syntax.md`, the `jobs.<job_id>.steps[*].uses` section, lines 620-641.)

The runner is where that is decided. A reference whose repository type is the string `self` becomes a filesystem path under the workspace, with no download at all.

- `runner/src/Runner.Worker/ActionManager.cs:699-705` — when the reference's `RepositoryType` equals `PipelineConstants.SelfAlias`, the action directory is `executionContext.GetGitHubContext("workspace")` joined with the reference's path. `runner/src/Sdk/DTPipelines/Pipelines/PipelineConstants.cs:44` gives that alias the value `"self"`.
- `runner/src/Runner.Worker/ActionManager.cs:715-719` — every other repository reference is a download, landing under the runner's actions directory keyed by repository name and ref.

A reusable workflow does not check out its own repository. The job's workspace holds whatever the job's own steps put there, which for a review workflow is the repository under review. So a `./` reference inside a reusable workflow looks for the publisher's `action.yml` inside the caller's source tree, and fails with a message about not finding `action.yml`, `action.yaml`, or `Dockerfile`.

### The self repository reference resolves against the file it appears in

The `$/` prefix, generally available on 2026-07-30, is the platform's answer. The documentation states the rule and names this exact case:

> `$/` always resolves against the repository of the file it appears in, not the repository that called it. For example, if a reusable workflow in one repository is called by a workflow in another repository, a `$/` reference in the called workflow resolves to the called workflow's repository, not the calling workflow's repository. This makes `$/` reliable for action composition, where a relative `./` path would instead resolve against whatever is checked out in the caller's workspace.

That is `workflow-syntax.md:616`. The same section gives four further constraints. The reference resolves to "that repository at the running commit (the same SHA as the running workflow or action)". No checkout is needed first. An `@{ref}` suffix is invalid, so `$/actions/my-action@v1` is rejected. And the syntax is not available on GitHub Enterprise Server. The composite action metadata reference repeats all of this for a composite action's own steps (`docs/content/actions/reference/workflows-and-actions/metadata-syntax.md:352`), and the reusable workflow calling syntax adds a same-repository form, `$/.github/workflows/{filename}`, which it calls the recommended way to reference a reusable workflow in the same repository (`docs/data/reusables/actions/reusable-workflow-calling-syntax.md`).

The runner shows what the resolution actually is. It is a rewrite into an ordinary remote reference, performed before any download happens.

- `runner/src/Runner.Worker/ActionManager.cs:190-201` — the resolution runs when the `actions_self_repository` feature variable is set, and takes the repository and commit from `executionContext.JobContext.WorkflowRepository` and `JobContext.WorkflowSha`. The comment beside it reads: "job.workflow_repository/workflow_sha point to the repo containing the workflow file — correct for both regular and reusable workflows." `runner/src/Runner.Common/Constants.cs:184` names the feature variable.
- `runner/src/Runner.Worker/ActionManager.cs:1553-1580` — `ResolveSelfRepositoryReferences` walks the step list, and for each reference whose type is `selfRepository` it overwrites the type with `github`, the name with the repository, and the ref with the commit. From that point the reference is indistinguishable from one a workflow author wrote out by hand.
- `runner/src/Runner.Worker/ActionManager.cs:707-711` — a `$/` reference that reaches action loading unresolved throws rather than falling back to the workspace.

Nesting resolves against the nearest enclosing action rather than against the workflow. `runner/src/Runner.Worker/ActionManager.cs:319-351` groups each composite action's child steps by their parent and resolves each group against that parent's repository and ref, falling back to the workflow's own only when the parent is not a GitHub repository reference. The test at `runner/src/Test/L0/Worker/ActionManagerL0.cs:3738-3810` pins the consequence: a `$/lib/bar` inside a composite action fetched from `external/foo@v1` resolves to `external/foo@v1/lib/bar`, not to the workflow's repository. Chains are bounded at nine levels by `runner/src/Runner.Common/Constants.cs:46`.

The two properties this depends on are documented and carry one restriction. The `job` context lists `job.workflow_ref`, `job.workflow_sha`, `job.workflow_repository`, and `job.workflow_file_path`, each marked "not available on GitHub Enterprise Server". `job.workflow_ref` is described as "The full ref of the workflow file that defines the current job... For jobs defined in a reusable workflow, this refers to the reusable workflow file." (`docs/content/actions/reference/workflows-and-actions/contexts.md`, the `job` context table.)

This matters because the `github` context does not behave that way. The reusable workflow reference states: "When a reusable workflow is triggered by a caller workflow, the `github` context is always associated with the caller workflow." So `github.repository`, `github.sha`, `github.workflow_ref`, and the whole event payload describe the caller. There is no property on the `github` context that names the called workflow's own repository.

### A secret reaches the job either by name or by inheritance

A called workflow declares the secrets it accepts under `on.workflow_call.secrets`, each with a description and an optional `required` flag, and the caller supplies them by name in the calling job's `secrets:` block. The alternative is `secrets: inherit`, which the documentation scopes: "Workflows that call reusable workflows in the same organization or enterprise can use the `inherit` keyword to implicitly pass the secrets." (`docs/data/reusables/actions/pass-inputs-to-reusable-workflows.md`.)

Inheritance does not travel further than one hop. "Secrets are only passed to directly called workflow, so in the workflow chain A > B > C, workflow C will only receive secrets from A if they have been passed from A to B, and then from B to C." (`docs/content/actions/how-tos/reuse-automations/reuse-workflows.md`, the "Passing secrets to nested workflows" section.)

Every secret used in a job is redacted from that job's logs, whatever its value. That is the guarantee, and the next section is where it turns into a hazard.

### A composite action cannot read the secrets context

This is enforced, not advised. The contexts reference states: "The `secrets` context contains the names and values of secrets that are available to a workflow run. The `secrets` context is not available for composite actions due to security reasons. If you want to pass a secret to a composite action, you need to do it explicitly as an input." (`docs/content/actions/reference/workflows-and-actions/contexts.md:641`.)

The runner enforces it through the action manifest schema. `runner/src/Runner.Worker/action_yaml.json` gives every expression position inside a composite action the same context allowlist, and `secrets` is not in it. The definitions `step-with`, `step-env`, and `step-if` each permit `github`, `inputs`, `strategy`, `matrix`, `steps`, `job`, `runner`, `env`, and `hashFiles`. So does `string-steps-context`, which types the `run` body. A `${{ secrets.FOO }}` written into an `action.yml` is a template validation error rather than an empty string.

Two routes across the boundary exist, and both are ordinary. The first is an input, because a workflow step's `with:` block *may* read the `secrets` context — the workflow schema and the action schema differ here. The second is an environment variable set on the step that invokes the composite action. `runner/src/Runner.Worker/Handlers/CompositeActionHandler.cs:250-295` builds each embedded step's `env` context from the job's global environment variables, then merges the overrides recorded on the invoking step. So a secret placed in `env:` on the `uses:` step is visible to the composite action's `run:` steps as a process environment variable, without ever appearing in the action's declared inputs.

What a composite action cannot do is set an action-wide `env` block. `action_yaml.json`'s `composite-runs` definition permits only `using` and `steps`, and its `uses-step` definition permits only `name`, `id`, `if`, `uses`, `continue-on-error`, `with`, and `env`. Environment variables are per-step or they come from the caller.

### A private publishing repository restricts who can call it

The reusable workflow reference gives an accessibility table. A `private` caller can reach `private`, `internal`, and `public` workflow repositories. A `public` caller can reach only `public` ones. Two settings gate it beyond that. The caller's own **Actions permissions** policy must allow actions and reusable workflows at all. And for a private called repository, "the **Access** policy on the Actions settings page of the called workflow's repository must be explicitly configured to allow access from repositories containing caller workflows". (`docs/content/actions/reference/workflows-and-actions/reusing-workflow-configurations.md`, the "Access to reusable workflows" section.)

That Access setting has exactly two values, and its permissive one is narrower than its name suggests. For a repository owned by an organization the options are "**Not accessible** - Workflows in other repositories cannot access this repository" and "**Accessible from repositories in the 'ORGANIZATION NAME' organization** - Workflows in other repositories that are part of the 'ORGANIZATION NAME' organization can access the actions and reusable workflows in this repository. Access is allowed only from private repositories." The user-owned variant is the same with the account substituted. The section's opening sentence draws the boundary: "Actions and reusable workflows in your private repositories can be shared with other private repositories owned by the same user or organization." (`docs/content/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository.md:139-171`.)

So a private publishing repository serves private repositories inside one organization, and nothing else. The consequence for a public caller is not a permissions failure to debug — it is unreachable by design.

Sharing this way also widens who can read the publisher's code. The private-repository sharing guide states that "outside collaborators on the other repositories can indirectly access the private repository, even though they do not have direct access", because they "can view logs for workflow runs when actions or workflows from the private repository are used". It also describes the credential: GitHub "passes a scoped installation token to the runner" with read access to the repository, expiring after an hour. (`docs.github.com/actions/creating-actions/sharing-actions-and-workflows-from-your-private-repository`, read 2026-08-06.)

None of this changes when the publisher switches from a hardcoded reference to `$/`, because `$/` resolves into an ordinary remote reference and is fetched the same way.

### What the called workflow can and cannot carry

A called workflow is a whole workflow file, so it carries `permissions` and `concurrency` of its own. What it cannot do is grant itself more than the caller has. The reusable workflow reference is explicit on both halves: "If `jobs.<job_id>.permissions` is not specified in the calling job, the called workflow will have the default permissions for the `GITHUB_TOKEN`", and "The `GITHUB_TOKEN` permissions passed from the caller workflow can be only downgraded (not elevated) by the called workflow."

So the token the called workflow's jobs receive is the caller's job token, filtered by whatever the called workflow declares. A publisher that writes `pull-requests: write` on one of its jobs gets it only when the calling repository's default token already carries it. That default is a repository or organization setting, not something the publisher can see.

Concurrency is different, and the reference documents a specific way to get it wrong. "If you use `jobs.<job_id>.concurrency.cancel-in-progress: true`, don't use the same value for `jobs.<job_id>.concurrency.group` in the called and caller workflows as this will cause the workflow that's already running to be cancelled. A called workflow uses the name of its caller workflow in `${{ github.workflow }}`, so using this context as the value of `jobs.<job_id>.concurrency.group` in both caller and called workflows will cause the caller workflow to be cancelled when the called workflow runs."

Triggers cannot move, since the called workflow's `on:` block is `workflow_call` and nothing else.

Two further limits bound the shape. The chain is at most ten levels deep on github.com and four on Enterprise Server. A single workflow file may call at most 50 unique reusable workflows on github.com and 20 on Enterprise Server, counting nested trees. Runner assignment and billing are always evaluated from the caller's context, so a called workflow cannot bring its own hosted runners.

## Prior art

### Reusable workflows that publish an API-key-taking review job

Both repositories read here that ship an AI pull request reviewer as a `workflow_call` workflow declare their provider keys by name rather than inheriting, and both mark them `required: false` so one workflow can serve several providers.

- `code-review-action/.github/workflows/code-review.yml:139-148` — three declared secrets, `anthropic_api_key`, `openai_api_key`, and `gemini_api_key`, each `required: false` with a description naming which `provider` input needs it.
- `ai-code-review-workflows/.github/workflows/codex-review-reusable.yml:69-72` — one declared secret, `openai_api_key`, `required: false`.
- `ai-code-review-workflows/.github/workflows/codex-review-reusable.yml:85-86` — the key is put on the job's `env:` block as `OPENAI_API_KEY` rather than referenced at each step.

Neither uses `secrets: inherit`, and neither ships a composite action, so neither crosses the second boundary at all.

Both push `concurrency` upstream into the published workflow, keyed on the pull request number.

- `code-review-action/.github/workflows/code-review.yml:157-163` — group `ai-review-<number>-<trigger_mode>` with `cancel-in-progress: true`. The number is read as `github.event.issue.number || github.event.pull_request.number`, which works because the `github` context inside a called workflow is the caller's. The trigger mode is in the key so a pull request event and a comment event for the same pull request do not cancel each other.
- `ai-code-review-workflows/.github/workflows/codex-review-reusable.yml:74-76` — group `codex-review-<repository>-<pr_number>`, taking the number from a declared input rather than the payload.

They differ on permissions. `code-review-action/.github/workflows/code-review.yml:150` sets `permissions: {}` at workflow level and then re-grants per job, splitting the run so that the job running the model holds no write scope and a separate job does the posting. Its README's quickstart, at `code-review-action/README.md:24-46`, shows a caller file with no `permissions:` block at all, so the split depends on the calling repository's default token already carrying `pull-requests: write`. `ai-code-review-workflows/README.md:31-47` instead shows the caller granting `contents: read` and `pull-requests: write` on the calling job.

They also differ on who resolves the pull request. `ai-code-review-workflows` requires the caller to pass seven facts as inputs — `pr_number`, `base_ref`, `head_ref`, `base_sha`, `head_sha`, `author_association`, and `is_draft` — so the caller's file reads the event payload and the published workflow reads none of it. `code-review-action` resolves the same facts in its own first job.

### Reaching your own repository, four ways

The hardcoded full reference is still the most common thing in shipped code, and it appears alongside every other approach rather than instead of them.

- `harisekhon-actions/.github/workflows/docker_build_aws_ecr.yaml:169` — a `workflow_call` workflow referencing `HariSekhon/GitHub-Actions/generate-docker-tags@master`. This is the repository whose author opened the community discussion about the problem in 2022; the workaround GitHub offered in 2023 was never adopted here, and the reference is pinned to a branch.
- `slsa-github-generator/.github/workflows/builder_go_slsa3.yml:133,145,160,194` — four references to `slsa-framework/slsa-github-generator/.github/actions/...@main`, all on a branch, in a workflow whose whole purpose is build provenance.

Discovering the workflow's own identity at run time, then checking that repository out, is what `slsa-github-generator` does for everything past those four steps.

- `slsa-github-generator/.github/actions/detect-workflow-js/src/detect.ts:34-61` — `detectWorkflowFromOIDC` requests an OIDC token, base64-decodes its payload, and reads the `job_workflow_ref` claim, splitting on the first `@` because a release tag may itself contain one. That claim names the reusable workflow's own repository, path, and ref.
- `slsa-github-generator/.github/workflows/builder_go_slsa3.yml:135-145` — the job that runs it declares `permissions: id-token: write`, with the comment "Needed to detect the current reusable repository and ref". The caller has to have granted that scope.
- `slsa-github-generator/.github/actions/detect-workflow-js/src/detect.ts:63-134` — the fallback, `detectWorkflowFromContext`, asks the API for the current workflow run and scans its `referenced_workflows`. It filters that list by the literal string `slsa-github-generator`, and rejects any entry with no `ref`, whose error message reads "Referenced slsa-github-generator workflow missing ref: was the workflow invoked by digest?".
- `slsa-github-generator/.github/actions/secure-builder-checkout/action.yaml` — a composite action taking `repository`, `ref`, `path`, and `token`, wrapping one pinned `actions/checkout` with `persist-credentials: false`.
- `slsa-github-generator/.github/workflows/builder_go_slsa3.yml:194-213` — the sequence. The builder repository is checked out into the workspace at the literal path `__BUILDER_CHECKOUT_DIR__`, and every subsequent step uses `./__BUILDER_CHECKOUT_DIR__/.github/actions/...`. The odd directory name is not a template placeholder; it is the directory name, chosen so it cannot collide with anything in the repository being built.

`code-review-action` reaches the same place with no JavaScript and no OIDC scope, using the documented `job` context.

- `code-review-action/.github/workflows/code-review.yml:394-406` — one `actions/checkout` with `repository: ${{ job.workflow_repository }}` and `ref: ${{ job.workflow_sha }}`, into `path: _action`, with `persist-credentials: false` and `fetch-depth: 1`. The step comment states the rule it relies on: "Reusable workflows only auto-checkout the caller repo, never their own. job.workflow_repository/job.workflow_sha resolve to *this* file's own repo+commit (not the caller's) even when called cross-repo, so this is guaranteed to match the exact ref the caller pinned in 'uses:'".
- `code-review-action/.github/workflows/code-review.yml:408-416` — what it buys. Two scripts are copied out of the checkout into an artifact directory so that later jobs, which never see this checkout, run the same secret-scanning and guideline-discovery code as this one. The alternative the comment names is inlining them, duplicated.

The self repository reference is the newest approach and the two adopters both moved within the last week.

- `github-docs-build/.github/workflows/_shared-docs-build-pr.yml:312,336,361,385,395` — a `workflow_call` workflow referencing five composite actions in its own repository as `$/actions/ansible-docs-build-init` and siblings. Adopted in commit `0442e4e`, dated 2026-08-01, titled "Pin actions, and use new GHA syntax to reference own shared workflows and actions".
- `actions/post-build/action.yml:31,39,48` — a composite action referencing a sibling composite action in the same repository as `$/failures-summary-and-bottle-result`. Commit `8b335f2`, dated 2026-08-05, replaced `Homebrew/actions/failures-summary-and-bottle-result@fd832223f9f99ebf0244dd20658680e5d4aca049 # 2026.08.03.2` at each of these lines. This is the composite-inside-composite case, which is where the old workaround cost the most: the pinned SHA had to be bumped in every sibling file on every release.
- `actions/post-build/action.yml:25-27` — the same action reaches a shell script in its own repository as `"$GITHUB_ACTION_PATH/../deprecate-master.sh"`. That worked before `$/` existed and still does, because the action's own directory is on disk. It has never worked for a `uses:` reference.

## How the field splits

### Approach A — hardcode the full owner, repository, path, and ref

- **What it is:** every reference inside the reusable workflow is written out as `owner/repo/path@ref`, with the ref a branch name or a tag.
- **Exemplified by:** `harisekhon-actions/.github/workflows/docker_build_aws_ecr.yaml:169`, `slsa-github-generator/.github/workflows/builder_go_slsa3.yml:133`.
- **Tradeoffs its authors accepted:** nothing to build and nothing to check out. The reference is legible and greppable.
- **Failure mode:** the ref inside the workflow is fixed at authoring time and has no relationship to the ref the caller pinned. A caller pinning `@v1.2.0` runs the version 1.2.0 workflow and, if the internal references say `@main`, actions from whatever `main` holds right now. A fork is worse than stale: the fork's copy of the workflow still fetches the upstream's actions, so a fork cannot be tested against its own changes. Bumping a release means editing every reference in every file.

### Approach B — accept the repository and ref as workflow inputs

- **What it is:** the reusable workflow declares inputs such as `actions-repo` and `actions-ref`, defaults them to itself, and builds its references from them so a fork can override.
- **Exemplified by:** nothing read here. It is the workaround GitHub staff posted in community discussion 18601 on 2023-02-07, and the author who raised the problem did not adopt it (`harisekhon-actions/.github/workflows/docker_build_aws_ecr.yaml:169` still hardcodes).
- **Tradeoffs its authors accepted:** forks work, at the price of two more inputs on every published workflow.
- **Failure mode:** the version now lives in an input rather than in a `uses:` line, so dependency automation cannot see it. A commenter on that thread in September 2023 reported exactly this, that Dependabot "won't bump your inputs when bumping an action", leaving the workflow ref and the action ref to drift apart until somebody notices by hand.

### Approach C — discover the workflow's own identity at run time, then check it out

- **What it is:** an action reads the run's OIDC token, or the run's `referenced_workflows` list, to learn which repository and ref the currently executing reusable workflow came from. It checks that out into a known directory in the workspace, and every later step uses a `./` path into it.
- **Exemplified by:** `slsa-github-generator/.github/actions/detect-workflow-js/src/detect.ts:34-61` with `slsa-github-generator/.github/workflows/builder_go_slsa3.yml:194-213`.
- **Tradeoffs its authors accepted:** the actions the workflow runs come from the same commit the caller pinned, including in forks, without any hardcoded name. The bootstrap steps still need Approach A, so the first few references stay hardcoded on a branch.
- **Failure mode:** the OIDC path needs `id-token: write`, a scope the caller has to grant and one no reviewer expects a code review job to want. The API fallback needs a hardcoded repository name to filter `referenced_workflows` by, which is the fork problem coming back in through the fallback, and it fails outright when the caller pins by digest, because the API then reports no ref. The whole mechanism is a JavaScript action with a `dist/` bundle to build, review, and keep current.

### Approach D — the self repository reference

- **What it is:** every internal reference is `$/path/to/action`. The platform resolves it to the publishing repository at the commit currently running, before any download.
- **Exemplified by:** `github-docs-build/.github/workflows/_shared-docs-build-pr.yml:312`, `actions/post-build/action.yml:31`.
- **Tradeoffs its authors accepted:** no checkout, no bootstrap references, no inputs, no `dist/` bundle, and the caller's pin propagates automatically to every internal reference including composite actions nested inside composite actions. In exchange the publisher depends on a syntax that reached general availability on 2026-07-30.
- **Observed working on a GitHub-hosted `ubuntu-latest` runner, 2026-08-06.** A `workflow_call` workflow in `kkestell/coral`, called cross-repository from `kkestell/coral-test` with `@main`, referenced three sibling composite actions as `$/actions/<name>`. Each resolved to `kkestell/coral/actions/<name>@<sha>`, where the SHA is the commit the called workflow file is running from, and the resolved form is what the run's step names report.
- **Failure mode:** it does not exist on GitHub Enterprise Server, and neither do the `job.workflow_*` properties it is built on, so a publisher who needs to serve Enterprise Server needs a second answer anyway. Self-hosted runners below version 2.336.0 cannot resolve it; `runner/src/Test/L0/Worker/ActionManagerL0.cs:3614` is the test for the disabled case, and `runner/src/Runner.Worker/ActionManager.cs:711` is the exception it throws. The resolution is invisible in the file, so reading `$/foo` tells you nothing about which commit runs, only that it matches this file's.

### Approach E — publish no composite actions at all

- **What it is:** the reusable workflow's steps are `run:` blocks and references to third-party actions. There is no `action.yml` in the repository, so the relative-path question never arises.
- **Exemplified by:** `code-review-action/.github/workflows/code-review.yml` and `ai-code-review-workflows/.github/workflows/codex-review-reusable.yml`, neither of which contains an `action.yml` anywhere.
- **Tradeoffs its authors accepted:** one file to read and one boundary to reason about, and the `secrets` context is available at every step because nothing is a composite action.
- **Failure mode:** logic that several jobs need has nowhere to live. `code-review-action` hit this and did not escape it — it added Approach C purely so two scripts could be required rather than duplicated, and `code-review-action/.github/workflows/code-review.yml:408-416` copies them into an artifact so the later jobs get them too. The file is 1,263 lines.

## Cautionary findings

**A low-entropy secret corrupts the values around it.** Redaction is unconditional and matches on the value, so a secret whose value is a common string gets replaced wherever that string appears. `slsa-github-generator/internal/builders/container/README.md:225` documents the result for a registry username offered both as an input and as a secret: "This should only be used for high entropy values such as AWS Access Key... Normal username values could match other input values and cause them to be ignored by GitHub Actions and causing your build to fail. In those cases, use the `registry-username` input instead." The workflow declares both spellings and the README tells callers which to choose (`slsa-github-generator/.github/workflows/generator_container_slsa3.yml:30-45`). An API key is high-entropy and safe here. A model name, an account identifier, or a base URL passed as a secret is not.

**A `./` reference inside a reusable workflow does not fail safely in every case.** It resolves against the workspace, and the workspace usually holds the repository under review. The common outcome is a missing `action.yml` and a clear error. The outcome when the path happens to exist in the caller's tree is that the caller's file runs instead, with the publisher's inputs. Nothing in the runner distinguishes the two: `runner/src/Runner.Worker/ActionManager.cs:701-705` joins the workspace path to the reference and loads whatever manifest is there. This is why the documentation reduced `./` to "Edge cases only" rather than merely discouraging it.

**The `github` context inside a published workflow describes somebody else's repository.** "When a reusable workflow is triggered by a caller workflow, the `github` context is always associated with the caller workflow." Every intuition built on `github.repository` and `github.sha` inverts here, and the failure is silent because both properties are populated with plausible values. The distinction is load-bearing in both directions: `code-review-action/.github/workflows/code-review.yml:157-163` relies on the caller's payload being in `github.event` to key concurrency on the pull request number, and `code-review-action/.github/workflows/code-review.yml:402-403` relies on `job.workflow_repository` and `job.workflow_sha` for the one thing `github` cannot supply.

**Branch-pinned internal references undercut the pin the caller was told to use.** `slsa-github-generator` exists to produce build provenance, and its Go builder workflow fetches four of its own actions from `@main` (`slsa-github-generator/.github/workflows/builder_go_slsa3.yml:133,145,160,194`). A caller pinning the workflow to a release tag still runs whatever those four actions contain today. The elaborate run-time detection in Approach C exists to fix this for the steps after the bootstrap, and it cannot fix the bootstrap itself.

**A published workflow's own `permissions` block is a filter, not a grant.** `code-review-action` sets `permissions: {}` at workflow level and grants each job the minimum it needs, and its quickstart shows a caller with no `permissions:` block. That design holds only when the calling repository's default token carries `pull-requests: write`. Where the default is read-only, the posting job's declared `pull-requests: write` is downgraded to read and the run fails at the end, after the model has already been paid for. Nothing in the published workflow can detect the condition in advance.

## Open threads

Whether a caller repository running the "Allow select actions and reusable workflows" policy must list the publisher's composite actions separately from its reusable workflow. The policy documentation says that under that setting "local actions (`./` and `$/`)... are allowed", but does not say whether the check is on the reference's syntax or on the repository it resolves to. A `$/` reference inside a third-party reusable workflow is local by syntax and third-party by target. Nothing read here settles it, and the answer decides whether a restrictive caller needs one allow-list entry or several.

What GitHub's Actions service sends for `job.workflow_repository` when a reusable workflow is called by digest rather than by tag. The runner reads the property and trusts it (`runner/src/Runner.Worker/ActionManager.cs:198-199`), and the population happens server-side, where there is no source to read. `slsa-github-generator` documents that the older `referenced_workflows` API reports no ref in that case (`slsa-github-generator/.github/actions/detect-workflow-js/src/detect.ts:110-116`), which is reason to check rather than assume the newer property is complete.

Whether a composite action invoked from a reusable workflow can receive a secret through `env:` on its `uses:` step in practice, not only in the runner's context merging. `runner/src/Runner.Worker/Handlers/CompositeActionHandler.cs:250-295` shows the merge, and the workflow schema permits `secrets` in a step's `env:`. No repository read here does this, so there is no worked example and no report of how it interacts with redaction inside the action's own logs.

The `openrouter` and `langchain-openrouter` packaging story was not touched. This topic is about the workflow boundary and stops at the point where a key is an environment variable.

GitHub Enterprise Server was surveyed only through the documentation's version conditionals. Every count and every availability note quoted here for Enterprise Server came from those conditionals rather than from a running instance.

`github/codeql-action` was again not read. It publishes several step actions over one library and remains the largest worked example of the cross-step protocol, but it publishes no `workflow_call` workflow, so it does not speak to this topic.

## Sources

- `runner` — https://github.com/actions/runner at `2009b20729fdf49c50a88e0ca368906c16a3129c`, whose `src/runnerversion` reads `2.336.0`
- `slsa-github-generator` — https://github.com/slsa-framework/slsa-github-generator at `4d014fae4dbd39eb09e8d40348b73db095e6ba9a`
- `code-review-action` — https://github.com/DataDog/code-review-action at `2c558ddeddb86069cd6c49793a6bd61c4dbeb71f`
- `ai-code-review-workflows` — https://github.com/liatrio-labs/ai-code-review-workflows at `7e471a8dd8ef992df21612208795893e5e3eaed8`
- `github-docs-build` — https://github.com/ansible-community/github-docs-build at `0442e4ef1e1f2ac6169f4c8f74cf8c1aa905e91b`
- `actions` — https://github.com/Homebrew/actions at `d3565f64e59130f1fd713440276f7d3e11079b88`
- `harisekhon-actions` — https://github.com/HariSekhon/GitHub-Actions at `fb055c2b4aa67596c29b863e53158c00c0e3e4e9`
- `docs` — https://github.com/github/docs at `738593aef7b8d80183a376d5c692feefc0e8a5ff`, the source of the rendered GitHub Actions documentation. Files cited: `content/actions/reference/workflows-and-actions/workflow-syntax.md`, `content/actions/reference/workflows-and-actions/metadata-syntax.md`, `content/actions/reference/workflows-and-actions/contexts.md`, `content/actions/reference/workflows-and-actions/reusing-workflow-configurations.md`, `content/actions/how-tos/reuse-automations/reuse-workflows.md`, `content/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository.md`, `data/reusables/actions/reusable-workflow-calling-syntax.md`, `data/reusables/actions/pass-inputs-to-reusable-workflows.md`, `data/reusables/actions/allow-specific-actions-intro.md`, `data/reusables/actions/secrets-redaction-warning.md`
- "Sharing actions and workflows from your private repository" — https://docs.github.com/actions/creating-actions/sharing-actions-and-workflows-from-your-private-repository, read 2026-08-06
- "Reference same-repository actions with self-repository syntax" — https://github.blog/changelog/2026-07-30-reference-same-repository-actions-with-self-repository-syntax/, dated 2026-07-30, the general availability announcement for `$/`
- "GitHub Actions: Simplify using secrets with reusable workflows" — https://github.blog/changelog/2022-05-03-github-actions-simplify-using-secrets-with-reusable-workflows/, dated 2022-05-03, the introduction of `secrets: inherit`
- "Accessing Composite Action within Reusable Workflow from called workflow repo" — https://github.com/orgs/community/discussions/18601, opened 2022-06-14, with the GitHub staff workaround dated 2023-02-07 and the Dependabot objection dated 2023-09-04
- "Path to action in the same repository as workflow" — https://github.com/orgs/community/discussions/26245, where the `$/` syntax was proposed on 2026-01-26 and its general availability announced on 2026-07-30
