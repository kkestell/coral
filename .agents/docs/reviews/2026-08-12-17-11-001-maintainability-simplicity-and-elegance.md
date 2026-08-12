# Review: maintainability, simplicity, and elegance

A read of every Python module, workflow, composite action, prompt, test module, and authoritative
project document. `uv run pytest` passes 419 tests; `uv run ruff check`, `uv run ruff format
--check`, `uv run mypy`, and `git diff --check` all pass. Pytest reports two dependency warnings:
LangChain imports Pydantic v1 compatibility code that warns on Python 3.14, and Google GenAI uses a
typing implementation detail deprecated for removal in Python 3.17.

Priorities describe maintenance cost, not Coral finding severity. Dispositions assume the stated
TypeScript rebuild is real; maintaining the Python implementation instead changes the first two
recommendations.

## 1. The repository has no single current product contract

Priority: critical

Disposition: decide the Python implementation's lifecycle before changing it again.

`functional-requirements.md` says it describes what Coral does and is the whole product, including
`pull_request_target`, referenced-issue context, and end-to-end byte limits. The implementation has
none of those three. `roadmap.md` is wholly a not-started TypeScript rebuild, while `architecture.md`,
`development.md`, `testing.md`, and `README.md` describe the live Python implementation. Architecture
even points two known Python gaps at roadmap items that will be implemented in another language.

This is more expensive than stale prose. An agent following `AGENTS.md` cannot tell whether a task
should preserve the Python architecture, advance the TypeScript roadmap in this repository, or make
the Python implementation meet the requirements. The latest plan explains the cleanroom handoff,
but plans are immutable historical records and explicitly are not where current facts are read.

Choose one of two honest states:

- If Python is frozen evidence for a separate rebuild, say that in one authoritative current
  document, stop treating this repository's roadmap as work on this tree, and make clear that the
  requirements are the target product rather than the behavior of the shipped tag.
- If this repository remains the product, restore a roadmap for it and treat the three mismatches as
  unfinished high-priority work. The TypeScript roadmap belongs in the future repository it governs.

Do not refactor the Python internals until this is settled. Most recommendations below should be
implemented only in the version that will live.

## 2. The shipped automatic-review trigger still gives branch workflow code the secrets

Priority: critical

Disposition: fix immediately if `v0.1.0` remains installable; otherwise retire that installation.

Both `.github/workflows/review.yml` and `examples/coral.yml` trigger automatic reviews with
`pull_request`. The caller gives that job the OpenRouter secret and write-scoped issue and
pull-request token, and the repository itself documents that the pull-request branch supplies the
workflow code. A same-repository branch author can therefore replace the workflow before Coral's
fork and container gates run.

This was already reported, and the new requirements now explicitly reject it. The code is locally
careful about job and container boundaries, but those boundaries cannot compensate for the caller
workflow itself running from the untrusted branch. Move automatic delivery to default-branch
workflow code before advertising the current release as satisfying the requirements.

## 3. The safety net is configured but not run by CI

Priority: high

Disposition: trivially fixable.

`pyproject.toml` configures strict mypy, Ruff, formatting, and pytest, and `code-style.md` explicitly
depends on a strict type checker and linter in CI. Neither workflow runs any of them. The only
repository workflow runs Coral itself; the 419 passing tests are evidence about this checkout, not
a guard on the next push to `main`.

Add one ordinary check job using the committed lockfile and the four documented commands. Keep it
one job and do not introduce a matrix: this project pins one Python version and values a small
surface area. If Python is frozen, run it on pushes that touch the frozen tree so the evidence does
not decay accidentally.

## 4. The agent boundary is coupled to undocumented DeepAgents mechanics

Priority: high

Disposition: simplify in the implementation that will live; do not add another adapter layer.

`coral/agent.py` is the only importing module, which is good, but it relies on several incidental
framework behaviors inside that module:

- `ContainerBackend` must inherit `BaseSandbox` because tool registration uses an `isinstance`
  check.
- A replacement filesystem middleware works because middleware merge identity currently equals the
  class name.
- Construction mirrors a private permissions-list default and assumes OpenRouter has no harness
  profile.
- The recursion cap depends on a second `with_config` overriding the framework's own value.
- `grep` rejects one public argument shape because the dependency emits a broken shell script.

Tests appropriately pin several of those assumptions, but that converts ordinary dependency
upgrades into a forensic exercise. About half of `agent.py` and a substantial part of
`test_agent.py` exist to adapt or characterize the framework rather than express Coral's review
domain.

Prefer the smallest explicit tool surface Coral needs: one container-backed execute tool can read,
search, edit, and run focused tests with ordinary shell commands. If named file tools materially
improve model behavior, own their tiny command implementations rather than inherit the framework's
filesystem middleware. Keep DeepAgents for the loop only. This removes the inheritance constraint,
upload/download bridge, upstream glob and grep quirks, middleware replacement assumption, and many
dependency-contract tests together.

## 5. Pull-request and main-push behavior are interleaved through one long orchestration function

Priority: medium

Disposition: simplify when the next cross-cutting context or limit is implemented.

`review()` is 167 lines and branches on `main_push` while loading the subject, rendering the first
request, constructing verifier tools, rendering the verification request, filtering duplicate
evidence, and choosing publication payloads. Four request-rendering functions duplicate the same
document shape, and the main verification variant changes pull-request prose with an exact string
replacement. Duplicate-suppression logic is also repeated once for logging in `review.py` and once
for the actual decision in `schema.py`.

This structure made the current two modes readable when they were small, but it is now the place
every new context block and end-to-end limit has to be threaded through repeatedly. Represent the
subject as a small tagged union, split pull-request and push setup/publication at the edges, and keep
one shared reviewer/verifier core. Have the schema filter return dispositions that logging can read
instead of reimplementing the decision. Avoid a class hierarchy or generic pipeline framework; two
plain subject dataclasses and a few `match` statements fit the project's style.

## 6. Python 3.14 currently outruns part of the dependency stack

Priority: low

Disposition: accept only if Python is frozen; otherwise remove the warning at the boundary.

The package requires Python 3.14 and uses it for only one new exception-list spelling; its generic
function syntax already works on Python 3.12. A clean test run imports a LangChain compatibility
module that explicitly warns its Pydantic v1 path is incompatible with Python 3.14. Everything
tested still passes, so this is not a demonstrated defect, but it makes the only supported runtime
one a central dependency does not fully support.

Either pin the project to the newest Python version supported without warnings by the selected
agent stack, or document and test why the warned code path is unreachable. Do not suppress the
warning globally.

## What holds up

The deterministic core is notably good. Frozen dataclasses and pattern matching make the review
contract readable; schema validation and publication are separated from model control; credentials,
workspaces, and posting authority have narrow owners; the container implementation bounds processes,
time, and output rather than relying on prompt behavior; and comments usually explain a measured
constraint rather than narrating obvious code. Module names and paths align closely with the three
pipeline stages. The unit suite is fast, edge-oriented, and unusually effective at recording subtle
GitHub and framework contracts.

The overall recommendation is therefore subtraction, not redesign: settle which implementation is
alive, close the shipped trigger gap, enforce the checks already present, and spend architectural
effort only in the implementation that will survive.
