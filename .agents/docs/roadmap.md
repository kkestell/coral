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

- The OpenRouter key is referenced by the review job alone, which is what makes item 11 safe to build.
- README tells whoever installs Coral to set a credit limit on the OpenRouter key they pass, which is the only bound on what an exfiltrated key can spend.

Done when: a real review in the test repository posts everything it posts today, with the agent's job holding a read-only token and the run green.

## 11. A key per run

Status: built
Depends on: 10

Coral takes either a plain OpenRouter API key, used as it is, or a management key it mints one capped, expiring API key per run with. `coral/openrouter.py` is the only place Coral speaks to the management API, and the resolve job is the only job the management key reaches.

- A minted key reaches the review job through one cleartext line of that job's log, which no arrangement of masking removes. Its audience is whoever can already read the repository's logs.

Done when: a real review runs green in each mode, the minted key no longer authenticates once its run is over, and the README says which mode to choose.

## 12. Take the agent out of the runner user

Status: built
Depends on: 11

Runs the agent's shell inside a container on the runner, out of reach of `Runner.Worker`'s memory, the runner's filesystem, and every secret the job holds. Items 10 and 11 bound what a compromised agent gets; this is the item that stops it getting anything. `coral/container.py` is the only place Coral speaks to `docker`, and `reset` in `coral/diff.py` is retired by it.

- Each agent run gets its own copy of the checkout and its own container, so the verifier installs whatever the reviewer already installed. Revisit only against a measurement of what that costs.

Done when: reviews in the test repository run a Python, a Node, and a Go project's own tests from inside the container, and a shell command the agent runs there can reach neither the runner's filesystem nor its process table.

## 13. Structured output on any model

Status: built
Depends on: 12

The agent returns its structured object through an arrangement that is not written for one model's behavior. `_run` names the synthetic tool, so no profile key and no table of model names kept upstream decides the strategy.

- A model that answers in the schema on its first response has reviewed the diff alone, having read no file and run no test. Whatever lands keeps the tool calls ahead of the answer.
- One arrangement for every model. A branch per model is a lookup table that goes stale without saying so.
- The synthetic tool binds every call with `tool_choice: required`, which an endpoint may refuse — DeepSeek's own serves v4 Pro but not that — and `require_parameters` routes past the endpoints that do not offer it. A model Coral cannot serve is one with no endpoint left, which reaches the caller as the provider's own words.

Done when: the reviewer returns a valid `Review` from each model tested with tools called before the answer, and a real review in the test repository still posts confirmed findings.

## 14. Configuration knobs

Status: built
Depends on: 13

The caller file sets the model, the reasoning effort, and the review's time budget, as `workflow_call` inputs whose defaults leave an existing install reviewing exactly as it does today. The model's context window is fetched from OpenRouter at run time, retiring the profile `coral/agent.py` copies by hand.

- Configuration lives in the caller's workflow file and never in the reviewed repository. GitHub reads that file from the default branch on the comment paths, so a file in the checkout would let a pull request pick the model that reviews it by commenting `/coral`.
- A model name carrying a `~` alias is refused, which is what keeps the exact-naming rule in `.agents/docs/architecture.md` true once the name comes from outside.
- A model OpenRouter does not list stops the run saying so. A model run against a guessed profile is one whose summarization triggers are scaled to somebody else's context window.
- The job's `timeout-minutes` is derived from the budget input and keeps the headroom `coral/deadline.py` explains, and the input is bounded by GitHub's own ceiling on a job.
- Nothing validates the model or the effort ahead of the review job. A value the provider refuses arrives as the provider's own words in the failure comment, the path a broken key already takes.

Done when: a review in the test repository runs green on a model, an effort, and a budget the caller named; an install naming none of them is unchanged; and an aliased model name and an over-ceiling budget each stop the run with the reason said.

## 15. A spend ceiling

Status: built
Depends on: 14

Coral stops a review that has spent more than the caller's cap, in both key modes. Every OpenRouter response carries its own cost, which `ChatOpenRouter` puts in the message's `response_metadata`; the running total is checked between steps, where the deadline is checked.

- One input drives both mechanisms: it caps a minted key at mint time and stops the run when the accounting reaches it. The provider's cap survives Coral's arithmetic being wrong, and the accounting reaches the passed-through key that no minted cap does.

Done when: a review capped at a fraction of a cent stops and posts one comment naming what it spent against the cap, in each key mode, and a review under its cap posts its review and nothing beside it.

## 16. What a review cost

Status: built
Depends on: 15

Every review ends with what the run spent, read off the ledger item 15 built. Coral is installed on its own repository, so this is the first item checked by a pull request on `kkestell/coral` rather than on the test repository.

- The figure is Coral's own accounting rather than the model's, composed where the payloads are, so a compromised agent cannot understate what it spent.
- Four decimal places. Every review measured so far cost a fraction of a cent, which cents would print as `$0.00`.

Done when: a pull request on `kkestell/coral` carries a review whose last line names what it cost, matching the total in the review step's log.

## 17. Encrypt the minted key between jobs

Status: not started
Depends on: 16

The resolve job still mints the capped, expiring OpenRouter API key, but only ciphertext crosses into the review job. The management key remains confined to resolve, and neither the key nor a reversible text encoding of it appears in a job output, log, or artifact.

- The plain API-key mode remains unchanged, because GitHub already registers that caller secret with the review job's masker.
- The review process decrypts the minted key outside the agent's container and never writes its plaintext to the checkout or an artifact.

Done when: a real review using a management key runs green, the complete run log contains no cleartext minted key, and the review container still carries no credential.

## 18. External credential broker (optional)

Status: not started
Depends on: 17

An installation can use an external broker that holds the OpenRouter management key outside GitHub Actions. The review job authenticates with its GitHub OIDC identity, and the broker grants authority for only that repository, workflow run, model, spend cap, and expiry.

- This is optional hardening. An installation without a broker keeps the encrypted handoff from item 17.
- No standing broker credential reaches GitHub Actions. Compromising one review can spend no more than that review's server-enforced cap.

Done when: a broker-backed real review runs green without an OpenRouter management key in GitHub, a request with the wrong workflow identity or run parameters is refused, and the same caller still runs through the encrypted-handoff path when broker configuration is absent.

## 19. MicroVM agent shell (optional)

Status: not started
Depends on: 17

An installation can run agent-chosen commands in a disposable microVM whose kernel is separate from the review runner. The model client and its credential remain on the runner side of that boundary.

- This is optional hardening. An installation without a microVM keeps the container path from item 12.
- The microVM gets the checkout and toolchains it needs, but no OpenRouter credential, GitHub token, runner filesystem, runner process table, or host control socket.

Done when: broker-backed and encrypted-handoff reviews each run Python, Node, and Go project tests inside the microVM; commands there cannot reach the runner's filesystem or process table; and an installation with no microVM configuration still runs the same checks in the container.

## 20. Review main commits as issues

Status: not started
Depends on: 17

Coral reviews every commit pushed to `main` against the prior main commit. It creates one issue for each confirmed finding instead of a pull-request review.

Done when: a planted defect pushed to `main` in the test repository produces one issue per confirmed finding, no pull-request review, and an empty main-push review creates no issue.

## Not On This Roadmap

Named so nobody has to guess. Everything under "Out Of Scope" in `.agents/docs/functional-requirements.md` also applies.

- A second forge or model provider. The swappable backend and the single model-client construction site are as far as this goes.
- Any store of past reviews. Coral reads the pull request.
- GitHub Enterprise Server. The `$/` reference does not exist there; supporting it means a second packaging answer, not attempted.
