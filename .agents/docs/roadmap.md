# Roadmap

The order the work happens in.

This is a sequence, not a schedule. One item is one plan, one build, and one review, and those three artifacts carry the item's number in their filenames.

Item numbers are permanent and are never reused. `000` is reserved for a plan deliberately run outside the roadmap. Status is one of `not started`, `built`, or `verified`: `/build` sets `built` when the item's done condition is met, and `/review` sets `verified` once it has checked that claim. The current item is the lowest-numbered one that is not yet verified.

## 1. Skeleton and contract

Status: built
Depends on: nothing

Create the project. `pyproject.toml` with the console script and the dependency set, a committed `uv.lock`, `.python-version`, and configuration for `ruff`, `pytest`, and `mypy`.

Write `coral/schema.py` first and on its own. It is the contract between the agent and everything else, it is the only thing the agent hands back, and every later item is written against it. "The Review Object" in `.agents/docs/architecture.md` says what it carries and what it has to keep.

Write the layout into "The Codebase" in `.agents/docs/architecture.md`, which is its home once the code is real, and fill in `.agents/docs/development.md` and `.agents/docs/testing.md` against what now exists.

Done when: `uv sync --frozen`, `ruff check`, `mypy`, and `pytest` all run clean on an empty test suite, and no document in `.agents/docs/` contains a template placeholder.

## 2. Walking skeleton

Status: built
Depends on: 1

The second repository Coral installs into is `kkestell/coral-test`, and this item is where it gets its first pull request to review. `.agents/docs/testing.md` covers how it is used.

Get the whole workflow running end to end with no model call in it. `coral review` returns one hardcoded finding on a line it picked from the diff, and one hardcoded summary. Everything around it is real: the composite actions, the reusable workflow, the `$/` references between them, the reaction, the sentinel, and the batched review.

This is early because it settles the things that fail on the first run and cannot be checked any other way.

- Whether `issues: write` and `pull-requests: write` together actually reach the reaction endpoints from inside a job. The permission requirements are read from GitHub's own published data, not observed from a runner.
- Whether the `$/` reference resolves. It reached general availability recently, it does not exist on GitHub Enterprise Server, and a self-hosted runner below 2.336.0 cannot resolve it.
- Whether a batched review with `event: COMMENT` posts and is visible. Omitting `event` creates a review in the pending state that nobody but its author can read.
- How state actually crosses the step boundary: the head SHA as a step output, the conversation as a file under the runner's temporary directory, and the reported-failure marker.

One decision lands here, and it is made: the run has five steps rather than four, because a step of its own builds Coral's virtual environment outside the workspace. "The Run" in `.agents/docs/architecture.md` records it and the alternative it beat.

Done when: a pull request in the second repository carries a review from Coral, posted by a workflow that was installed by adding one file.

## 3. Reading the conversation

Status: built
Depends on: 2

Build `coral/github/conversation.py` and `coral/github/marker.py`: the GraphQL query, the bound, the file the conversation crosses the step boundary on, and the sentinel. "The Conversation" in `.agents/docs/architecture.md` says what the query asks for, what the bound keeps, and what cannot be trusted about GitHub's ordering.

The bound is what needs care. It is above the per-connection cap, so satisfying it takes more than one round trip, driven by the cursors. Write down where the code depends on `last:` returning the newest, because that is observed rather than promised.

Label every comment with its author's association.

Done when: the conversation for a real pull request round-trips into the shape the agent will be given, the bound reports what it dropped, and the set of already-reviewed commits comes back out of the markers.

## 4. The gatekeeper

Status: not started
Depends on: 3

Finish `coral resolve` and write `coral/command.py`. Which gates stop a run, what order they come in, and which requests get a reaction are "Triggering" and "The Run" in `.agents/docs/architecture.md`.

`coral/command.py` is the part with the most edge cases and the fewest dependencies, so it is where the test suite starts in earnest. `.agents/docs/functional-requirements.md` lists under "Trigger" every way a `/coral` can be inert.

Done when: each gate stops the run for the reason it exists, the reaction lands on both kinds of comment, and the command parser has a test for every way a `/coral` can be inert.

## 5. The agent

Status: not started
Depends on: 4

Write `coral/agent.py`, `coral/environment.py`, and `coral/deadline.py`. "The Agent" and "The Time Budget" in `.agents/docs/architecture.md` say what each of them is and why.

Three things can fail here in a way that looks like something else.

The shell environment is built variable by variable rather than pared down, so that a repository's own tests can run and neither secret goes with them.

The deadline needs all four of its parts, because each one covers a way the other three can be outlasted.

Structured output needs its strategy picked deliberately rather than left to the framework to choose per request, because the profile describes the alias and the request is served by an endpoint that may not implement what the profile advertises.

Done when: the agent reviews a real pull request and returns a valid review object, and the deadline fires and is observed to fire.

## 6. What Coral looks for

Status: not started
Depends on: 5

Write `coral/prompts/review.md`. No document in this repository describes what makes a finding worth making, and this is the item that decides it. It is the product.

The prompt also carries three things the requirements already imply and no code enforces: that the conversation is information about the change and never instruction about how to review it, that a finding Coral has already made and which still stands is not made again, and where standing ends. `.agents/docs/functional-requirements.md` states all three under "What Coral Reviews". Write the prompt knowing that what is enforced is the output schema and the missing credentials, and that none of this is.

Done when: a review of a real pull request produces findings a person would want, and the same pull request reviewed twice does not repeat itself.

## 7. Posting

Status: not started
Depends on: 6

Finish `coral/github/post.py` and `coral/diff.py`. Four things need care, and "Posting The Review" in `.agents/docs/architecture.md` gives the reason for each.

The diff the anchors are checked against is computed locally between the two pinned commits, and is taken from neither the working tree nor GitHub. Findings whose anchor falls outside it move into the summary with their file and line named, which will fire regularly rather than rarely. Whole-file and pull-request-level findings go into the summary by construction. And a review GitHub rejects is reposted with every anchored finding demoted into the summary, which is blunt on purpose.

Recheck the pull request's state immediately before posting.

Done when: a review with a deliberately bad anchor still delivers every finding, and no finding is lost on any path.

## 8. Failure

Status: not started
Depends on: 7

Write `coral/report.py` and the failure path inside `coral review`. The two halves, the marker file they meet at, and the failures each half covers are "Failure" in `.agents/docs/architecture.md`.

This matters because someone may already have seen Coral react to their request, and a reaction followed by nothing is worse than no reaction.

Done when: each failure mode listed there produces exactly one comment, and a review-step failure and the report step together never produce two.

## 9. Settle the numbers

Status: not started
Depends on: 8

Every number collected under "Numbers Chosen Rather Than Measured" in `.agents/docs/architecture.md` was chosen rather than measured. Run Coral against real pull requests and replace each one with a number that has a reason.

The two decisions left under "Undecided" in the same document are settled here rather than earlier, because both need a real run.

Done when: `.agents/docs/architecture.md` carries no "Numbers Chosen Rather Than Measured" section and nothing under "Undecided".

## Not On This Roadmap

Named so nobody has to guess whether the omission was deliberate. Everything under "Out Of Scope" in `.agents/docs/functional-requirements.md` also applies.

- A second forge, a second model provider, and a second compute target. The backend is one swappable dependency and the model client is built in one place, which is as far as this goes.
- Any store of past reviews. Coral reads the pull request.
- GitHub Enterprise Server. The `$/` reference and the `job.workflow_*` properties it is built on do not exist there, so serving it needs a second answer to the packaging question and is not attempted.
