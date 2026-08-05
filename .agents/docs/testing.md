# Testing

THIS FILE MUST BE KEPT UP TO DATE AT ALL TIMES

A scaffold, not a cage. Drop sections that don't apply and expand the ones that matter.

How this project tests itself: where the tests live, how to run them, and what a new test is expected to look like. The full-suite commands live in `.agents/docs/development.md`; this document covers everything narrower than that.

Coral runs the tests of the repository under review. Those are not this project's tests, and nothing about them belongs in this document.

## Frameworks and Tools

{The test runner, the assertion library, and anything that supports them — a mocking library, a snapshot tool, a coverage tool, a container harness for integration tests. One line each.}

- {Tool} — {what it is used for}

## Layout

{Where tests live and how that maps onto the code under test: alongside the source, in a parallel tree, split by kind. Give the convention a new file is expected to follow, including the naming pattern.}

- `{path/}` — {what is tested here}

## Kinds of Test

{The tiers this project actually has, and what each is for. Say where the line between them falls — what a unit test is allowed to touch, what earns an integration test, what only the end-to-end suite covers. Drop the tiers the project does not have rather than describing them aspirationally.}

- **{Kind}** — {what it covers, what it is allowed to touch, where it lives}

## Running Tests

{Narrower invocations than the full suite: one file, one test by name, one tier, with output shown, in a loop on change. The exact flags, since this is the section a reader copies from.}

- {What you want to run} — `{command}`

## Fixtures and Test Data

{How a test gets the data it needs — factories, builders, fixture files, a seeded database, a golden-file directory — and where those live. Say what a new test should reuse instead of building its own.}

## Writing a New Test

{What this project expects of a test that is being added: the structure it follows, what gets asserted, how much setup belongs in the test body, what may be mocked and what must be real. Written as the rules a reviewer would hold a new test to.}

## Not Covered

{Parts of the system the suite does not exercise, and why — no harness for it, needs credentials, checked by hand. Worth recording: it tells a later plan where a change carries risk the tests will not catch.}

- {Area} — {why}
