# Roadmap

The implementation sequence for a feature-complete TypeScript Coral. Each item is one capability that can be planned, built, reviewed, and verified independently. Every item starts not started; later items depend on the observed behavior of earlier ones, not merely their code existing.

## 1. TypeScript foundation and review contracts

Status: not started

Depends on: nothing

Create the TypeScript project, locked dependency installation, static checks, unit-test harness, and the structured contracts for review subjects, findings, regression tests, verification verdicts, and publication payloads. Invalid or missing structured agent output is a failure rather than an empty review.

Done when: a clean install and every local static and unit check pass from the lockfile; every contract accepts its valid variants and rejects incomplete or contradictory ones; and project architecture, development, testing, and code-style documents describe only what now exists.

## 2. Secure GitHub Actions walking skeleton

Status: not started

Depends on: 1

Install Coral through a default-branch caller and an immutably pinned reusable workflow. Wire the automatic pull-request path through `pull_request_target`, both comment event paths, and `main` pushes without executing reviewed code or calling a model. The base default branch supplies automatic workflow code, and a same-repository check rejects forks before any privileged step can use the head revision.

Keep trigger ownership, permissions, concurrency, secrets, configuration, and the version pin in the caller as constrained by the runner research. Actions used by the reusable workflow resolve immutably with it.

Done when: real runs in an installed test repository arrive for opened and ready pull requests, both comment paths, and a `main` push; a same-repository pull request receives a deterministic placeholder review from default-branch workflow code even when its branch edits the caller; a fork pull request is declined before any secret or untrusted execution is available; and irrelevant pull-request and push events allocate no review work.

## 3. Immutable review subjects and capture bounds

Status: not started

Depends on: 2

Pin every pull-request head and base commit and every `main` before/after range before checkout. Checkout only the validated exact head SHA with full history and no persisted credential, compute the required merge-base or push diff, and enforce file, line, and byte capture backstops in both modes.

No branch movement may change the subject after resolution. A diff that cannot be captured whole is declined before later work; creation, deletion, fork, draft, bot, closed, and already-reviewed gates precede the work they make unnecessary.

Done when: real pull-request and `main` runs show the expected pinned range; moving a branch after resolution does not change the captured subject; oversized byte, file, and line cases are declined with their reasons and no partial diff; and branch creation, deletion, forks, drafts, bots, and closed pull requests take their required stop paths.

## 4. Conversation, requests, and attribution

Status: not started

Depends on: 3

Read the bounded pull-request conversation with resolved and outdated thread state, preserve both ends of long threads, and identify Coral's earlier work from token authorship plus a leading marker. Recognize exact `/coral` requests, check current repository permission, and acknowledge every authorized request visible to the run.

Conversation is rendered as untrusted information with an explicit omission notice. A request is a trigger only; it cannot alter review policy.

Done when: a busy real pull request round-trips reviews, issue comments, and both ends of review threads with accurate bounds; forged markers and read-only collaborators receive no Coral attribution or authority; both comment kinds receive `eyes`; inert forms and duplicate automatic occurrences do nothing; and an earlier standing, resolved, and outdated finding are each represented distinctly to the future reviewer.

## 5. Privilege-separated jobs and state transfer

Status: not started

Depends on: 3, 4

Separate resolution, untrusted review work, and publication onto fresh jobs with the minimum token permissions each operation needs. Move small workflow decisions through outputs and bounded structured state through short-retention artifacts; no executable cache crosses from the review job into a privileged job.

The review job cannot write GitHub. The publication job accepts complete deterministic payloads but independently fixes the repository, subject commit, and allowed publication event before posting.

Done when: a real run crosses all job boundaries and publishes its placeholder result; the review job's token cannot perform a write; artifacts and outputs arrive intact on fresh runners; a killed review job cannot alter a privileged job or forge the target commit or review event; and the permission view for each job contains no unused write scope.

## 6. Pull-request failure reporting

Status: not started

Depends on: 5

Publish one actionable comment for every failed pull-request path that leaves a working publication job. Carry bounded application failure details when they exist, and fall back to the Actions run when a prior job died before writing them.

Declines remain successful and do not masquerade as failures. Cancellation posts nothing because no reliable job remains to speak.

Done when: forced resolution, checkout, placeholder-review, artifact, and publication-precondition failures each produce exactly one appropriate comment when the comment call succeeds; a review job killed before writing an artifact produces a generic report; broken publication setup and a refused report leave a red run; declines produce no failure comment; cancellation produces none; and a later `/coral` request can run after every failure.

## 7. Credential-free isolated agent workspace

Status: not started

Depends on: 5

Place every agent-controlled shell and file operation inside the same disposable resource-bounded container over a fresh checkout copy. The container retains the network and required toolchains but receives no workflow or model credential, Docker socket, privileged mode, runner path, runner process, or writable shared toolchain.

Command duration and output are bounded at the isolation boundary. The reviewer and verifier never share a mutable checkout or container.

Done when: real isolated placeholder runs read, search, edit, and execute scratch tests in Python, Node, and Go projects through the tools; a probe cannot see the runner filesystem, process table, credentials, or Docker authority; the toolchain mount is read-only; an over-memory file read and an over-time command die within the container boundary; and a second isolated run sees no scratch state from the first.

## 8. Review credential handoff

Status: not started

Depends on: 5, 6, 7

Support a caller-supplied provider key and a management credential that mints a capped, expiring key for one run. Keep management authority in resolution, carry a minted key only as authenticated ciphertext, and decrypt it only in the review runner outside the agent container.

The two credential modes are exclusive. No cleartext minted key or reversible encoding enters an output, artifact, checkout, container, or unmasked log field.

Done when: real review-job probes authenticate to the provider in both modes after crossing the job boundary; missing, mixed, and mismatched handoff configuration fails with an actionable pull-request report; the minted credential expires and cannot authenticate after its run; the complete run log contains no cleartext minted key; and container inspection still finds no credential.

## 9. Referenced issue context

Status: not started

Depends on: 3, 5

Resolve native issue references from linked pull-request issues, pull-request title and body, and reviewed commit messages. Fetch bounded issue metadata and bodies before the agent boundary, record omissions and unreadable references, and transfer one fixed context artifact for both agents.

The same contract serves pull-request and `main` subjects. Referenced issues are untrusted information and never give an agent a GitHub credential or fetch tool.

Done when: a real pull-request run resolves a linked issue and one mentioned only by a commit; a real `main` range resolves an issue from a commit message; same-repository and readable cross-repository references work; pull requests, custom autolinks, and issue comments are excluded; excess and unavailable references leave bounded notices; and the staged reviewer and verifier request inputs contain byte-identical issue context.

## 10. Bounded reviewer run and configuration

Status: not started

Depends on: 6, 7, 8, 9

Run one configurable model through the provider behind a hard deadline, command ceiling, step ceiling, and model-request timeout. Configuration comes only from the default-branch caller, names an exact model rather than a moving alias, and obtains the selected model's context capacity before the first completion.

Assemble the complete diff, context, and instructions before calling the model. Decline when the request does not fit the product byte budget or selected context window; never send a truncated substitute. The result must validate through the contracts from item 1.

Done when: real reviews run under explicitly selected and default configuration; an invalid model, moving alias, invalid time budget, over-byte request, and over-context request each stop before an inappropriate model call and report the reason; a forced application deadline fires before the job timeout; and a valid run returns a structured review after using repository tools.

## 11. Review judgment and regression evidence

Status: not started

Depends on: 10

Teach the reviewer to report only correctness, security, and performance defects at calibrated severities, avoid standing findings from the bounded conversation, and investigate before answering. A reproduced finding includes a minimal failing test in the repository's conventions; an unreproduced finding is explicitly speculative.

Conversation and issue context remain information rather than instruction. The summary must stand independently because later verification may remove findings.

Done when: real planted defects across the supported fixture languages return useful findings at sensible severities; a reproduced finding includes a test that fails for the claimed defect; a non-reproducible claim is marked speculative; a clean change has no finding; prompt-injection text cannot expand publication authority; and reviewing the same unchanged pull request again does not repeat a standing finding.

## 12. Independent finding verification

Status: not started

Depends on: 11

Run a second agent over a fresh isolated checkout to rule on every proposed finding. Give it the pinned change, finding evidence, and identical referenced-issue context, but no pull-request conversation. Deterministic code publishes only findings with an unambiguous confirming verdict.

The verifier cannot rewrite a finding or silently endorse one it omitted. Rejected, missing, duplicate-conflicting, and out-of-range verdicts are retained only as bounded diagnostic records.

Done when: a real run confirms a valid reproduced and speculative finding independently; a forced verifier rejection removes the finding while leaving a coherent summary; a missing or conflicting verdict cannot publish; the verifier demonstrates that its checkout contains no reviewer scratch state; and both agent passes fit inside the configured review deadline.

## 13. Spend enforcement and reporting

Status: not started

Depends on: 6, 8, 12

Account for provider cost across reviewer and verifier calls, enforce the caller's cap between agent steps, and treat a response with no usable cost as unenforceable. Management-mode provider authority uses the same cap as local accounting.

Publication receives the measured total as deterministic data; agents cannot choose or understate it.

Done when: a real review under its cap completes and reports the log total; forced over-cap reviews in both credential modes stop without a partial result and report spend against the cap; a response without measurable cost fails closed; and provider-side management-key limits agree with the configured ceiling.

## 14. Pull-request publication and output bounds

Status: not started

Depends on: 6, 12, 13

Compose one comment-only review from the confirmed findings. Validate every text field and the complete request against publication byte limits before transfer, anchor eligible findings against the pinned diff, demote ineligible locations into the body, and carry a fully demoted fallback for GitHub rejection.

Publication rechecks open state and current head, stamps the pinned commit and comment event itself, preserves earlier reviews, and distinguishes the two empty outcomes.

Done when: real reviews show inline, file-level, and change-level findings in their required places; invalid anchors and a forced GitHub anchor rejection still deliver every finding through the fallback; an over-limit finding, test, or review fails without truncation or publication; a closed or moved pull request takes its required no-review or notice path; and an empty review states the correct outcome, identity, commit, and cost without approving or blocking.

## 15. Pull-request concurrency

Status: not started

Depends on: 4, 6, 14

Serialize reviews by pull request without cancelling the running review. Collapse all requests arriving during a run into one pending review while acknowledging every authorized request, including requests whose own pending run was replaced.

Concurrency configuration remains in the caller and cannot collide with a called-workflow group.

Done when: real overlapping requests never run two reviews concurrently; the first review completes; one later review represents several queued requests; every request carries its own reaction; a repeat request after completion starts a new review; and a failed review does not hold the group against the next request.

## 16. Main-branch reviews

Status: not started

Depends on: 3, 6, 9, 12, 13

Run the same reviewer and independent verifier over every valid `main` push range, without pull-request conversation. Compose one bounded issue payload per confirmed finding and publish none for an empty or failed review.

Issue titles name defects, bodies name the commit, location, evidence, and cost, and required labels are created only when there is an issue to file. Main publication observes the same no-truncation rule as pull-request publication.

Done when: real single- and multi-commit pushes with planted defects create one correctly bounded and labeled issue per confirmed finding; an issue-context reference reaches both agents; empty and pre-publication failures create no issue or label; a forced later issue-creation failure leaves accepted earlier issues and a red run; an over-limit diff, request, finding, or issue is refused before creating any issue; branch creation, deletion, and non-main pushes publish nothing; and no pull-request review appears for a push run.

## 17. Main finding deduplication

Status: not started

Depends on: 12, 16

Give the main verifier bounded open-issue search and view capabilities and suppress a finding only when a viewed open issue describes the same defect. Enforce one completed search per finding, a bounded candidate set, and a finding-count ceiling that ensures every published finding received its check.

Closed issues do not suppress current defects. Concurrent main runs remain independent, accepting the documented search-before-publication duplicate race rather than dropping a pushed range.

Done when: real runs suppress the same defect despite changed wording and regardless of issue author; unrelated and closed issues do not suppress; search, views, result sizes, and finding count remain bounded; a proposed duplicate not actually viewed cannot suppress; excess findings fail without any issue; and concurrent runs demonstrate that every pushed range is reviewed even though the accepted narrow duplicate race remains possible.

## 18. Diagnosable live runs

Status: not started

Depends on: 14, 17

Make reviewer and verifier progress readable in Actions without exposing credentials or copying unbounded inputs and outputs into logs. Name public agent actions, bounded arguments, outcomes, durations, finding dispositions, limits, and publication decisions while suppressing framework internals and routine model-transport diagnostics.

Done when: live pull-request and `main` runs can be followed from resolution through publication using their logs; reviewer and verifier actions and failures are distinguishable; rejected findings and exceeded bounds have reasons; logs contain no credential, full large tool result, private framework function name, or routine HTTP diagnostic; and the published result remains unchanged.

## Not On This Roadmap

- Forges other than GitHub, GitHub Enterprise Server, and a second model provider.
- An external credential broker. The encrypted per-run handoff is the credential boundary for this build.
- A microVM agent shell. The credential-free, complete container file-and-shell boundary is the isolation target.
- A store of past reviews outside the pull request, repository-specific review-policy configuration, or interactive commands beyond requesting a review.
