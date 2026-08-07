# AGENTS.md

Coral is a proof-of-concept code review agent, kept deliberately simple. When a pull request is opened or marked ready for review, or when somebody asks, Coral clones the repository and reviews the change, running individual tests of its own choosing along the way, and leaves its findings as comments on the pull request. It runs as a GitHub Actions workflow, written in Python on DeepAgents, with models reached through OpenRouter.

## Documentation

Each document owns a subject and is the only place that subject is written down. Read the one covering what you are about to do. Do not infer its contents from this list.

- `.agents/docs/functional-requirements.md` — what Coral does, why that behavior, and what is out of scope.
- `.agents/docs/architecture.md` — how Coral is built: the stack, where every part lives, how the parts fit together, the platform limits, the rules that hold across the codebase, the decisions still open, and every reason a thing is built the way it is.
- `.agents/docs/roadmap.md` — what each item builds, what it depends on, its status, and its done condition.
- `.agents/docs/development.md` — prerequisites, setup, commands, environment variables, and gotchas.
- `.agents/docs/testing.md` — where the tests live, how to run a subset, what a new test looks like, and the live checks.
- `.agents/docs/code-style.md` — the conventions this code follows, including the ones no linter checks.
- `README.md` — how somebody outside the project installs and uses Coral. Nothing under `.agents/docs/` describes installation or use.

## Where Things Go

One fact, one home. A second copy will disagree with the first, and nothing will catch which one went stale.

Pick the home by the question the fact answers. What does Coral do, and why that? Functional requirements. Why is it built this way, and what may not change? Architecture. What gets built next, and when is it done? Roadmap. What do I type? Development. How do I check it? Testing. How do I write this Python? Code style. How do I install Coral? README. Why is this line like this? A comment on that line.

State a fact you do not own in one clause. Never explain it. Writing "because" about something another document owns means stopping and pointing at that document instead.

Never summarize another document. No recap sections, no restated rules, no preamble listing what the other documents hold.

Never label anything for citation. No requirement numbers, no invariant identifiers, no scheme that exists to be referred to from elsewhere. Point at a document and a heading.

A fact with no home does not get written down. Do not add a section for it. Do not add a document.

A comment explains the line beneath it. If it would still be true with that code deleted, it belongs in a document.

Keep every document true. A change that leaves one wrong is not finished.

## Artifacts

Plans go in `.agents/docs/plans` as `YYYY-MM-DD-HH-MM-NNN-slug.md`.

A plan is a record: true as of its date, never edited afterwards, and never where a current fact is read. A decision a plan makes that the project keeps goes into the document that owns it.
