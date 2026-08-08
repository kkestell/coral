# Roadmap

The order the work happens in. A sequence, not a schedule: one item is one plan, one build, and one review, and those artifacts carry the item's number in their filenames.

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

## Not On This Roadmap

Named so nobody has to guess. Everything under "Out Of Scope" in `.agents/docs/functional-requirements.md` also applies.

- A second forge or model provider. The swappable backend and the single model-client construction site are as far as this goes.
- Any store of past reviews. Coral reads the pull request.
- GitHub Enterprise Server. The `$/` reference does not exist there; supporting it means a second packaging answer, not attempted.
