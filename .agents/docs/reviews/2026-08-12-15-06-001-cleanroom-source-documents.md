# Review: cleanroom source documents

A review of the implementation of `.agents/docs/plans/2026-08-12-14-15-001-cleanroom-source-documents.md`: the rewritten functional requirements, the runner research record, the replacement roadmap, and the ancillary edits to `AGENTS.md`, `architecture.md`, and `README.md`.

Mechanical checks pass. `git diff --check` is clean. Word counts: roadmap 2,560 of 3,500; architecture 1,443 of 1,500; requirements and research are exempt. No authoritative document references roadmap items 18, 19, 23, 25, or 26, deleted technical requirements, or deleted research paths. The working ledgers are gone. The diff touches documentation only and leaves the item 23 plan untouched. The research file follows the artifact naming convention, and `AGENTS.md` now registers `research/` as a document home, exempts it from the ceiling, and extends the record rules to it.

The plan's six named requirement gaps are all settled: referenced-issue context, end-to-end byte limits in both modes replacing the no-backstop statement, `pull_request_target` with fork rejection, Actions-log diagnosability kept as promised behavior, every post-review correction (marker attribution, conversation bounds, anchor fallback, cost enforcement, main duplicate handling, complete file-tool isolation), and the broker and microVM named out of scope. The roadmap mentions no Python implementation, history, or oracle; items 18 and 19 appear only under Not On This Roadmap; item 24's file-tool boundary is inside item 7 rather than a retrofit; bounds are introduced with the inputs they bound; the walking skeleton avoids executing reviewed code before isolation exists. The requirements-to-roadmap direction is nearly complete: walking every requirements bullet, each is proven by a done condition, with the one exception in finding 2.

Each finding carries a disposition, in the sense the earlier reviews use.

## 1. Roadmap items 8, 10, and 13 promise credential and configuration behavior no handoff document owns

Disposition: needs a decision — most likely a new group of requirements bullets.

The plan's roadmap coverage review requires every promised capability to implement product behavior in the requirements or a platform constraint in the research. Item 8 fails that test: two exclusive provider-credential modes, a management credential minting a capped expiring key, ciphertext-only transfer, and no-cleartext-anywhere are in neither document. Item 10's configurable model, exact-name-not-alias rule, and configurable time budget, and item 13's cap agreement between management-mode provider authority and local accounting, are likewise unowned; the research record supports only the placement conclusion that installation configuration lives in the default-branch caller.

The contradiction is sharper than a missing assignment. The requirements' out-of-scope section excludes "a … configuration mechanism not named above", and the requirements name none, so a cleanroom agent reading the two documents together sees the roadmap building what the requirements exclude. The requirements preamble also claims security properties an installation can inspect, and the minted-key lifecycle is exactly such a property, already product behavior in the current build (`README.md` and `development.md` document both key modes).

The likely fix is a short requirements group for installation configuration and provider credentials: where configuration lives, that the model, budgets, and credential mode are chosen there, the two exclusive modes, and the minted key's cap, expiry, and non-appearance in any log, output, artifact, or container. Alternatively, narrow the out-of-scope bullet and accept the roadmap as the owner — but that leaves a security property outside the document that claims to be the whole product.

## 2. One requirements bullet has no owning done condition

Disposition: trivially fixable.

"It never runs the full suite on its own initiative" is proven by no roadmap done condition. Item 11 owns reviewer judgment and its done conditions are the natural home — the planted-defect runs can check the run log for full-suite invocations. As written, the plan's requirement that every in-scope bullet be owned by a done condition is not met for this bullet.

## 3. The research record cannot satisfy the plan's handoff exclusion as written

Disposition: needs a decision, and the tension is in the plan, not the extraction.

The plan requires the research record to cite repository commits for observed live checks, and the record does, correctly. The same plan's handoff paragraph says the cleanroom handoff excludes commit identifiers and any statement that another Coral implementation exists — yet the record is one of the three handoff documents and necessarily contains both ("Commit `52912cd…` split Coral into resolve, review, and publish jobs"; "during Coral's build"). The roadmap and requirements are clean; only the research record reveals a prior build. Either the exclusion clause tolerates the research record's evidence trail, or the record needs a redacted handoff variant. Nothing in the record needs to change until that is decided.

## 4. Architecture points its remediation at the rebuild's roadmap

Disposition: needs a decision, probably accept.

`architecture.md` describes the current Python build and now says the diff byte bound and the `pull_request_target` move live in roadmap items — but those items build the TypeScript rebuild, not fixes to this code. The sentences read as if the current build will gain those fixes. If the Python build is frozen in favor of the rebuild, saying so once in the architecture document would make both sentences honest; if the pointers are meant only as "the plan of record handles this", the current text is tolerable.
