# Functional Requirements

THIS FILE MUST BE KEPT UP TO DATE AT ALL TIMES

What Coral does, written as behavior someone could watch happen. How it does it is in `.agents/docs/technical-requirements.md`.

Coral is a proof of concept. The requirements below are the whole of it. Anything not listed here is out of scope until this document says otherwise.

## Trigger

- **FR-1** — Coral reviews a pull request when that pull request is opened.
- **FR-2** — Coral reviews pull requests whose head branch lives in the same repository as the base branch. Pull requests from forks are out of scope.
- **FR-3** — Coral reviews the pull request at its head commit as of the moment the event arrived.

## What Coral Reviews

- **FR-4** — The subject of the review is the diff between the pull request's head commit and its merge base.
- **FR-5** — Coral works from a full checkout, not from the diff alone. It reads and searches any file in the repository, whether or not the pull request touched it, because understanding a change usually means reading code the change did not touch.

## What Coral Can Do While Reviewing

Coral is an agent, not a static analyzer. It decides for itself which of the following to use, in what order, and how many times.

- **FR-6** — Coral runs shell commands inside the checkout.
- **FR-7** — Coral runs individual tests and test selections that it chooses. It does not run the full test suite. Continuous integration already does that, and a pull request is assumed to arrive with its tests passing. Coral runs a test to answer a specific question it has formed about the change.
- **FR-8** — Coral writes new test files into the checkout to confirm a behavior or to check a theory about a regression. These are scratch. They are never committed and never pushed, and they disappear with the checkout.
- **FR-9** — Coral never writes to the repository on GitHub. It pushes no commits, creates no branches, and modifies no files outside its own checkout.

## Output

- **FR-10** — A review is a summary plus a list of findings. Each finding carries the text of the finding and the place it concerns.
- **FR-11** — A finding concerns one of four things: a span of lines in a file, a single line in a file, a whole file, or the pull request as a whole. Coral chooses which, per finding.
- **FR-12** — Findings that concern a line or a span appear anchored to that code, so the reader sees the finding against the thing it is about. Findings about the pull request as a whole appear in the review summary.
- **FR-13** — A finding that cannot be anchored where Coral asked for it is still shown to the reader, in the summary, naming the file and line it was meant for. A finding is never silently discarded because it would not attach.
- **FR-14** — Coral posts one review per pull request. It does not post a comment per finding as it goes.
- **FR-15** — When Coral finds nothing worth reporting, it says so. Silence is indistinguishable from failure.
- **FR-16** — Coral never approves a pull request, never requests changes, and never blocks a merge. Its review is advisory, and a human decides what to do with it.

## Failure

- **FR-17** — When Coral cannot complete a review, it says so on the pull request, in enough detail that a human knows whether to retry or to investigate. A review that dies quietly is worse than no review, because the author waits for it.
- **FR-18** — Coral reviews a given pull request once. A duplicate delivery of the same event does not produce a second review, and does not cost a second agent run.
- **FR-19** — Two reviews of the same pull request never run at the same time. Deliveries that arrive while a review is in progress are dropped, not queued behind it.
- **FR-20** — A review that dies partway through does not lock the pull request out of ever being reviewed again.

## Out Of Scope

Named here so nobody has to guess whether the omission was deliberate.

- Forges other than GitHub.
- Pull requests from forks.
- Re-reviewing when new commits are pushed to an open pull request.
- Replying to comments, or any conversation after the review is posted.
- Suggested changes that a reviewer can apply with a click.
- Per-repository configuration of what Coral looks for.
- Any persistent memory of past reviews.
