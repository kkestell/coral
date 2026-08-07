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

Wrote the failure comment and the reason it carries, which live in `coral/publish.py`.

Done when: every way a review can fail produces exactly one comment.

## 9. Settle the numbers

Status: verified
Depends on: 8

Every number items 3 through 7 chose carries a measured reason where the number lives, and nothing is left under "Undecided" in `.agents/docs/architecture.md`.

## 10. Shrink what a compromised agent gets

Status: built
Depends on: 9

Split the run into three jobs — resolve, review, publish — so the job that runs the agent holds `contents: read` and nothing more. Reactions, the review, and the failure comment happen in the two jobs holding the write scopes.

The `Posting` and `Failure` groups have not been re-run against the split; `VALIDATION_TODO.md` at the repository root is what is owed.

- The OpenRouter key is referenced by the review job alone, which is what makes item 11 safe to build.
- README tells whoever installs Coral to set a credit limit on the OpenRouter key they pass, which is the only bound on what an exfiltrated key can spend.

Done when: a real review in the test repository posts everything it posts today, with the agent's job holding a read-only token and the run green.

## 11. A key per run

Status: not started
Depends on: 10

Coral accepts either a plain OpenRouter API key, used as it is today, or a management key it uses to mint one API key per run. Minting is safe only once item 10 keeps the management key out of the agent's job, because a management key mints against the whole account balance.

- Two `workflow_call` secrets, `openrouter_api_key` and `openrouter_management_key`; resolve fails when neither or both are set. Never one input whose kind Coral detects — detection costs a probe request, and the caller knows which one they created.
- `POST /api/v1/keys` takes `limit` and `expires_at` and returns the key once alongside a `hash`. Set `expires_at` to cover the run, so revocation does not depend on a cleanup job that can be cancelled or skipped.
- A management key cannot call the completion endpoints, and a per-key `limit` caps that key rather than partitioning the account balance.
- Pass-through mode needs no channel; the review job reads the caller's secret directly. Minting mode crosses as a job output, because Actions refuses to set an output matching a registered secret.
- Mask the minted key where it is created and again where it is received. A mask does not cross a job boundary.
- Both modes get live checks. The workflow and the composite actions have no `pytest` coverage, so an unexercised mode is an untested one.

Done when: a real review runs green in each mode, the minted key no longer authenticates once its run is over, and the README says which mode to choose.

## 12. Take the agent out of the runner user

Status: not started
Depends on: 11

Runs the agent's shell inside a container on the runner, out of reach of `Runner.Worker`'s memory, the runner's filesystem, and every secret the job holds. Items 10 and 11 bound what a compromised agent gets; this is the item that stops it getting anything.

- Coral's own process stays on the runner and only the shell tool executes in the container, so no credential enters the container at all.
- A container rather than a second user. Root in a container is not root on the host, so `sudo` and `apt-get` keep working, which is what a second user gives up.
- No Docker reachable from the container, and never `--privileged`. Both are host root, so a daemon the agent can reach is not a sandbox. `.agents/docs/functional-requirements.md` gains this under "Out Of Scope" when this is built.
- `.agents/docs/architecture.md` records that the hosted image's preinstalled toolchain is the only reason a repository Coral has never seen builds at all. The container answers that with `/opt/hostedtoolcache` mounted read-only plus `apt-get` for the rest, and that answer is what this item has to prove.
- The agent gets a copy of the checkout that it owns.

Done when: reviews in the test repository run a Python, a Node, and a Go project's own tests from inside the container, and a shell command the agent runs there can reach neither the runner's filesystem nor its process table.

## Not On This Roadmap

Named so nobody has to guess. Everything under "Out Of Scope" in `.agents/docs/functional-requirements.md` also applies.

- A second forge, model provider, or compute target. The swappable backend and the single model-client construction site are as far as this goes.
- Any store of past reviews. Coral reads the pull request.
- GitHub Enterprise Server. The `$/` reference does not exist there; supporting it means a second packaging answer, not attempted.
