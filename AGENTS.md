# AGENTS.md

Coral is a proof-of-concept CLI code review agent, kept deliberately simple. It runs configured reviewers concurrently, verifies their findings with a separate agent, and prints one Markdown review. It is written in Python on LangChain, with models reached through OpenRouter.

## Documentation

Each document owns a subject and is the only place that subject is written down. Read the one covering what you are about to do. Do not infer its contents from this list.

- `.agents/docs/functional-requirements.md` — Coral's feature-complete behavior, why that behavior, and what is out of scope; the roadmap names any behavior not built yet.
- `.agents/docs/architecture.md` — how the code is organized and how the CLI runs: the stack, the layout, the run, the rules that hold everywhere, and the decisions still open.
- `.agents/docs/roadmap.md` — the order the work happens in: what each item builds, what it depends on, its status, and its done condition.
- `.agents/docs/development.md` — prerequisites, setup, commands, environment variables, and gotchas.
- `.agents/docs/testing.md` — where the tests live, what a new test looks like, what the unit suite cannot show, and how a change is checked against a real run.
- `.agents/docs/code-style.md` — the conventions this code follows, including the ones no linter checks.
- `.agents/docs/research/` — dated records of investigation: sources, observations, experiments, and the conclusions they supported at the time.
- `README.md` — how somebody outside the project installs and uses Coral. Nothing under `.agents/docs/` describes installation or use.

## How These Documents Are Written

These documents are context for agents. They are loaded into a context window before the work starts, and every word they spend is budget the work does not get. They are reference material, not writing to be read for pleasure: an agent looks a fact up, acts on it, and moves on.

State the fact. One bullet is one fact, one or two sentences, and the first sentence is the fact itself.

A reason earns one clause — "X, because Y" — only when it protects the fact from a wrong future change: a rule that looks arbitrary and is not, a number that must not be tuned, an approach that was tried and fails for a non-obvious reason. A reason that is obvious from the fact gets nothing.

No rhetoric. Never restate a fact from a second angle, never write a sentence whose only job is emphasis or transition, and never narrate — no "this is what makes X possible", no walking the reader through rejected alternatives, no building up to a conclusion. If deleting a sentence loses no fact, delete it.

Ceilings, checked with `wc -w`: `roadmap.md` holds at most 3,500 words; every other document under `.agents/docs/`, `functional-requirements.md`, `plans/`, `reviews/`, and `research/` excepted, holds at most 1,500. An edit that would cross a ceiling deletes something old before it adds. Ceilings never rise, and a ceiling is a limit rather than a target. `functional-requirements.md` has no ceiling, because it enumerates behavior and a cap on it is a cap on what Coral may do.

An item's bullets hold only what constrains work still to come: a decision a later item is written against, a number that must not be tuned, a shape the next build has to match. A mechanic the code explains where it lives is a comment there. Verifying an item settles its mechanics, so the bullets describing them go then, leaving what the item built, what it depended on, its status, and its done condition. The roadmap shrinks as the work finishes.

## Where Things Go

One fact, one home. A second copy will disagree with the first, and nothing will catch which one went stale.

Pick the home by the question the fact answers. What does Coral do, and why that? Functional requirements. How is the code organized, and what holds everywhere? Architecture. What gets built next, and when is it done? Roadmap, in that item. What did an investigation find, from which evidence, and when? Research. What do I type? Development. How do I check it? Testing. How do I write this Python? Code style. How do I install Coral? README. Why is this line like this? A comment on that line.

State a fact you do not own in one clause. Never explain it. Writing "because" about something another document owns means stopping and pointing at that document instead.

Never summarize another document. No recap sections, no restated rules, no preamble listing what the other documents hold.

Never label anything for citation. No requirement numbers, no invariant identifiers, no scheme that exists to be referred to from elsewhere. Point at a document and a heading.

A fact with no home does not get written down. Do not add a section for it. Do not add a document.

A comment explains the line beneath it. If it would still be true with that code deleted, it belongs in a document.

Keep every document true. A change that leaves one wrong is not finished.

## Finishing Work

An item's done condition is in `.agents/docs/roadmap.md`, and every claim it makes is met by a real run, the way `.agents/docs/testing.md` describes. Do those runs before calling the item done or changing its status. Describing what a run would show, or naming it as left over for later, is not doing it — an item is not done until the run actually happened and its evidence was read.

## Artifacts

Plans go in `.agents/docs/plans`, code reviews go in `.agents/docs/reviews`, and research goes in `.agents/docs/research`, all as `YYYY-MM-DD-HH-MM-NNN-slug.md`.

A plan, review, and research document are records: true as of their date, never edited afterwards, and never where a current fact is read. A decision any of them makes that the project keeps goes into the document that owns it.
