# Architecture

THIS FILE MUST BE KEPT UP TO DATE AT ALL TIMES

What this project is built out of, where each part lives, and how the parts fit together. Read this before planning a change, so the change lands where the code already expects it to.

## Tech Stack

- **Language(s):** Python 3.14 — pinned in `.python-version`, which is what `uv` builds against, and again as `requires-python` in `pyproject.toml`, which is what makes an install on an older interpreter fail outright
- **Frameworks:** DeepAgents
- **Build system:** `uv`, against a committed lockfile
- **Datastores:** None. Coral owns no state. What Coral has said about a pull request lives on the pull request, and Coral reads it back from GitHub at the start of every run.
- **Model provider:** OpenRouter — `~deepseek/deepseek-v4-flash-latest`
- **Deployment target:** GitHub Actions. There is no cloud account and nothing to provision. Coral ships as composite actions wired together by a reusable workflow, and a repository installs it by adding one file that calls that workflow. That file carries a version pin, an OpenRouter key, the event triggers, the token permissions, and the concurrency group — the last three because a reusable workflow cannot declare any of them for its caller.

## Codebase Map

This is the whole layout, and every part of it that does not exist yet is marked.

- `coral/cli.py` — the console script. One `argparse` parser, three subcommands, and nothing else.
- `coral/runner.py` — what every subcommand needs from the Actions runner: the event, step outputs, the temporary directory, and the one reading of `GITHUB_WORKSPACE`.
- `coral/resolve.py` — the gatekeeper step. The only gate it applies so far is the closed pull request.
- `coral/review.py` — the review step: build the agent, run it, post the result. The review is hardcoded until the agent exists.
- `coral/report.py` — the failure step, which runs on the job's failure path. Not built.
- `coral/agent.py` — the only module that imports `deepagents`. Not built.
- `coral/schema.py` — the review object and its anchors: the contract with the agent, and the only place structure originates.
- `coral/command.py` — recognizing `/coral` in a comment body. Not built.
- `coral/environment.py` — building the environment the agent's shell gets. Not built.
- `coral/deadline.py` — the four parts of the time budget. Not built.
- `coral/diff.py` — the merge-base diff. Anchor validation is not built.
- `coral/github/client.py` — the one authenticated transport.
- `coral/github/conversation.py` — the GraphQL query and its bounds. Not built.
- `coral/github/marker.py` — the sentinel: writing it and reading it back.
- `coral/github/reactions.py` — the two reaction namespaces.
- `coral/github/post.py` — creating the review and demoting anchors. The retry on a rejection is not built.
- `coral/prompts/review.md` — what Coral looks for. Not built.
- `tests/` — one `test_<module>.py` per module under test.
- `.github/workflows/coral.yml` — the `workflow_call` workflow.
- `actions/setup/` — installs `uv` and builds Coral's own virtual environment.
- `actions/resolve/` and `actions/review/` — one `run:` step each, invoking the console script.
- `examples/coral.yml` — the file a repository copies in to install Coral.

## How It Fits Together

A pull request is opened or marked ready for review, or somebody leaves a comment, and GitHub starts a workflow run. Before a runner is allocated, a job-level condition throws out what is certainly not a trigger. That condition is coarse by necessity, because Actions expressions have no regular expressions and no way to work line by line: on a comment it can check that the body mentions the command at all, that it sits on a pull request rather than an issue, and that the author association passes. Deciding whether the command really stands alone on its own line, unquoted and outside a code fence, needs a real parse and happens in the first step of the run. So a comment merely discussing Coral does allocate a runner, and then stops within seconds.

Two properties of the platform do work here that Coral would otherwise have to do itself. Events created with the job's own token start no workflow runs, so Coral cannot trigger itself no matter what its findings say — a property that would stop being free the day Coral is given an identity of its own. And a concurrency group keyed on the pull request number means a run already going finishes undisturbed while a newly queued run replaces whichever run was waiting, which is the whole of "never two at once, and several requests collapse into one".

The run itself is five steps: set up, resolve, check out, review, and report. The middle three carry the work, and the split between resolve and the checkout exists for one reason — the checkout needs a commit SHA that only an API call can supply. The report step runs only when something failed.

The setup step builds Coral's own virtual environment, once, under the runner's temporary directory, and publishes the directory holding the console script. It is a step of its own because resolve runs before the checkout and review runs after it, so both need that environment and neither can build it. Nothing ever activates that environment or puts it on `PATH`; every step invokes the console script by absolute path.

The resolve step is the gatekeeper. It fetches the pull request and pins two commits: the head SHA, which is the subject of the review, and the base branch's current SHA. Pinning both is what stops the reviewed diff shifting when either branch moves during the run. It stops the run if the command turns out to be inert, if the pull request is closed, if the change is larger than Coral will read, or if the head lives in a fork — that last check is a security control rather than a scope statement, because a comment event fires in the base repository and would otherwise run the base repository's secrets against a branch nobody vouched for.

Stopping the run is not failing it. The resolve step writes a `proceed` flag as a step output, prints its reason, and exits zero, and the checkout and review steps are conditioned on that flag. A pull request Coral declined to review therefore leaves a green run with two skipped steps. Only a run that broke ends red.

It then fetches the conversation over GraphQL, because deciding whether a past finding still stands means reading each thread's resolved and outdated state, and REST exposes neither. The conversation does double duty: it is the agent's context, and because every review Coral posts opens with an invisible marker carrying the reviewed commit SHA, it is also the record of which commits Coral has already reviewed. That is the whole of Coral's memory and the reason there is no database. It is written to the runner's temporary directory, outside the workspace, so the checkout cannot disturb it. Finally the step leaves the reaction, which is the only acknowledgment a comment-triggered run can give, since such a run does not show up among the pull request's checks. It reacts to every unacknowledged request it finds in the conversation rather than only to the one that started this run, because the concurrency collapse means other people's requests may have had their own runs cancelled before they could react.

The checkout step takes the head SHA the resolve step produced, with full history so the merge base is exact and so the base commit is present locally, and with credential persistence turned off so the token is not written into the repository's own git config where the agent would find it.

The review step is where the agent lives. Two things keep the secrets away from it. The environment the agent's shell runs under is built by Coral variable by variable rather than inherited, because the backend inherits nothing on its own and an empty environment would leave the agent unable to run a command at all. Coral puts in what the runner's toolchain needs and leaves out both secrets, along with every trace of Coral's own virtualenv, so that the repository's tests run against the repository's interpreter. Separately the step reads the OpenRouter key and the GitHub token out of its own process environment, holds them in memory, and deletes them before constructing anything, so no later code that assembles a child environment can pick them up by accident. The model client and the posting code still hold what they were handed. The agent then reaches the checkout through a single DeepAgents backend, which is the seam where Coral's own code stops and the framework starts. Nothing else in the codebase shells into the checkout or holds a second idea of where it lives. Coral runs directly on the runner rather than inside a container of its own, and that is deliberate: the agent needs the runner's preinstalled toolchain to run the tests of a repository it has never seen.

The agent hands back a structured review object and nothing else. That constrains what it returns, not what its shell does, which is why the missing credentials matter as much as the schema. Together they are what make "Coral never pushes and never approves" a property rather than an instruction.

Posting is deterministic code again. It checks each finding's anchor against the diff it computed locally between the two pinned commits, demotes the ones that will not attach into the summary, rechecks that the pull request has not merged in the meantime, and posts one review naming the commit. GitHub accepts or rejects a review as a whole, so one bad anchor would otherwise take every finding with it. If GitHub rejects the batch, the retry demotes every anchored finding into the summary and reposts with no inline comments at all. That is deliberately blunt: a retry that depended on the error naming the offending entry would fail silently when it did not, and the guarantee worth keeping is that no finding is ever lost.

Failure reporting has two halves. Coral owns its own deadline and sets it comfortably inside the job's timeout, so a run that overruns is still alive and still holds the token, and it posts its own failure and records that it did so. Everything that fails earlier — a rate-limited API call, a force-pushed SHA the checkout cannot find, a full disk, a missing key — never reaches that code, so the report step picks those up on the job's failure path and posts instead. It matters because a person may already have seen Coral react to their request, and a reaction followed by nothing is worse than no reaction at all. Only a run that dies with the runner itself escapes both, and that shows up as a failed run in the Actions tab, where the recovery is that a person asks again.

## Invariants

Facts that stay true as the code moves, recorded so a later plan does not have to re-derive them. One line each. `/build` appends to this section as plans land.

- Coral stores nothing. Any question about what Coral has already done is answered by reading the pull request.
- The agent's only return value is the structured review object. Fetching and posting are deterministic code.
- No secret is reachable from the agent's shell. Its environment is built by naming what goes in rather than by removing what should not, and both secrets are also deleted from Coral's own process environment before the backend is constructed.
- Coral's own code runs `git` against the checkout; the agent never does, and reaches it only through the DeepAgents backend. Both facts are what make the diff the agent saw and the diff the anchors are checked against the same diff.
- The checkout's location is read from the environment in one place, `coral/runner.py`, and passed from there.
- Coral's own virtual environment lives under the runner's temporary directory, outside the workspace, and is never activated or placed on `PATH`. Every step runs the console script by absolute path.
- A run Coral declines to make ends green. Only a run that broke ends red.
- The review is defined by two commit SHAs, both read from the GitHub API and both pinned at the start of the run. Neither arrives on an event, neither is a branch name, and neither is read a second time.
- Every review opens with a machine-readable marker carrying the commit it reviewed, because the next run reads that back. The prose that names the commit is for the human reader and is not the record.
- Every way a review can fail ends in a comment on the pull request. The review step reports what it can reach; the report step covers everything that fails before it.
- Coral runs on the runner, not in a container, because it needs the runner's toolchain to run the repository's tests.
- Anything the agent is told not to do — run the whole suite, commit its scratch files, write outside the checkout — is a prompt-level request. Only the missing credentials and the output schema are enforced.
- The review object is the only place structure originates. It is a set of frozen dataclasses handed to the agent framework unchanged, so the type the model fills is the type the posting code reads.
- A finding's anchor is a union of four frozen dataclasses, each naming itself with a `kind` literal. Reading one is an exhaustive `match` over the four classes, so a fifth kind is a type error at every site rather than a runtime surprise.
- The schema's JSON form uses `anyOf` and no `oneOf`, which is what a strict provider-side validator accepts.
- The agent's structured result is required. Its absence, and a `structured_response` of `None`, are the same failure, and there is no path that recovers a review from prose or substitutes an empty one.
- The interpreter is pinned in `.python-version` and by `requires-python`; `ruff`, `pytest`, and `mypy` are all configured in `pyproject.toml`.
