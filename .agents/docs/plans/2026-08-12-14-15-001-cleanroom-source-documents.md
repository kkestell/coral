# Prepare the cleanroom source documents

## Goal

Produce the three documents that define the TypeScript rebuild before its repository exists:

1. `.agents/docs/functional-requirements.md`, complete and internally consistent.
2. `.agents/docs/research/<timestamp>-github-actions-runner-contract.md`, extracting the GitHub
   Actions knowledge already established by this build.
3. `.agents/docs/roadmap.md`, rewritten as a not-started roadmap for a feature-complete TypeScript
   implementation.

The execution order is requirements, runner-knowledge extraction, then roadmap. The roadmap is
written last because its item boundaries and dependency order must account for both product behavior
and the platform constraints that made the existing build change course.

The existing implementation, history, plans, reviews, and live-check commits are evidence for the
author of these documents. They are not copied into the cleanroom repository or disclosed to its
implementation agents.

## Evidence

Read the whole current document that owns each subject before changing it. Use these sources:

- The current functional requirements, architecture, roadmap, development guide, testing guide,
  README, workflows, actions, source, and tests.
- Every historical version of `functional-requirements.md`, `roadmap.md`,
  `technical-requirements.md`, and the deleted files under `.agents/docs/research/`.
- Plans for roadmap items 1 through 24, including the uncommitted item 23 plan; the current roadmap
  text for items 25 and 26; and both code reviews.
- The commits that built, corrected, live-checked, and verified each roadmap item. Temporary probe
  commits and their reverts are evidence of the observed result, not changes to restore.
- The GitHub sources and live observations already cited by the deleted research, plans, and current
  documents.

Do not browse for new platform facts. If the sources disagree or a claim has no surviving evidence,
label it unresolved while drafting and settle only what can be settled from the repository. A fact
whose volatility matters is marked for revalidation in the research document rather than silently
refreshed.

## Working ledgers

Keep two temporary ledgers outside `.agents/docs/`. They are drafting tools and are deleted after the
documents pass their checks.

The behavior ledger has one row per candidate requirement:

- Behavior in observable terms.
- Evidence and the last commit that changed it.
- Whether it is implemented, planned, corrected after review, or deliberately out of scope.
- Disposition: keep, revise, add, combine, or exclude.
- The final requirements heading and bullet that owns it.

The roadmap ledger has one row per historical item 1 through 26:

- Capability built or proposed.
- Actual prerequisites discovered during implementation.
- Corrections and live-check lessons that constrain a rebuild.
- Final disposition: roadmap item, merged into another item, split across items, or out of scope.
- The new roadmap item or items that carry it.

The ledgers may use stable labels while drafting. Those labels do not enter the requirements,
roadmap, code, or cleanroom repository.

## Functional requirements audit

Treat intended product behavior as the authority. Current code proves behavior and exposes omissions,
but an accidental implementation choice does not become a requirement merely because it exists.
An unfinished roadmap item becomes a requirement only when it is part of the intended cleanroom
product.

Read the evidence in passes rather than file order:

1. Inventory every current requirements bullet into the behavior ledger.
2. Walk historical roadmap items 1 through 26 and add behavior the current requirements do not own.
3. Walk the two reviews and every corrective commit after the item builds; add the behavior whose
   absence caused the correction.
4. Walk the current workflow, source, and tests by user-visible path: automatic pull request,
   requested pull request, main push, successful review, empty review, declined review, failed
   review, concurrent review, and over-budget review.
5. Walk the old technical requirements and research for platform or security properties that a
   clean implementation must preserve rather than rediscover.
6. Resolve duplicate or conflicting candidates, then edit the requirements once from the settled
   ledger.

The audit must explicitly settle these known gaps:

- Add referenced-issue context from item 23, including its sources, bounds, identical reviewer and
  verifier context, unreadable-reference notice, and treatment as untrusted information rather than
  instruction.
- Add the end-to-end byte limits from item 25. Replace the present statement that a main push has no
  size backstop; both review modes must refuse a request that cannot be captured, assembled, sent,
  or published whole.
- Require automatic pull-request delivery through `pull_request_target`, with the workflow sourced
  from the base repository's default branch, the exact head SHA treated as untrusted input, and fork
  rejection before the run can expose credentials or privileged execution. The mechanism is part of
  the requirement because substituting `pull_request` loses the required security property.
- Decide whether readable Actions-log progress is promised behavior. Keep it when it is necessary to
  understand a live run; otherwise leave its format as an implementation concern without losing the
  requirement that the run be diagnosable.
- Preserve the corrected behavior found after code review: marker attribution, conversation bounds,
  line-anchor fallback, cost and limit enforcement, main-push duplicate handling, and isolation of
  every agent-controlled file and shell operation.
- Put the external credential broker and microVM shell explicitly out of scope. They were speculative
  optional hardening, not dependencies of the feature-complete rebuild.

Keep the requirements implementation-language neutral. A GitHub mechanism may be named when it is
the contract that supplies required behavior; Python modules, DeepAgents control points, and current
file layouts never appear. Each bullet states one observable behavior or one security property and
has one home. Do not add requirement identifiers, history notes, source citations, or a traceability
appendix.

### Requirements checks

- Every behavior-ledger row has a final disposition, and every `keep`, `revise`, or `add` row points
  to one final bullet.
- Each final bullet can be checked by deterministic tests, a real GitHub run, or inspection of a
  named security boundary.
- Trigger, review subject, agent capabilities, output, failure, and out-of-scope behavior contain no
  contradictions across pull-request and main-push modes.
- No final bullet describes TypeScript structure or repeats a GitHub explanation owned by research.

## GitHub Actions runner research extraction

Write one dated research record under `.agents/docs/research/`. This is extraction and synthesis of
work already done, not a new research project. Cite repository commits for observed live checks and
retain the upstream source URLs, versions, SHAs, and read dates from the old research wherever they
survive.

Organize the record by platform question:

- Which revision of a workflow GitHub runs for `pull_request`, `pull_request_target`, comment, push,
  reusable-workflow, and local-action paths.
- What the caller and reusable workflow each own: triggers, version pin, permissions, concurrency,
  inputs, and secrets.
- What a job boundary guarantees about runners, filesystems, processes, environments, tokens, and
  state transfer; when to use outputs and when to use artifacts.
- How `GITHUB_TOKEN` permissions compose, why unspecified permissions become `none`, which Coral API
  operations need which permissions, when the token expires, and which token-authored events do not
  trigger another workflow.
- How checkout refs, full history, `persist-credentials`, `GITHUB_WORKSPACE`, `RUNNER_TEMP`, action
  directories, and caches behave.
- How concurrency queues and cancellation behave when several requests address one pull request.
- What is and is not isolated by a Docker container on a hosted runner, including the Docker socket,
  process and filesystem namespaces, bind mounts, the hosted toolcache, credentials, command
  timeouts, and agent file tools.
- How job and command timeouts, failure conditions, skipped report steps, artifacts, and cancelled
  runs affect what can still be published.

For each claim, identify its evidence class in prose:

- Documented contract: guaranteed by a cited GitHub or runner source.
- Observed behavior: measured by a dated query or live run and not promised by documentation.
- Coral conclusion: a design constraint derived from one or more facts.
- Drift-sensitive fact: image contents, tool versions, runner version, undocumented ordering, or
  another observation the cleanroom build must revalidate before relying on it.

Do not turn the research record into a second architecture or requirements document. It explains
the platform evidence and failure modes. Required product behavior remains in functional
requirements; implementation order remains in the roadmap; TypeScript module layout remains for a
later architecture document.

### Research checks

- Every Actions-specific reason preserved in the requirements or roadmap is supported by a research
  claim or is explicitly marked unresolved.
- Every observation says where and when it was observed; every upstream claim retains a source.
- Current conclusions do not depend on deleted technical-requirement numbers or historical roadmap
  numbers.
- The record contains no secrets, transient run URLs requiring private access, or Python source
  instructions that would steer the cleanroom implementation.

## Hindsight roadmap

Replace `.agents/docs/roadmap.md`; do not restore an old version and edit it down. The new document is
the initial roadmap for the TypeScript build, so every item starts `not started`. It may state that
the project is TypeScript, but it must not mention the Python implementation, its history, or the
existence of an oracle.

Choose granularity from the work rather than a target item count. One item is one capability that an
agent can plan, implement, review, and verify independently. Keep two historical items separate when
they have distinct failure surfaces or live checks; combine them only when they share a contract,
implementation boundary, and done condition. Split an old item when hindsight shows it hid multiple
independent boundaries.

Use the roadmap ledger to preserve all historical capability:

- Items 1 through 17 and 20 through 22 remain evidence for required capability and safe dependency
  order.
- Item 23, referenced issues; item 25, end-to-end bytes; and item 26,
  `pull_request_target`, are part of the feature-complete target even though they were unfinished.
- Items 18 and 19, the external broker and microVM, are absent from build items and named only under
  `Not On This Roadmap`.
- Item 24's complete file-tool boundary is part of the initial isolation design, not a late retrofit.

Order items by prerequisites learned from the first build. Establish a real GitHub walking skeleton
early. Pin immutable review inputs before model work. Put all agent-controlled shell and file access
behind the credential-free isolation boundary before processing untrusted code under
`pull_request_target`. Introduce bounds when each input or output first exists rather than as a final
hardening pass. Give failure reporting, independent finding verification, concurrency, credential
handoffs, and live checks their own item when each has an independent acceptance surface.

Each item contains only:

- A capability-oriented title.
- `Status: not started` and its item dependencies.
- The outcome it creates and the few platform or product constraints later work must build against.
- A done condition expressed as observed behavior, including the real GitHub run needed to prove
  claims the unit suite cannot prove.

Do not prescribe TypeScript modules, framework APIs, class names, test files, implementation steps,
or numeric constants whose selection belongs in the item's plan. Do not repeat functional
requirements verbatim. Point to the relevant document heading where a dependency needs more than a
clause.

### Roadmap coverage review

After drafting, walk in both directions:

1. Requirements to roadmap: assign every in-scope functional-requirements bullet to the first item
   whose done condition proves it. Add or change items until none are unowned.
2. Roadmap to requirements or research: every promised capability must implement product behavior
   in the requirements or a platform constraint in the research. Remove accidental new scope.
3. Historical ledger to roadmap: every item 1 through 26 has a disposition, and every correction or
   live-check lesson that would change build order appears in a dependency, constraint, or done
   condition.

Delete the coverage assignments with the ledgers. The final roadmap remains readable without a
numbering system shared with the requirements.

## Consistency sweep

Read every current authoritative document after the three outputs are complete. Make only the
ancillary edits required to keep them true: remove stale references to old roadmap item numbers,
point platform evidence at the research record, and move a lasting conclusion into the document that
owns it. Do not rewrite the current Python architecture as a TypeScript design; that design belongs
to the future repository and its first roadmap item.

The cleanroom handoff later consists only of the finalized functional requirements, runner research,
and roadmap, plus new repository instructions written for the employer workflow. It excludes this
plan, every working ledger, current architecture and development documents, source, tests, reviews,
historical artifacts, commit identifiers, and any statement that another Coral implementation
exists.

## Validation

1. Run `git diff --check` and the documentation word-count checks in `AGENTS.md`.
2. Search all authoritative documents for stale references to roadmap items 18, 19, 23, 25, and 26,
   deleted technical requirements, and deleted research paths.
3. Read the functional requirements once as a product spec with no implementation context.
4. Read the runner record once as evidence with no Coral source context.
5. Read the roadmap once as the only implementation sequence available to a TypeScript agent.
6. Complete both ledger-direction checks, then delete the temporary ledgers.
7. Inspect the final diff and confirm it changes documentation only, does not alter the uncommitted
   item 23 plan, and contains no cleanroom implementation code.

The work is complete when the three documents can be copied to an empty repository and an agent can
plan every roadmap item without access to this repository, while every functional requirement is
owned by a roadmap done condition and every Actions constraint that affects the build is supported by
the research record.

## Not doing

- No TypeScript repository, architecture, dependencies, framework choice, or source code.
- No implementation of current roadmap items 23, 25, or 26 in Python.
- No new GitHub experiment, documentation survey, or live check unless a separate task authorizes
  one after extraction finds an evidence gap.
- No external credential broker or microVM roadmap track.
- No permanent requirement identifiers, traceability matrix, restoration of deleted roadmap prose,
  or history narrative in a cleanroom document.
