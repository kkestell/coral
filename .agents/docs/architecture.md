# Architecture

THIS FILE MUST BE KEPT UP TO DATE AT ALL TIMES

What this project is built out of, where each part lives, and how the parts fit together. Read this before planning a change, so the change lands where the code already expects it to.

## Tech Stack

- **Language(s):** Python — {version, and the file that pins it}
- **Frameworks:** DeepAgents
- **Build system:** `uv`, against a committed lockfile
- **Datastores:** None. Coral owns no state. What Coral has said about a pull request lives on the pull request, and Coral reads it back from GitHub at the start of every run.
- **Model provider:** OpenRouter — `~deepseek/deepseek-v4-flash-latest`
- **Deployment target:** GitHub Actions. There is no cloud account and nothing to provision. Coral ships as composite actions wired together by a reusable workflow, and a repository installs it by adding one file that calls that workflow. That file carries a version pin, an OpenRouter key, the event triggers, the token permissions, and the concurrency group — the last three because a reusable workflow cannot declare any of them for its caller.

## Codebase Map

{A short description of each major part of the codebase — what it is, what it does, and where it lives. Organize this however suits the project: by directory, by layer, by domain area. One line per entry. Only break into subsections if the project has genuinely separate deployable units with different stacks, such as "### Client" and "### Server".}

- `{path/}` — {what this part does}

## How It Fits Together

A pull request is opened or marked ready for review, or somebody leaves a comment, and GitHub starts a workflow run. Before a runner is allocated, a job-level condition throws out what is certainly not a trigger. That condition is coarse by necessity, because Actions expressions have no regular expressions and no way to work line by line: on a comment it can check that the body mentions the command at all, that it sits on a pull request rather than an issue, and that the author association passes. Deciding whether the command really stands alone on its own line, unquoted and outside a code fence, needs a real parse and happens in the first step of the run. So a comment merely discussing Coral does allocate a runner, and then stops within seconds.

Two properties of the platform do work here that Coral would otherwise have to do itself. Events created with the job's own token start no workflow runs, so Coral cannot trigger itself no matter what its findings say — a property that would stop being free the day Coral is given an identity of its own. And a concurrency group keyed on the pull request number means a run already going finishes undisturbed while a newly queued run replaces whichever run was waiting, which is the whole of "never two at once, and several requests collapse into one".

The run itself is four steps: resolve, check out, review, and report. The first three carry the work, and the split between the first two exists for one reason — the checkout needs a commit SHA that only an API call can supply. The report step runs only when something failed.

The resolve step is the gatekeeper. It fetches the pull request and pins two commits: the head SHA, which is the subject of the review, and the base branch's current SHA. Pinning both is what stops the reviewed diff shifting when either branch moves during the run. It stops the run if the command turns out to be inert, if the pull request is closed, if the change is larger than Coral will read, or if the head lives in a fork — that last check is a security control rather than a scope statement, because a comment event fires in the base repository and would otherwise run the base repository's secrets against a branch nobody vouched for.

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
- Nothing outside the DeepAgents backend shells into the checkout, and nothing else knows where the checkout lives.
- The review is defined by two commit SHAs, both read from the GitHub API and both pinned at the start of the run. Neither arrives on an event, neither is a branch name, and neither is read a second time.
- Every review opens with a machine-readable marker carrying the commit it reviewed, because the next run reads that back. The prose that names the commit is for the human reader and is not the record.
- Every way a review can fail ends in a comment on the pull request. The review step reports what it can reach; the report step covers everything that fails before it.
- Coral runs on the runner, not in a container, because it needs the runner's toolchain to run the repository's tests.
- Anything the agent is told not to do — run the whole suite, commit its scratch files, write outside the checkout — is a prompt-level request. Only the missing credentials and the output schema are enforced.
