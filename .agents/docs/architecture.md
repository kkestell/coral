# Architecture

How the code is organized and how it runs on GitHub Actions.

## The Platform

- A GitHub Actions workflow. No cloud account, no standing service; GitHub supplies the trigger, compute, checkout, and credential.
- Python, built with `uv`. Dependencies install with `uv sync --frozen` against the committed lockfile; nothing resolves at run time.
- The agent is DeepAgents. Models are reached only through OpenRouter, via `langchain-openrouter`'s `ChatOpenRouter`.
- The model, the reasoning effort, the review's time budget, and the spend cap are `workflow_call` inputs, defaulted in the reusable workflow and nowhere else. The model is named exactly and a `~` alias is refused, so the concrete model cannot change under a review; its profile is fetched from OpenRouter's model listing at run time.
- No datastore. Everything Coral remembers about a pull request is written on the pull request and read back each run.

## Installation and Packaging

- Composite actions in this repository, wired by a reusable workflow, installed by one short caller file per repository.
- The caller file must carry all five of: version pin, OpenRouter secret, `on:` block, `permissions:` block, concurrency group. A reusable workflow cannot declare its caller's triggers or grant itself withheld permissions. Any configuration goes there too, and only there: a file in the repository under review would let a pull request pick the model that reviews it.
- This repository is public, so callers need no access configuration.
- One OpenRouter secret, exactly one of two kinds: a plain API key, used as it is, or a management key Coral mints one capped, expiring API key per run with. The GitHub token comes from the job.

## The Run

Three jobs in fixed order — resolve, review, publish — each on its own runner with its own `permissions`.

- Resolve holds `contents: read`, `issues: write`, and `pull-requests: write`. The gatekeeper: it fetches the pull request and the conversation, acknowledges requests, and decides whether a review runs. Both commits are pinned here and never re-read. It validates the time budget before the fetch and derives the review job's `timeout-minutes` from it, because Actions expressions have no arithmetic. It is also the only job the management key reaches, minting once the gates pass, at the caller's spend cap, and handing the key on as a job output the review job masks on receipt. That crossing costs one cleartext log line, readable by whoever can already read the repository's logs.
- Review runs the agent and holds `contents: read` — what the checkout needs and nothing more; its review step makes no API call and its environment carries no token. Its `timeout-minutes` is resolve's derived output. Each agent run gets a fresh copy of the checkout and a container of its own, so no agent writes the workspace. It verifies the reviewer's findings with a second run and writes the two finished create-review bodies: the anchored one and the one with every finding demoted. The review object never crosses: both bodies need the added-line set the anchors were checked against, which exists only here.
- The checkout takes the pinned head SHA, full history, and no persisted credentials; the workflow file says why. A force-pushed SHA can make it fail; the publishing job covers that.
- Publish holds resolve's three scopes and is the only job that posts: the review, or the failure comment — including for a review job that died whole and crossed no reason file. It stamps `commit_id` and `event` on whichever body it posts; the agent's job gets no say in either.
- Each job installs `uv` and builds Coral's virtual environment under the runner's temporary directory — outside the workspace, never activated, never on `PATH`, every step invoking the console script by absolute path. - A job boundary is a machine boundary, each side a fresh runner and filesystem. The head SHA, the `proceed` flag, the review job's timeout, and the minted key cross as job outputs — the values YAML reads; everything else crosses as artifacts under the runner's temporary directory, outside the workspace.
- A stopped run is green: `proceed=false`, reason on stderr, exit zero, later jobs skipped. Only a broken run is red. A cancelled run posts nothing.

## The Codebase

One console script, three subcommands — `coral resolve`, `coral review`, `coral publish` — each invoked by one composite action's `run:` step.

- `coral/cli.py` — one `argparse` parser, three subcommands.
- `coral/runner.py` — the event, step outputs, the temporary directory whose files cross jobs as artifacts, the one reading of `GITHUB_WORKSPACE`.
- `coral/resolve.py` — the gatekeeper: fetch the pull request and conversation, acknowledge requests, apply the gates.
- `coral/review.py` — render each request, run both agents, filter, write the bodies that cross to publish.
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
- `coral/github/conversation.py` — the GraphQL query, the bound, the conversation's file.
- `coral/github/marker.py` — the sentinel: writing and reading it.
- `coral/github/reactions.py` — which comments get the reaction, through both namespaces.
- `coral/github/post.py` — the two create-review bodies that cross to publish, anchor demotion, the retry on rejection, the plain comment.
- `coral/prompts/review.md` — what Coral looks for.
- `coral/prompts/verify.md` — how Coral checks a finding it was handed.
- `tests/` — one `test_<module>.py` per module under test.
- `.github/workflows/coral.yml` — the `workflow_call` workflow: the three jobs, their tokens, and what crosses between them.
- `actions/setup/` — installs `uv`, builds Coral's virtual environment.
- `actions/resolve/`, `actions/review/`, `actions/publish/` — one `run:` step each.
- `examples/coral.yml` — the file a repository copies in to install Coral.

Rules:

- Nothing but `coral/agent.py` depends on `deepagents`. `coral/review.py` imports it inside the function; the comment there says why.
- The prompt is Markdown inside the package, read with `importlib.resources`, so changes diff readably.

## Rules That Hold Everywhere

- An agent's only return value is a structured object, and deterministic code does the posting. Nothing the model produces becomes a push, an approval, or a comment Coral did not compose.
- Coral is installed only on private repositories whose read, write, and admin access is controlled. Everybody who can open a pull request, comment, or submit a review is already trusted to run code in that repository's CI. A public repository, or one taking pull requests from outside, needs every bullet here rewritten first.
- Each agent run reaches only its own copy of the checkout, and Coral's own code reaches `git` in the workspace only through `coral/diff.py`, so the diff the agent saw and the diff the anchors are checked against are the same.
- The agent's shell holds no credential and sees only that copy and the read-only toolcache. The runner's filesystem, its process table, and `Runner.Worker`'s memory are on the far side of a namespace boundary. It keeps the network, because there is nothing in the container to send out.
- What a compromised agent can still choose is the text of the review the publishing job posts, marker included — never `event`, `commit_id`, or any write anywhere.
- The conversation is untrusted input reaching a model with an unsandboxed shell, and the prompt rule — information, never instruction — is not enforced. The bound that holds is the schema-only return path; everything else rests on who may comment.
- Coral cannot trigger itself: events created with the job's `GITHUB_TOKEN` start no workflow runs (except `workflow_dispatch` and `repository_dispatch`). Free only while Coral has no identity of its own; a move to a GitHub App needs an explicit self-check.

## The Runner

- Hosted Ubuntu: 4 vCPU / 16 GB public, 2 vCPU / 8 GB private, 14 GB SSD. Larger runners need Team or Enterprise Cloud.
- Coral's own process runs on the runner; the agent's shell runs as root in an `ubuntu:24.04` container. Reviewing a repository means running its tests with its toolchain, and the container answers that with the hosted image's toolcache mounted read-only plus `apt-get` for the rest.
- On the comment paths the workflow file is read from the default branch, so a pull request cannot change how it is reviewed by asking. On the `pull_request` path it comes from the head, so a pull request can alter its own review.
