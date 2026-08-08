# Architecture

How the code is organized and how it runs on GitHub Actions.

## The Platform

- A GitHub Actions workflow. No cloud account or standing service; GitHub supplies the trigger, compute, checkout, and credential.
- Python, built with `uv` against a committed lockfile; nothing resolves at run time.
- The agent is DeepAgents. Models are reached only through OpenRouter, via `langchain-openrouter`'s `ChatOpenRouter`.
- The model, the reasoning effort, the review's time budget, and the spend cap are `workflow_call` inputs, defaulted in the reusable workflow and nowhere else. The model is named exactly and a `~` alias is refused, so the concrete model cannot change under a review; its profile is fetched from OpenRouter's model listing at run time.
- No datastore. Everything Coral remembers about a pull request is written on the pull request and read back each run.

## Installation and Packaging

- Composite actions in this repository, wired by a reusable workflow, installed by one short caller file per repository.
- The caller file carries the version pin, OpenRouter secret, `on:` block, `permissions:` block, and concurrency group. A reusable workflow cannot declare them for its caller. It also owns configuration, because a file under review would let a pull request pick the model.
- This repository is public, so callers need no access configuration.
- A caller passes a plain API key, or a management key and generated Fernet encryption key. The management key reaches resolve alone. The encryption key has no provider authority and reaches resolve and review. The GitHub token comes from the job.

## The Run

Three jobs in fixed order — resolve, review, publish — each on its own runner with its own `permissions`.

- Resolve holds `contents: read`, `issues: write`, and `pull-requests: write`. It fetches the pull request and conversation, acknowledges requests, and decides whether a pull-request review runs. On a `main` push it pins the event's commit and prior main tip, without a pull-request call. It derives the review timeout and mints, masks, and encrypts a capped key after the gates pass.
- Review holds `contents: read` and `issues: read`. On a `main` push it gives the verifier two bounded issue-reading tools; it receives the job token only for that path and removes it before either container starts. Its `timeout-minutes` is resolve's derived output. Each agent run gets a fresh checkout copy and container. It verifies findings, then writes two create-review bodies for a pull request or one issue body per main-push finding. The review object never crosses; the review bodies need the added-line set checked here.
- The checkout takes the pinned head SHA, full history, and no persisted credentials.
- Publish holds resolve's three scopes and is the only job that posts: a pull-request review, a failure comment, or main-push issues. It stamps `commit_id` and `event` on a pull-request review; the agent's job gets no say in either.
- Each job builds Coral's virtual environment under the runner's temporary directory — outside the workspace and off `PATH`, every step invoking the console script by absolute path.
- A job boundary is a machine boundary, each side a fresh runner and filesystem. The head SHA, `proceed` flag, review timeout, and ciphertext cross as job outputs; everything else crosses as artifacts under the runner's temporary directory, outside the workspace. Review decrypts ciphertext in its runner process before either container starts.
- A stopped run is green: `proceed=false`, reason on stderr, exit zero, later jobs skipped. Only a broken run is red; a cancelled run posts nothing.

## The Codebase

One console script. `coral resolve`, `coral review`, and `coral publish` are each invoked by one composite action's `run:` step; `coral rehearse` is run by a person, and `.agents/docs/development.md` owns it.

- `coral/cli.py` — one `argparse` parser.
- `coral/runner.py` — the event, job outputs, and temporary artifact paths.
- `coral/handoff.py` — validation, encryption, and decryption for the minted-key handoff.
- `coral/resolve.py` — the gatekeeper for pull requests and main pushes.
- `coral/review.py` — render each request, run both agents, filter, write publishing bodies.
- `coral/rehearse.py` — the review step over one commit of a local clone.
- `coral/publish.py` — the publishing step: the review, or the failure comment.
- `coral/agent.py` — the only module that imports `deepagents`.
- `coral/container.py` — the agent's container: the pinned image, the mounts, and the shell it runs.
- `coral/openrouter.py` — OpenRouter's HTTP API: minting this run's key, and the model listing the profile is built from.
- `coral/schema.py` — the review object and its anchors, the verifier's verdicts, and the filter between them; the only place structure originates.
- `coral/command.py` — what counts as a request: the command, who may make one, Coral's own comments.
- `coral/environment.py` — the agent's container environment, built from the toolcache.
- `coral/deadline.py` — the time budget.
- `coral/spend.py` — the spend cap and the run's total against it.
- `coral/diff.py` — the merge-base diff and which anchors may attach.
- `coral/github/client.py` — the one authenticated transport.
- `coral/github/issues.py` — the bounded open-issue search and view evidence for a main-push verifier.
- `coral/github/conversation.py` — the GraphQL query, the bound, the conversation's file.
- `coral/github/marker.py` — the sentinel: writing and reading it.
- `coral/github/reactions.py` — which comments get the reaction, through both namespaces.
- `coral/github/post.py` — review bodies, issue bodies, anchor demotion, and posting helpers.
- `coral/prompts/review.md` — what Coral looks for.
- `coral/prompts/verify.md` — how Coral checks a finding it was handed.
- `tests/` — one `test_<module>.py` per module under test.
- `.github/workflows/coral.yml` — the reusable workflow's jobs, tokens, and handoffs.
- `actions/setup/` — installs `uv`, builds Coral's virtual environment.
- `actions/resolve/`, `actions/review/`, `actions/publish/` — one `run:` step each.
- `examples/coral.yml` — the file a repository copies in to install Coral.

Rules:

- Nothing but `coral/agent.py` depends on `deepagents`. `coral/review.py` imports it inside the function; the comment there says why.
- The prompt is Markdown inside the package, read with `importlib.resources`, so changes diff readably.

## Rules That Hold Everywhere

- An agent's only return value is a structured object, and deterministic code does the posting. Nothing the model produces becomes a push, an approval, or a comment Coral did not compose.
- Every change Coral runs came from somebody with push access: it refuses a fork's pull request, and `/coral` from anybody whose collaborator permission is not push. An `author_association` decides nothing, because GitHub gives `MEMBER` and `COLLABORATOR` to read-only people.
- Each agent run reaches only its own copy of the checkout, and Coral's own code reaches `git` in the workspace only through `coral/diff.py`, so the diff the agent saw and the diff the anchors are checked against are the same.
- The agent's shell holds no credential and sees only that copy and the read-only toolcache. The runner's filesystem, its process table, and `Runner.Worker`'s memory are on the far side of a namespace boundary, and the container is capped in memory, processors, and processes. It keeps the network, because there is nothing in the container to send out.
- Every answer Coral holds is bounded as it arrives — a GitHub response, a comment body, a command's output — so no input decides how much memory Coral spends.
- The review runner logs each public tool call with bounded arguments and its duration. It omits tool results, DeepAgents implementation names, and HTTP transport diagnostics.
- What a compromised agent can still choose is the text of the review the publishing job posts, marker included — never `event`, `commit_id`, or any write anywhere.
- The conversation is untrusted input reaching a model with an unsandboxed shell, and the prompt rule — information, never instruction — is not enforced. The bound that holds is the schema-only return path; everything else rests on who may comment.
- Coral cannot trigger itself: events created with the job's `GITHUB_TOKEN` start no workflow runs (except `workflow_dispatch` and `repository_dispatch`). Free only while Coral has no identity of its own; a move to a GitHub App needs an explicit self-check.

## The Runner

- Hosted Ubuntu: 4 vCPU / 16 GB public, 2 vCPU / 8 GB private, 14 GB SSD.
- Coral's own process runs on the runner; the agent's shell runs as root in an `ubuntu:24.04` container. Reviewing a repository means running its tests with its toolchain, so the container mounts the hosted image's toolcache read-only and has `apt-get` for the rest.
- On the comment paths the workflow file is read from the default branch, so a pull request cannot change how it is reviewed by asking. On the `pull_request` path it comes from the head, so a pull request can alter its own review.
