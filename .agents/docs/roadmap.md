# Roadmap

The order the work happens in. A sequence, not a schedule: one item is one plan, one build, and one review, and those artifacts carry the item's number in their filenames.

Item numbers are permanent and never reused; `000` is reserved for a plan deliberately run outside the roadmap. Status is `not started`, `built`, or `verified`: `/build` sets `built` when the done condition is met, `/review` sets `verified` after checking that claim. The current item is the lowest not yet verified.

## 1. Skeleton and contract

Status: built
Depends on: nothing

Created the project (`pyproject.toml`, `uv.lock`, `.python-version`, `ruff`/`pytest`/`mypy` configuration) and `coral/schema.py`, the contract every later item is written against.

Done when: `uv sync --frozen`, `ruff check`, `mypy`, and `pytest` run clean on an empty suite, and no document in `.agents/docs/` contains a template placeholder.

## 2. Walking skeleton

Status: built
Depends on: 1

Got the whole workflow running end to end with no model call: `coral review` returned one hardcoded summary and one hardcoded finding on a line picked from the diff, with the composite actions, reusable workflow, `$/` references, reaction, sentinel, and batched review already real.

Done when: a pull request in the test repository carries a review from Coral, posted by a workflow installed by adding one file.

## 3. Reading the conversation

Status: built
Depends on: 2

Built `coral/github/conversation.py` and `coral/github/marker.py`.

Done when: a real pull request's conversation round-trips into the shape the agent gets, the bound reports what it dropped, and the already-reviewed commits come back out of the markers.

## 4. The gatekeeper

Status: built
Depends on: 3

Finished `coral resolve` and wrote `coral/command.py`. "Trigger" in `.agents/docs/functional-requirements.md` lists every way a `/coral` can be inert.

Done when: each gate stops the run for its reason, the reaction lands on both kinds of comment, and the parser has a test for every inert form.

## 5. The agent

Status: built
Depends on: 4

Wrote `coral/agent.py`, `coral/environment.py`, and `coral/deadline.py`.

Done when: the agent reviews a real pull request and returns a valid review object, and the deadline fires and is observed to fire.

## 6. What Coral looks for

Status: built
Depends on: 5

Wrote `coral/prompts/review.md` and `coral/prompts/verify.md`, extended the contract in `coral/schema.py`, and added the verifier run. What makes a finding worth making is written in the reviewer's prompt and nowhere else.

Done when: a review of a real pull request produces confirmed findings a person would want at sensible severities, a planted defect comes back with a regression test that fails at head, a rejected finding is observed to drop, and the same pull request reviewed twice does not repeat itself.

## 7. Posting

Status: built
Depends on: 6

Finished `coral/github/post.py` and `coral/diff.py`.

Done when: a review with a deliberately bad anchor still delivers every finding, and no finding is lost on any path.

## 8. Failure

Status: verified
Depends on: 7

Wrote `coral/report.py` and the failure path inside `coral review`.

Done when: every way a review can fail produces exactly one comment, and the review step and report step together never produce two.

## 9. Settle the numbers

Status: verified
Depends on: 8

Every number items 3 through 7 chose carries a measured reason where the number lives, and nothing is left under "Undecided" in `.agents/docs/architecture.md`.

## 10. Shrink what a compromised agent gets

Status: not started
Depends on: 9

Splits the run across jobs so the job that runs the agent holds a token with `contents: read` and `pull-requests: read` and nothing more. Reactions, the review, and the failure comment move to jobs that hold the write scopes. `.agents/docs/architecture.md` records that every secret the agent's job references is reachable; this item does not change that, it makes what is reachable worth less.

- A job boundary is not a step boundary. The runner's temporary directory does not survive a job, so everything crossing one crosses as an artifact.
- The review job hands the posting job the finished payload `review_payload` builds, not the review object. The diff the anchors were checked against stays in the job that has the checkout.
- Each job pays setup again. Three virtual environments per run is the price of the split.
- README tells whoever installs Coral to set a credit limit on the OpenRouter key they pass, which is the only bound on what an exfiltrated key can spend.

Done when: a real review in the test repository posts everything it posts today, with the agent's job holding a read-only token and the run green.

## Not On This Roadmap

Named so nobody has to guess. Everything under "Out Of Scope" in `.agents/docs/functional-requirements.md` also applies.

- A second forge, model provider, or compute target. The swappable backend and the single model-client construction site are as far as this goes.
- Any store of past reviews. Coral reads the pull request.
- GitHub Enterprise Server. The `$/` reference does not exist there; supporting it means a second packaging answer, not attempted.
