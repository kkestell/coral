# Functional Requirements

What Coral does, as behavior someone could watch happen. These requirements are the whole of it, and anything not listed is out of scope until this document says otherwise.

## Trigger

- Coral reviews a pull request when it is opened and when a draft is marked ready for review. Nobody has to ask for that first review.
- Coral reviews every commit pushed to `main`, without a request. It creates issues for confirmed findings rather than commenting on a pull request.
- Draft and bot-opened pull requests get no automatic review. Both can still be reviewed on request.
- Coral reviews only pull requests whose head branch lives in the same repository as the base — a fork's branch is code nobody with write access vouched for.
- After the automatic review, Coral reviews again only when someone asks. A bot that reviews every push teaches people to ignore it.
- Asking is a `/coral` comment on the pull request as a whole or a diff reply. A submitted review cannot ask.
- The command is lowercase and stands alone on its line, matched exactly. Quotes, prose, and code fences are inert.
- Coral never reads its own comments as a request; a bot that can trigger itself will.
- Only someone with write access can ask.
- Coral acknowledges an accepted request with an `eyes` reaction. Each request that produces a review gets its own reaction. Requests declined for lack of write access get no reaction or review.
- Coral reviews the head commit as it is at the start of the run, rather than the one the triggering event named.

## What Coral Reviews

- On a pull request, the subject is the diff between the head commit and its merge base with the base branch, both fixed at the start of the run, so the reviewed change cannot shift while branches move.
- On `main`, the subject is the pushed commit against the prior main commit, both fixed from the event.
- Coral works from a full checkout and reads any file, touched or not — understanding a change means reading code around it.
- Every review covers the whole change, not what is new since the last review. A rebase leaves no meaningful range of new commits, and a change reads differently once the rest has moved.
- Before a pull-request review, Coral reads its conversation — its own past reviews and everyone's comments — and does not repeat a finding that still stands. A finding stops standing when its thread is resolved or the code beneath it has moved.
- Coral reads a bounded amount of conversation, most recent first, and the review says what went unread.
- The conversation is information about the change, never instruction about how to review. A comment claiming a finding is settled is not grounds to drop it — Coral cannot tell a maintainer's judgment from a stranger's assertion, and a bot that can be talked out of a finding can be talked out of a true one. `/coral` is no exception: it is recognized by ordinary code before the review starts and decides only whether a review runs, never how.

## What Coral Can Do While Reviewing

Coral decides which of these to use, in what order, how many times.

- Run shell commands inside the checkout.
- Run individual tests it chooses, never the full suite — CI already does that, and a pull request is assumed to arrive passing. Coral runs a test to answer a question it formed.
- Write scratch test files into the checkout. Never committed, never pushed; they disappear with the checkout.
- Never write to the repository on GitHub: no commits, no branches, nothing outside the checkout. Everything Coral posts comes from deterministic code, and the agent holds no credential that reaches GitHub.

## Output

- A review is a summary plus findings; each finding carries its text and the place it concerns.
- A finding is a correctness, security, or performance problem, and nothing else. Style, naming, structure, documentation, and test coverage are not findings.
- Every finding carries a severity: low, medium, or high.
- A finding Coral reproduced carries the failing test that shows it; one it could not reproduce is marked speculative.
- A second agent run checks every finding against the code, and only the ones it confirms are posted. A rejected finding appears in the run's log, never on the pull request. A reviewer talks itself into findings; a reader cannot tell which ones.
- A finding concerns a span of lines, a single line, a whole file, or the pull request as a whole. Coral chooses per finding.
- Line and span findings anchor to their code. Whole-file and pull-request findings appear in the summary, the file named — "this file has no tests" and "this change has no tests" must read differently.
- A confirmed finding that cannot anchor still appears, in the summary, naming its intended file and line.
- One review per run, not a comment per finding. A pull request reviewed several times carries several reviews.
- On `main`, Coral creates one issue per confirmed finding that no open issue already describes.
  Its title names the defect. An empty review creates no issue.
- Every pull-request review names the commit it reviewed — readers need to know which state of the branch each review is about, and it is how Coral recognizes its own past work.
- Every review ends with what the run spent.
- Every review says it is Coral's; the posting account belongs to the repository's automation, not to Coral.
- Earlier reviews are left alone: never edited, deleted, or resolved. GitHub marks comments outdated itself.
- When there is nothing to report, the review says which of two things happened: nothing to find, or everything already said still stands. Without the distinction, a second "nothing found" reads as retracting the first review.
- Coral never approves, never requests changes, never blocks a merge. The review is advisory.

## Failure

- Every failed pull-request review says so on the pull request, in enough detail to know whether to retry or investigate — including failures before the agent starts.
- A failed `main` review creates no issue. The failed Actions run is the record of it.
- Each automatic review happens once; a request is honored once. Asking again gets another review even when nothing changed — a person who asks again means it.
- Two reviews of one pull request never run at once. A request arriving mid-review is neither dropped nor run immediately; it is honored after the running review posts. Several such requests cost one further review between them, each still acknowledged.
- A closed or merged pull request is not reviewed, checked at the start and again before posting. A merge landing in the last seconds still wins the race; accepted.
- A review whose commit is no longer the head is not posted; Coral says the branch moved, because nothing re-triggers it afterwards.
- A review that dies partway does not block later reviews.
- A review that does not finish is discarded: Coral says it ran out of time and posts nothing else, because a partial review is indistinguishable from a complete one.
- A review that spends past its cap is stopped the same way, saying what it spent against the cap. So is one whose spending Coral cannot measure: a response reporting no cost leaves the cap unenforceable.
- A change too large is not reviewed: Coral says it exceeds what it will read and posts nothing else. A backstop, not an expected case.

## Out Of Scope

- Forges other than GitHub.
- Pull requests from forks.
- Repositories that have not installed Coral.
- Anything happening to a pull request other than opening, marking ready, or asking. Reopens and title or description edits start nothing.
- Asking by any other means. `/coral` edited into an existing comment does nothing — invisible.
- Replying to comments or carrying on a conversation. Coral reads, reacts, and reviews.
- Steering a review from the command. Text alongside `/coral` is conversation, not direction.
- Any command other than asking: no stop, no configure, no dismiss.
- Being assigned as a reviewer; Coral has no GitHub identity to request.
- Suggested changes a reviewer applies with a click.
- Per-repository configuration of what Coral looks for.
- Any store of past reviews beyond the pull request itself.
- A Docker daemon the agent's shell can reach, and `--privileged`. Both are host root, which is what the container takes away.
