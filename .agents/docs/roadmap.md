# Roadmap

The order the work happens in. A sequence, not a schedule: one item is one plan, one build, and one review, and those artifacts carry the item's number in their filenames.

## 24. Agent file tools inside the container

Status: built
Depends on: 12

Every agent file tool runs in the container under the limits its shell already has. `read_file`, `write_file`, `edit_file`, `glob`, `grep`, and `delete` reach the checkout through `container.execute` rather than through Coral's Python on the runner.

- The framework's inherited implementation reads a whole file into the runner's memory before slicing it to the requested lines, and its own size cap covers `grep` alone.
- The tools and the shell see one filesystem: a file a tool writes is immediately runnable in the shell, and the other way around.
- A tool's own failure still goes back to the model as an observation rather than ending the run.

Done when: a real review reads, edits, searches, and runs a scratch test through the tools; a read of a file larger than the container's memory limit dies in the container rather than on the runner; and no agent tool reaches the runner's filesystem.

## 25. A byte budget end to end

Status: not started
Depends on: 4

One budget covers the diff Coral captures, the request it assembles, and the text it publishes. A change over the budget, or one whose request does not fit the model's context window, is declined rather than reviewed in part.

- The diff's ceiling is enforced where `git` output is captured, because the pull-request gate counts files and lines and one very long line passes it.
- A `main` push is bounded the same way a pull request is.
- Publication ceilings live in `coral/schema.py`, where structure originates, and a review crossing one fails rather than posting a cut body.

Done when: a real pull request whose diff crosses the byte budget is declined with the reason on it, a review whose text crosses a publication ceiling fails rather than posting a cut body, and a model whose context window cannot hold the assembled request stops the run before the first model call.

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

## 23. Give referenced issue context to review agents

Status: not started
Depends on: 21

Before reviewing a pull request or a main-branch range, Coral reads each referenced GitHub issue
and gives both agents the same fixed context. References come from the pull request's manually and
closing-linked issues, its title and body, and every commit message in the reviewed range.

- A reference is an ordinary GitHub issue, not a pull request. It can name this repository or another repository that the job token can read.
- GitHub's native issue-reference forms count. Pull-request discussion and repository custom autolinks do not add issue context.
- The context holds an issue's repository, number, state, title, and body. It does not read issue comments.
- The number of references, each body, and the total context are bounded. The request says what the bound or an unavailable issue left out.
- Resolve fetches the context before the review, and it crosses to review as an artifact. The agents receive no GitHub credential.

Done when: a real pull-request review reads both a linked issue and one named only in a commit message, a real main-push review reads an issue named by a commit in its range, both agents receive the same context, unavailable and excess references leave an explicit bounded notice, and no agent container carries a GitHub token.

## 26. Automatic pull-request review from pull_request_target

Status: not started
Depends on: 24

Automatic pull-request review moves from the `pull_request` trigger to `pull_request_target`, so the workflow that receives the OpenRouter and GitHub secrets always runs from the default branch rather than from the pull request's own merge branch. A same-repository branch that edits `review.yml` no longer changes how its own pull request is reviewed.

- The event's pinned head SHA is what's checked out, checked against, and posted against, the same pattern a `main` push already uses; the ref itself is never checked out.
- Safe only once item 24 lands: `pull_request_target` still runs the pull request's diff through the review, and doing that outside the container while secrets are present would be a privileged execution path.
- `pull_request_target` hands every secret to a fork's pull request too, unlike `pull_request`. The existing repository-id fork gate in `resolve.py`, not the current absence of secrets on a fork-triggered run, has to be what still declines a fork's pull request.
- `/coral`'s manual-comment path is unaffected; only the automatic pull-request trigger's event type and checkout ref change.

Done when: a real pull request from a same-repository branch that edits `review.yml` is reviewed under the default branch's version of it, not its own; the review still anchors against and posts against the pull request's actual head commit; and a real fork's pull request is still declined before any secret is touched.

## Not On This Roadmap

Named so nobody has to guess. Everything under "Out Of Scope" in `.agents/docs/functional-requirements.md` also applies.

- A second forge or model provider. The swappable backend and the single model-client construction site are as far as this goes.
- Any store of past reviews. Coral reads the pull request.
- GitHub Enterprise Server. The `$/` reference does not exist there; supporting it means a second packaging answer, not attempted.
