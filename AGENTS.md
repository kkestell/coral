# AGENTS.md

THIS FILE MUST BE KEPT UP TO DATE AT ALL TIMES

Coral is a proof-of-concept code review agent, kept deliberately simple. When a pull request is opened or marked ready for review, or when somebody asks, Coral clones the repository and reviews the change, running individual tests of its own choosing along the way, and leaves its findings as comments on the pull request. It runs as a GitHub Actions workflow, written in Python on DeepAgents, with models reached through OpenRouter.

## Documentation

This file is an index. Each document below is the authority on its subject — read the one that covers what you are about to do, and do not assume its contents from the description here.

- `.agents/docs/functional-requirements.md` — what Coral does, as behavior someone could watch happen, and what is deliberately out of scope. Read before planning a change, to know whether the change is one Coral is meant to make.
- `.agents/docs/technical-requirements.md` — what Coral is built on, the platform limits the design lives inside, and the decisions still open. Read alongside the architecture document before planning anything that touches deployment or the agent's access to the checkout.
- `.agents/docs/roadmap.md` — the order the work happens in, what each item depends on, and which one is current. Read before starting work, to know whether the ground it stands on exists yet.
- `.agents/docs/architecture.md` — the stack, what lives where, how the parts fit together, and the invariants that hold across the codebase. Read before planning a change, to put it where the code already expects it.
- `.agents/docs/development.md` — prerequisites, setup, the build and run and check commands, environment variables, and local services. Read before running anything.
- `.agents/docs/testing.md` — where the tests live, how to run one without running all of them, and what a new test is expected to look like. Read before writing or running tests.
- `.agents/docs/code-style.md` — the conventions this code follows and the rules this project has chosen for itself, including the ones no linter checks. Read before writing code.

The `FR-*` and `TR-*` numbers are internal to the documents above. They never appear in code, comments, or commit messages.

## Artifacts

The ox stages write into `.agents/docs/`: `research/` for how a problem is solved elsewhere, `plans/` for a settled change, `builds/` for what actually landed, `reviews/` for findings against a build. Read the relevant artifact before repeating work someone already did.

One roadmap item has one plan, one set of build notes, and one review, and all three share a filename ending in that item's number. Research is separate: it is named for its question, and a plan uses any number of research documents or none.
