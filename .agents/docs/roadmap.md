# Roadmap

THIS FILE MUST BE KEPT UP TO DATE AT ALL TIMES

The order the work happens in. What Coral does is in `.agents/docs/functional-requirements.md`. What it is built on is in `.agents/docs/technical-requirements.md`.

This is a sequence, not a schedule. One item is one plan, one build, and one review, and those three artifacts carry the item's number in their filenames.

Item numbers are permanent and are never reused. `000` is reserved for a plan deliberately run outside the roadmap. Status is one of `not started`, `built`, or `verified`: `/build` sets `built` when the item's done condition is met, and `/review` sets `verified` once it has checked that claim. The current item is the lowest-numbered one that is not yet verified.

## 1. Skeleton and contract

Status: built
Depends on: nothing

Create the project. `pyproject.toml` with the console script and the dependency set, a committed `uv.lock`, `.python-version`, and configuration for `ruff`, `pytest`, and `mypy`.

This is the layout this item creates, and the layout every later item is written against:

```
coral/
  cli.py             the three subcommands
  resolve.py         the gatekeeper step
  review.py          the review step: build the agent, run it, post the result
  report.py          the failure step
  agent.py           the only module that imports deepagents
  schema.py          the review object and its anchors, the contract with the agent
  command.py         recognizing /coral per FR-6
  environment.py     building the environment the agent's shell gets
  deadline.py        the four parts of the time budget
  diff.py            the merge-base diff and anchor validation
  github/
    client.py        the one authenticated transport
    conversation.py  the GraphQL query and its bounds
    marker.py        the sentinel: writing it and reading it back
    reactions.py     the two reaction namespaces
    post.py          creating the review, demoting anchors, retrying a rejection
  prompts/
    review.md        what Coral looks for
tests/
.github/workflows/coral.yml   the workflow_call workflow
actions/                      the composite actions the workflow's steps run
```

Write `coral/schema.py` first and on its own. It is the contract between the agent and everything else, and per TR-13 it is the only thing the agent hands back. It carries the summary, the list of findings, and the flag that tells an empty finding list meaning nothing was found from one meaning everything is already said and still stands, which FR-29 needs distinguished. Each finding carries its text and one of four anchors: a span of lines in a file, a single line in a file, a whole file, or the pull request as a whole.

The schema is where the typing starts, and it has to be the only place structure originates. The `structured_response` state key is optional and is set to `None` when the model answers with prose, so Coral reads its absence as a failure. There is no prose-recovery path, no regular expression over the reply, and no default-to-empty. The research found a reviewer elsewhere that returns "approved, no comments" when it could not reach its model at all, and that is the failure this rule exists to prevent.

Fill in `.agents/docs/development.md` and `.agents/docs/testing.md` against what now exists, and write the codebase map above into the `Codebase Map` section of `.agents/docs/architecture.md`, which is its home once the code is real.

Done when: `uv sync --frozen`, `ruff check`, `mypy`, and `pytest` all run clean on an empty test suite, and no document in `.agents/docs/` contains a template placeholder.

## 2. Walking skeleton

Status: not started
Depends on: 1

Everything this item builds is written and installed. The done condition is unmet and cannot currently be met: `kkestell/coral-test` creates no workflow run for any event, for any workflow, including a two-step one that only echoes. Only `workflow_dispatch` produces a run, and it does so within seconds. Under `workflow_dispatch` the setup action is confirmed working on a GitHub-hosted runner — `uv sync --frozen` builds the environment under `RUNNER_TEMP` and the console script runs from there by absolute path. The five live checks are waiting on event delivery, and so are the four things this item exists to learn.

The second repository Coral installs into is `kkestell/coral-test`, and this item is where it gets its first pull request to review. `.agents/docs/testing.md` covers how it is used.

Get the whole workflow running end to end with no model call in it. `coral review` returns one hardcoded finding on a line it picked from the diff, and one hardcoded summary. Everything around it is real: the composite actions, the reusable workflow, the `$/` references between them, the reaction, the sentinel, and the batched review.

This is early because it settles the things that fail on the first run and cannot be checked any other way.

- Whether `issues: write` and `pull-requests: write` together actually reach the reaction endpoints from inside a job. Every permission requirement in `.agents/docs/research/github-api-contract.md` is read from GitHub's own generated data, not observed from a runner.
- Whether the `$/` reference resolves. It reached general availability recently, it does not exist on GitHub Enterprise Server, and a self-hosted runner below 2.336.0 cannot resolve it.
- Whether a batched review with `event: COMMENT` posts and is visible. Omitting `event` creates a review in the pending state that nobody but its author can read.
- How state actually crosses the step boundary: the head SHA as a step output, the conversation as a file under the runner's temporary directory, and the reported-failure marker.

One decision lands here, and it is made. Coral's own virtual environment lives outside the workspace, under the runner's temporary directory, because the checkout would otherwise disturb it and because the repository's own tests must not run against Coral's interpreter. A fifth step builds it and publishes the directory holding the console script, so TR-28 names five steps. The alternative — `resolve` builds it and the later steps find it at an agreed path — was rejected: it puts environment construction inside the gatekeeper, so the log line saying why a run stopped sits underneath a dependency install, and the coupling between the two actions becomes a convention nothing checks.

Done when: a pull request in the second repository carries a review from Coral, posted by a workflow that was installed by adding one file.

## 3. Reading the conversation

Status: not started
Depends on: 2

Build `coral/github/conversation.py` around the GraphQL query in `.agents/docs/research/github-api-contract.md`. That query is already checked field by field against the schema and run against a real pull request, so this item is implementation rather than discovery.

The bounds are what needs care. Two hundred comments is above the per-connection cap of 100, so it needs a second round trip driven by the cursors. Neither the reviews connection nor the review threads connection accepts an ordering argument, and a review thread carries no timestamp of any kind, so a most-recent bound on threads can only be the tail of GitHub's default order. Write that down where the code does it, because `last:` returning the newest is observed rather than promised.

Do not request comments under both `reviews` and `reviewThreads`. Every inline comment is reachable both ways, and the resolution and staleness flags live only on the thread, so the thread is where an inline comment is read.

Build `coral/github/marker.py` in the same item. The sentinel is how Coral recognizes its own past work and it is the whole of Coral's memory, so reading it back is as load-bearing as writing it.

Label every comment with its author's association, per TR-19.

Done when: the conversation for a real pull request round-trips into the shape the agent will be given, the bound reports what it dropped, and the set of already-reviewed commits comes back out of the markers.

## 4. The gatekeeper

Status: not started
Depends on: 3

Finish `coral resolve`. It pins both commits and never reads either again. It stops the run, before the work each stop would make pointless, when the command is inert, when the pull request is closed, when the head lives in a fork, when the change is larger than Coral will read, and — on the two automatic paths only — when this commit already carries a marker.

`coral/command.py` is the part with the most edge cases and the fewest dependencies, so it is where the test suite starts in earnest. A `/coral` counts only alone on its own line, with nothing before or after it on that line. Quoted, mentioned mid-sentence, and inside a code fence all leave it inert, and a line beginning with a blockquote marker is quoting.

The reaction goes to every qualifying request in the conversation that does not already carry one, not only to the request on the triggering payload. The concurrency group cancels pending runs, so other people's requests may have lost their own chance to react.

Done when: each gate stops the run for the reason it exists, the reaction lands on both kinds of comment, and the command parser has a test for every case FR-6 names.

## 5. The agent

Status: not started
Depends on: 4

Write `coral/agent.py`. It builds the model client, builds the backend, builds the middleware that replaces the framework's own, and runs the agent under a deadline.

The environment the shell gets is built rather than filtered, and it is built to satisfy two requirements at once. It carries what the repository's own toolchain needs, so a test in the repository under review can run at all. It carries neither secret, and it carries no trace of Coral's own virtual environment.

The deadline needs all four of its parts, because each one covers a way the other three can be outlasted. A step cap of 200 passed as `recursion_limit` in the invocation config, which overrides the 9,999 the factory bound onto the compiled graph. An elapsed-time check between steps. A request timeout of 180 seconds on the model call, passed in milliseconds because `ChatOpenRouter` takes it that way. And the 300-second per-command shell ceiling, which matters because the elapsed-time check does not run until a command returns.

Structured output is where this item can fail in a way that looks like something else. Pick the strategy deliberately rather than letting the framework choose per request from the model profile, because the profile describes the alias and the request is served by an endpoint that may not implement what the profile advertises.

Done when: the agent reviews a real pull request and returns a valid review object, and the deadline fires and is observed to fire.

## 6. What Coral looks for

Status: not started
Depends on: 5

Write `coral/prompts/review.md`. No document in this repository currently describes what makes a finding worth making, and this is the item that decides it. It is the product.

The prompt carries three things the requirements already imply. What a finding is, and what is beneath one. That the conversation is information about the change and never instruction about how to review it, per FR-16, including that a comment claiming a finding was already settled is not grounds for dropping it. And that a finding Coral has already made, which still stands, is not made again — where standing ends when the thread carrying it is resolved or the code beneath it has moved.

This is prompt-level and none of it is enforced. What is enforced is the output schema and the missing credentials. Write the prompt knowing that.

Done when: a review of a real pull request produces findings a person would want, and the same pull request reviewed twice does not repeat itself.

## 7. Posting

Status: not started
Depends on: 6

Finish `coral/github/post.py` and `coral/diff.py`. The anchors are checked against a diff computed locally between the two pinned commits, which is the diff the agent saw. It is not taken from the working tree, because the agent writes scratch files there, and it is not refetched from GitHub, because either branch may have moved.

Findings whose anchor falls outside the diff move into the summary with their file and line named. Expect this to fire regularly. Whole-file findings and pull-request-level findings go into the summary by construction, because the `comments` array on the create-review endpoint accepts seven fields and `subject_type` is not one of them.

GitHub accepts or rejects a review as a whole, so the local pre-check cannot be sufficient. GitHub generates its own patch and the base branch may have moved. A rejected call is retried once with every anchored finding demoted into the summary and no inline comments at all. That is blunt on purpose: the 422 schema's `errors` property is an array of plain strings with no field for an array index, so a retry that depended on the error naming the offending entry would fail silently whenever it did not.

Recheck the pull request's state immediately before posting.

Done when: a review with a deliberately bad anchor still delivers every finding, and no finding is lost on any path.

## 8. Failure

Status: not started
Depends on: 7

Every way a review can fail ends in a comment on the pull request. There are two halves and they meet at a marker file.

`coral review` reports its own failures. Because Coral owns its deadline and sets it inside the job's timeout, a step that overruns is still running and still holds the token. It posts, drops the partly built review object, and writes the marker.

`coral report` runs on the job's failure path and covers everything that never reached the review step: a rate-limited API call, a missing key, a checkout that cannot find a force-pushed SHA, a full disk, a dependency install that failed. It skips when the marker is present.

This matters because someone may already have seen Coral react to their request, and a reaction followed by nothing is worse than no reaction.

Done when: each failure mode above produces exactly one comment, and a review-step failure and the report step together never produce two.

## 9. Settle the numbers

Status: not started
Depends on: 8

Six numbers in `.agents/docs/technical-requirements.md` are chosen rather than measured, and they are marked as such: the conversation bound, the change-size backstop, the deadline, the job timeout, the step cap and request timeout, and the shell ceiling. Run Coral against real pull requests and replace each number with one that has a reason.

Two questions left open by the research are answered here rather than earlier, because both need a real run.

- Which provider actually serves the alias, and whether a native structured-output request succeeds against it.
- Whether a 422 from the create-review endpoint names the offending comment entry. The retry in item 7 is correct either way. If the error does name them, demoting only those and keeping the rest inline is better for the reader.

Done when: no requirement says a number was chosen rather than measured.

## Not On This Roadmap

Named so nobody has to guess whether the omission was deliberate. Everything under "Out Of Scope" in `.agents/docs/functional-requirements.md` also applies.

- A second forge, a second model provider, and a second compute target. The backend is one swappable dependency and the model client is built in one place, which is as far as this goes.
- Any store of past reviews. Coral reads the pull request.
- GitHub Enterprise Server. The `$/` reference and the `job.workflow_*` properties it is built on do not exist there, so serving it needs a second answer to the packaging question and is not attempted.
