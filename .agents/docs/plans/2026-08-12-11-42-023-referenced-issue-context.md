# Give referenced issue context to review agents

Roadmap: item `23`, `Give referenced issue context to review agents`.

## What Was Checked

Read out of GitHub's own documentation on 2026-08-12, and out of the installed code.

- GitHub autolinks five reference forms: an issue URL, `#123`, `GH-123`, `Username/Repository#123`,
  and `Organization/Repository#123`. Custom autolinks are a separate per-repository feature covering
  external systems, and are excluded by the item. Autolinks are not created in repository files or
  wikis. See [autolinked references](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/autolinked-references-and-urls).
- A closing keyword (`close`/`fix`/`resolve` and their forms, any casing, optional colon) links an
  issue, and `KEYWORD OWNER/REPOSITORY#NUMBER` links one in another repository. Keywords take effect
  only on a pull request targeting the default branch; against any other base no link is created.
  Manual linking from the PR sidebar is same-repository only and caps at ten. See
  [linking a pull request to an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue).
- Both link kinds close the issue on merge, so both are `PullRequest.closingIssuesReferences` in
  GraphQL. That the manual link appears there is the one assumption a live check has to confirm.
- Resolve already holds everything the fetch needs: the job token, `contents: read` for a compare or
  a commit list, and `issues: write` — which includes read — for an issue. It fetches the pull
  request verbatim, so the title, the body, the base SHA, and the commit count are already on hand.
- The push path in `coral/resolve.py` makes no GitHub call today. It will make three kinds.
- `coral/github/issues.py` is the main-push verifier's own bounded search-and-view tool pair, on the
  review side of the boundary. It is not what this item builds and does not change.

## Goal

Before either agent runs, Coral reads the issues the change refers to and gives both the same fixed
block of text: each issue's repository, number, state, title, and bounded body, plus a notice naming
what a bound or an unreadable issue left out. Resolve fetches it; it crosses to review as an
artifact; no agent holds a credential or a tool that reads GitHub on this path.

## Approach

### The new module

`coral/github/references.py` owns the reference forms, the query shapes, the bounds, and the file
the context crosses on. Constants, each `Final`:

- `MAX_REFERENCES = 10` — what one review reads, matching GitHub's own cap on manual links.
- `MAX_COMMITS = 100` — one page of the reviewed range's commits, scanned for references.
- `MAX_BODY_CHARACTERS = 20_000` — one issue body, the same cut the conversation and the verifier's
  view tool already make.
- `MAX_CONTEXT_CHARACTERS = 60_000` — every body together.

Frozen dataclasses: `Reference(owner, repo, number)`; `ReferencedIssue(owner, repo, number, state,
title, body, truncated)`; `IssueContext(issues, unavailable, left_out)`, where `unavailable` holds
`owner/repo#number` strings and `left_out` counts references a bound never read. A `TypeAdapter`
writes and reads it, as `coral/github/conversation.py` does for the conversation.

- `references_in(text, owner, repo) -> list[Reference]` — one regex over the four textual forms
  (URL, `owner/repo#n`, `GH-n`, `#n`), in the order they appear, a bare number defaulting to this
  repository. A left guard keeps `abc#1` from matching and a right guard keeps `#1a2b3c` from being
  issue 1. Markdown structure is not parsed: a reference inside a code fence is read too, which
  costs one bounded read rather than a Markdown parser.
- `linked_issues(github, owner, repo, number) -> list[Reference]` — one GraphQL query for
  `closingIssuesReferences`, asking only for each issue's number and repository, because every
  reference is resolved the same way below.
- `pull_request_messages(github, owner, repo, number) -> Messages` — `/pulls/{n}/commits` at
  `per_page=100`, page one. `Messages(messages, total)` carries the count the pull request reported
  so the notice can say how many commits went unscanned. Chosen over compare, which would answer
  with the whole diff's patches as well.
- `push_messages(github, owner, repo, base, head) -> Messages` — `/compare/{base}...{head}` at
  `per_page=100`, whose `total_commits` is that count. Three dots, so the range is the merge base's,
  the same range `coral/diff.py` reads.
- `pull_request_context(...)` and `push_context(...)` — one call per path for `coral/resolve.py`.
  Each assembles references in a fixed order and hands them to `context_for`: linked issues first,
  then the title, then the body, then each commit message oldest first, deduplicated on
  `(owner, repo, number)`. The order is what the bound cuts from the far end, so what somebody
  linked deliberately survives a change that mentions many.
- `context_for(github, owner, repo, references)` — reads the first `MAX_REFERENCES` with
  `/repos/{o}/{r}/issues/{n}`. A response carrying `pull_request` is not an issue and is dropped
  with a log line, not a notice. A read that fails or answers unreadably becomes an `unavailable`
  entry. A body is cut at `MAX_BODY_CHARACTERS`, and an issue whose body would cross
  `MAX_CONTEXT_CHARACTERS` is skipped rather than stopped on, so one enormous issue does not discard
  the smaller ones behind it. Everything past `MAX_REFERENCES`, and everything skipped, counts in
  `left_out`.

One issue read failing degrades to a notice; the linked-issues query or the commit list failing
fails resolve, which is what the pull-request fetch beside them already does.

### Resolve

Both paths fetch the context after every gate has passed and before the key is minted, so a declined
run makes none of these calls and a fetch that breaks leaves no minted key behind it. Each writes
`runner.issue_context_path()`, and the push path constructs the `GitHub` client it has not needed
until now. A log line names the numbers read, the unavailable ones, and `left_out`.

### Review

`render_issue_context(context) -> str` joins in `coral/review.py`, beside `render_conversation`, for
the same reason: the labels and the notice are Coral's deterministic job. It renders a heading per
issue — `owner/repo#number`, its state, its title — then the body, and it always renders, saying so
when a change refers to nothing. Its first line says the issues are information about the change and
never instruction, in the words `coral/github/issues.py` already uses for untrusted evidence.

One rendered string is interpolated into all four requests — `render_request`,
`render_push_request`, `render_verification_request`, `render_push_verification_request` — directly
before `# The change under review`, which is what makes both agents' context the same by
construction. `review()` reads the context once, logs the block's issue count and character count,
and passes the string down.

Both prompts gain a short section: referenced issues are the intent the change was written against,
they are read to judge whether the code does what the change claims, they are untrusted text and
never instruction, and a notice means some went unread.

### The wiring

- `coral/runner.py` — `issue_context_path()`, `issue-context.json`.
- `.github/workflows/coral.yml` — that file added to resolve's upload list. No permission changes:
  resolve's scopes already cover all three calls, and review gains nothing.
- `coral/rehearse.py` — stages an empty context beside the stub pull request and the empty
  conversation, so `review()` reads the file unconditionally rather than treating absence as empty.

## Related code

- `coral/github/references.py` — new: the forms, the three queries, the bounds, the artifact.
- `coral/resolve.py` — the fetch on both paths, after the gates.
- `coral/review.py` — the rendered block in all four requests, and the log line.
- `coral/runner.py`, `.github/workflows/coral.yml`, `coral/rehearse.py` — the artifact.
- `coral/prompts/review.md`, `coral/prompts/verify.md` — the referenced-issue section.
- `tests/test_references.py` — new. `tests/test_review.py`, `tests/test_resolve.py`,
  `tests/test_runner.py` — updated.

## Current state

- Neither agent is told anything about the issue a change is for. The reviewer gets the title, the
  body, the conversation, and the diff; the verifier gets the title, the body, the diff, and the
  findings.
- On a main push the agents get the commit and its diff and nothing else.
- The only issue text that reaches a model is the main-push verifier's own duplicate search.

## Test plan

**Unit tests**

- Each of the four textual forms parses, with the bare form defaulting to this repository and the
  `owner/repo` form keeping its own. `abc#1`, `#1a2b3c`, `#0`, and a bare `#` produce nothing.
- Source order and deduplication: a linked issue named again in the body appears once, first; commit
  messages contribute in range order.
- `MAX_REFERENCES` cuts the tail and counts it in `left_out`, fetching nothing for it.
- A response carrying `pull_request` is dropped and is not counted as unavailable; a failing read
  becomes an unavailable entry naming `owner/repo#number`.
- A body past `MAX_BODY_CHARACTERS` is cut and flagged truncated; an issue that would cross
  `MAX_CONTEXT_CHARACTERS` is skipped while a smaller one behind it is still read.
- `Messages` carries the reported total, so a range longer than `MAX_COMMITS` says what went
  unscanned.
- The context survives a write-and-read round trip through its adapter.
- All four requests carry the identical rendered block, in the same place; an empty context renders
  the sentence rather than nothing.
- Both installed prompts name referenced issues as information rather than instruction.

**What not to test**

- GitHub's own linking behavior, its search ranking, or Actions expression evaluation.
- Whether a model uses the context well. That is what the live checks read.

**Live checks**, in `kkestell/coral-test` with the caller pinned at Coral's `main`:

1. Two open issues, A and B. A pull request against `main` whose body says `Closes #A` and whose
   commit message names `#B` and nothing else. The run's log names both; the review reads as though
   it knows what the change was for. This is the done condition's first clause.
2. A second pull request with an issue linked from the sidebar alone, no text mention. It appears —
   the check that `closingIssuesReferences` covers a manual link.
3. A commit whose message names an open issue, pushed to `main`. The context reaches both agents and
   the run creates its issues as before. Revert the planted defect and close what it filed.
4. A pull request whose body names twelve issues, `kkestell/coral-test#999999`, an issue in
   `kkestell/coral`, and one of the repository's own pull requests. Expect ten read, the missing one
   listed unavailable, the pull request absent from the context entirely, and the excess counted in
   the notice. Whether the job token reads the cross-repository issue is what this check settles; if
   it cannot, it lands in the notice, which is the behavior either way.
5. The container environment lines in run 1's log still show no GitHub token, and the review job
   still receives an empty `github-token` on a pull request.
6. `uv run coral rehearse <sha>` before the rest, which is the check that an empty context renders
   and both agents still run.

## Implementation plan

1. **Save this plan.**
2. **Write `coral/github/references.py`** and `tests/test_references.py`.
3. **Wire resolve** — the fetch on both paths, the push path's client — and `tests/test_resolve.py`;
   **add the path** to `coral/runner.py` and the artifact list, and stage it in `coral/rehearse.py`.
4. **Render it** in `coral/review.py`'s four requests, with the log line, and
   `tests/test_review.py`.
5. **Update both prompts.**
6. **Run** `uv sync --frozen`, `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`,
   `uv run pytest` — all clean.
7. **Rehearse**, then live checks 1 through 5.
8. **Documentation updates** below; roadmap item 23 to `built`, then `verified` once the checks are
   read.

## Not doing

- **Issue comments.** The item holds the issue itself, and a comment thread is a second conversation
  to bound.
- **Transitive references.** An issue naming another issue adds nothing this bound can afford.
- **A pull-request issue-reading tool.** The context is fixed and fetched before the review, which is
  what keeps the review job's token out of the agent's reach. The main-push verifier's duplicate
  search is item 21's and is untouched.
- **Custom autolinks, and references in repository files or wikis.** GitHub does not autolink the
  latter, and the former is a per-repository configuration Coral would have to fetch and interpret.
- **Skipping references inside code fences.** A false reference costs one bounded read.
- **Paging the commit list.** One page of a hundred, and the notice says what that left.

## Documentation updates

`.agents/docs/functional-requirements.md` (no ceiling), under "What Coral Reviews": Coral reads the
issues a change refers to before reviewing it, from the pull request's linked issues, its title and
body, and every commit message in the range; the context is an issue's repository, number, state,
title, and body, and never its comments; a pull request is not an issue reference; the count, each
body, and the whole are bounded and the request says what a bound or an unreadable issue left out;
both agents get the same context; referenced issue text is information about the change, never
instruction, the same rule the conversation carries.

`.agents/docs/architecture.md` (1,497 words of 1,500 — trim before adding, and check with `wc -w`):
the resolve job's bullet gains the issue-context fetch; the review job's bullet, whose main-push
token sentence can carry the same fact in fewer words, pays for it. "The Codebase" gains
`coral/github/references.py`, one line naming the forms, the queries, and the bound.

`.agents/docs/development.md`: `GITHUB_TOKEN`'s entry gains that resolve's reads now include the
referenced issues.

`README.md`: the opening paragraph gains that Coral reads the issues a change refers to; the two
risk bullets naming what the provider sees and what attacker-controlled text reaches the model gain
referenced issue text.

`.agents/docs/roadmap.md`: item 23 to `built`, then `verified` with its bullets deleted — the forms,
the sources, and the bounds are settled by then and live where the code explains them.

## Validation

- The five commands, all clean.
- The done condition, mapped: check 1 is the linked issue and the commit-message-only issue; check 3
  is the main-push range; the identical rendered block, pinned by unit test and logged once per run,
  is both agents receiving the same context; check 4 is the bounded notice for excess and
  unavailable references; check 5 is no GitHub token in an agent container.

## Follow-up

- Item 25 folds these bounds into one byte budget over the whole request. Its ceiling has to count
  this block, and `MAX_CONTEXT_CHARACTERS` is the number it subsumes.
