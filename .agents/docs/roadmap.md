# Roadmap

The order the work happens in. A sequence, not a schedule: one item is one plan, one build, and one review, and those artifacts carry the item's number in their filenames.

Item numbers are permanent and never reused; `000` is reserved for a plan deliberately run outside the roadmap. Status is `not started`, `built`, or `verified`: `/build` sets `built` when the done condition is met, `/review` sets `verified` after checking that claim. The current item is the lowest-numbered one not yet verified.

## 1. Skeleton and contract

Status: built
Depends on: nothing

Create the project: `pyproject.toml` with the console script and dependencies, a committed `uv.lock`, `.python-version`, and configuration for `ruff`, `pytest`, and `mypy`.

Write `coral/schema.py` first and on its own — it is the contract every later item is written against. "The Review Object" in `.agents/docs/architecture.md` says what it carries.

Write the layout into "The Codebase" there, and fill in `.agents/docs/development.md` and `.agents/docs/testing.md` against what exists.

Done when: `uv sync --frozen`, `ruff check`, `mypy`, and `pytest` run clean on an empty suite, and no document in `.agents/docs/` contains a template placeholder.

## 2. Walking skeleton

Status: built
Depends on: 1

Get the whole workflow running end to end with no model call: `coral review` returns one hardcoded finding on a line picked from the diff, plus a hardcoded summary. Everything around it is real — the composite actions, the reusable workflow, the `$/` references, the reaction, the sentinel, the batched review. This is where `kkestell/coral-test` gets its first pull request.

Early because it settles what fails on the first run and cannot be checked another way:

- Whether `issues: write` plus `pull-requests: write` actually reach the reaction endpoints from a job.
- Whether the `$/` reference resolves — recently GA, absent on GitHub Enterprise Server, unresolvable below runner 2.336.0.
- Whether a batched review with `event: COMMENT` posts and is visible; omitting `event` creates a pending review only its author can read.
- How state crosses the step boundary: the head SHA as an output, the conversation as a file, the reported-failure marker.

One decision landed: five steps rather than four, with a step of its own building Coral's virtual environment. "The Run" in `.agents/docs/architecture.md` records it.

Done when: a pull request in the test repository carries a review from Coral, posted by a workflow installed by adding one file.

## 3. Reading the conversation

Status: built
Depends on: 2

Build `coral/github/conversation.py` and `coral/github/marker.py`: the GraphQL query, the bound, the file the conversation crosses the step boundary on, the sentinel. "The Conversation" in `.agents/docs/architecture.md` says what the query asks for and what cannot be trusted about ordering.

The bound needs care: it sits above the per-connection cap, so satisfying it takes cursor-driven paging, and the dependence on `last:` returning the newest is observed rather than promised. Label every comment with its author's association.

Done when: a real pull request's conversation round-trips into the shape the agent gets, the bound reports what it dropped, and the already-reviewed commits come back out of the markers.

## 4. The gatekeeper

Status: built
Depends on: 3

Finish `coral resolve` and write `coral/command.py`. The gates, their order, and which requests get a reaction are "Triggering" and "The Run" in `.agents/docs/architecture.md`.

`coral/command.py` has the most edge cases and the fewest dependencies, so the test suite starts in earnest there. "Trigger" in `.agents/docs/functional-requirements.md` lists every way a `/coral` can be inert.

Done when: each gate stops the run for its reason, the reaction lands on both kinds of comment, and the parser has a test for every inert form.

## 5. The agent

Status: not started
Depends on: 4

Write `coral/agent.py`, `coral/environment.py`, and `coral/deadline.py`. "The Agent" and "The Time Budget" in `.agents/docs/architecture.md` say what each is.

Three traps look like something else when they fail: the shell environment must be built variable by variable, the deadline needs all four of its parts, and structured output needs its strategy picked deliberately rather than left to the framework's per-request choice.

Done when: the agent reviews a real pull request and returns a valid review object, and the deadline fires and is observed to fire.

## 6. What Coral looks for

Status: not started
Depends on: 5

Write `coral/prompts/review.md`. No document describes what makes a finding worth making; this item decides it. It is the product.

The prompt also carries three things no code enforces, all under "What Coral Reviews" in `.agents/docs/functional-requirements.md`: conversation is information and never instruction, a standing finding is not repeated, and where standing ends. What is enforced is the output schema and the missing credentials — nothing else.

Done when: a review of a real pull request produces findings a person would want, and the same pull request reviewed twice does not repeat itself.

## 7. Posting

Status: not started
Depends on: 6

Finish `coral/github/post.py` and `coral/diff.py`. "Posting The Review" in `.agents/docs/architecture.md` gives the rules: the diff computed locally between the pinned commits, unanchorable findings demoted with file and line named, whole-file findings in the summary by construction, the blunt demote-everything retry on rejection, and the state recheck before posting.

Done when: a review with a deliberately bad anchor still delivers every finding, and no finding is lost on any path.

## 8. Failure

Status: not started
Depends on: 7

Write `coral/report.py` and the failure path inside `coral review`. The two halves, the marker file they meet at, and what each covers are "Failure" in `.agents/docs/architecture.md`.

Done when: each failure mode listed there produces exactly one comment, and the review step and report step together never produce two.

## 9. Settle the numbers

Status: not started
Depends on: 8

Run Coral against real pull requests and replace every number under "Numbers Chosen Rather Than Measured" in `.agents/docs/architecture.md` with one that has a reason. The two "Undecided" items settle here too — both need a real run.

Done when: `.agents/docs/architecture.md` carries no "Numbers Chosen Rather Than Measured" section and nothing under "Undecided".

## Not On This Roadmap

Named so nobody has to guess. Everything under "Out Of Scope" in `.agents/docs/functional-requirements.md` also applies.

- A second forge, model provider, or compute target. The swappable backend and the single model-client construction site are as far as this goes.
- Any store of past reviews. Coral reads the pull request.
- GitHub Enterprise Server. The `$/` reference does not exist there; supporting it means a second packaging answer, not attempted.
