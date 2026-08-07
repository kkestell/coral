# Review: correctness, security, and practices

A read of every module under `coral/`, the reusable workflow, the four composite actions, and both
prompts, against the guarantees `.agents/docs/` states. The test suite, `ruff check`, `ruff format
--check`, and `mypy --strict` all pass.

Each finding carries a disposition. **Trivially fixable** means the change is local and the correct
behavior is already decided. **Needs research** means the fix is agreed but one fact has to be
confirmed first. **Needs a decision** means somebody has to choose between accepting the behavior
and paying for a different one, and the two choices lead to different code.

---

## 1. The agent's shell can recover both secrets from an ancestor process

Disposition: **needs a decision**, and the closing option **needs research**.

`.agents/docs/architecture.md` accepts the prompt-injection risk on the grounds that the real
bounds are the unreachable secrets and the schema-only return path. The secrets are reachable.

`coral/review.py` pops `GITHUB_TOKEN` and `OPENROUTER_API_KEY` from `os.environ`, which calls
`unsetenv` and so clears them from the Python process itself. `coral/environment.py` then builds
the agent's shell environment from an allowlist that holds neither. But the composite action's bash
step is an ancestor of that shell, and `actions/review/action.yml` sets both secrets as step-level
`env:`, so the bash process still holds them.

On Linux, `/proc/<pid>/environ` is readable by the same user. Every step on `ubuntu-latest` runs as
`runner`. Ubuntu's default `ptrace_scope` of 1 restricts these reads to ancestors of the reading
process, and the bash step is an ancestor, so that restriction does not apply. One shell command
from the agent recovers both credentials.

The two paths:

- Accept it. Then `.agents/docs/architecture.md` has to stop resting the argument on unreachable
  secrets, because they are not. The residual risk becomes "an injected agent can exfiltrate the
  job token and the OpenRouter key", which is a larger claim than the one recorded there now.
- Close it. The secrets stop being step environment and reach `coral review` some other way — a
  file the runner writes and the step removes, or standard input. Research first: whether the
  composite action can hold a secret without it landing in the step's environment at all, and
  whether `GITHUB_TOKEN` can be kept out of it given the step invokes the console script directly.

Popping from `os.environ` is worth keeping either way. It is hygiene, not a boundary.

## 2. Coral's marker is forgeable, and it gates the already-reviewed decision

Disposition: the suppression half is **trivially fixable** but **needs research** on one GraphQL
field. The impersonation half **needs a decision**.

`.agents/docs/roadmap.md` calls the sentinel Coral's only reliable self-identification. The pattern
in `coral/github/marker.py` matches `<!-- coral:reviewed commit=... -->` anywhere in a body, and
anybody who can write a comment can write those characters.

The half that does not involve the model: `reviewed_commits` in `coral/github/conversation.py`
reads the marker out of every review body without checking who wrote it, and `declined` in
`coral/resolve.py` stops the run when the head SHA appears in that list. Anybody with read access
can submit a review on a public pull request. A review containing the marker and the head SHA
suppresses the automatic review of that commit, and that gate posts nothing, so the suppression is
silent.

The fix is to keep only markers on comments the token's own account wrote. GitHub's `Comment`
interface carries `viewerDidAuthor`, and `PullRequestReview` implements `Comment`. Confirm that the
field is present on `PullRequestReview` before adding it to `REVIEW_FIELDS`; the rest is a filter in
`reviewed_commits`.

The other half is `attribution` in `coral/review.py`, which labels any comment carrying the marker
as written by "Coral" when it renders the conversation for the model. The review prompt tells the
model not to repeat a finding that already stands, so a forged Coral comment is a lever on the
review. Deciding what to do here means deciding what the model should see: a forged marker could be
stripped from the rendered body, or the whole comment could be attributed to its real author, or
this could be folded into the injection risk already accepted. The same `viewerDidAuthor` check
feeds whichever is chosen.

## 3. `parse_added_lines` misreads added content as a file header

Disposition: **trivially fixable**, no research.

`coral/diff.py` treats a `+++ ` line as a file header when the line before it started with `--- `.
The comment above that code says the pairing only occurs at a real header. It also occurs inside a
hunk, when a deleted line's content begins with `--` and the next added line's content begins with
`++`.

Reproduced against real `git diff --unified=0` output:

```
@@ -1 +1 @@
--- alpha
+++ beta
@@ -3 +3 @@ keep
-second
+CHANGED
```

`parse_added_lines` returns `[AddedLine(path='f.txt', line=1), AddedLine(path='beta', line=3)]`.
Line 3 of the real file is lost, and a phantom path is recorded in its place. Every later hunk in
that file inherits the wrong path. Findings on those lines demote into the summary, and a finding
anchored to the phantom path draws a 422 from GitHub, which sends `post_review` down its retry and
demotes every finding in the review.

Track whether the walk is inside a hunk. Once a hunk header has been seen, `--- ` and `+++ ` lines
are content until the next `diff --git` line.

## 4. A git failure reports nothing actionable

Disposition: **trivially fixable**, no research.

`.agents/docs/functional-requirements.md` requires a failed review to say so on the pull request in
enough detail to know whether to retry or investigate. The `git` helper in `coral/diff.py` runs
with `check=True` and `capture_output=True`. `CalledProcessError`'s message is only `Command
'[...]' returned non-zero exit status 128.`; git's own stderr goes to the exception's `stderr`
attribute and never into the message. `described` in `coral/report.py` posts the message, so a
missing base commit or a bad ref reaches the pull request with the diagnosis stripped out.

Raise a `RuntimeError` carrying `result.stderr` instead of relying on `check=True`.

## 5. A failed reaction takes down a review that would have succeeded

Disposition: **trivially fixable**; one small choice inside it.

`react` in `coral/github/reactions.py` posts one reaction per request with no error handling, and
`resolve` calls it before any gate. A comment deleted between the fetch and the reaction answers
404 and ends the run. A locked conversation answers 403 and does the same. In both cases the report
step then posts that the run failed, for a review that had nothing wrong with it.

The acknowledgment is a courtesy and should not be able to cost the review. Log the failure and go
on to the next request. The choice is whether to swallow every `ApiError` or only 403 and 404;
swallowing every one is simpler and loses nothing, since the only thing a reaction failure can tell
Coral is that this comment did not get its acknowledgment.

## 6. `COLLABORATOR` includes read-only collaborators

Disposition: **needs a decision**.

`WRITE_ACCESS` in `coral/command.py` treats the `COLLABORATOR` association as write access. GitHub
sets that association for anybody invited to the repository, including at the read role.
`.agents/docs/architecture.md` justifies the trust level by saying that population has write access
and already runs code beside the secrets, which is not true of a read-only collaborator, who can
now start an agent with an unsandboxed shell.

The impact on `kkestell/coral` and `kkestell/coral-test` is nothing, since neither has
collaborators. The choice is between correcting the sentence in `.agents/docs/architecture.md` to
say what the association actually means, and spending one call per run on the repository
collaborator permission endpoint to check the real role. The first costs nothing and is honest; the
second costs a call and a failure mode on every run.

## 7. Smaller things

All **trivially fixable**, none needing research.

`bound` in `coral/github/conversation.py` uses `break` when the next comment would cross
`MAX_CHARACTERS`, so one large comment discards every older comment that would still have fit.
GitHub caps a comment at 65,536 characters against a 400,000 budget, so at most a handful are ever
lost this way. `continue` is no more complex and cannot lose one.

`rendered_thread` in `coral/review.py` binds a local named `where`, which shadows the `where`
imported from `coral.schema` at the top of the same file. Both are in use in that module and they
mean different things.

---

## Holds up

Read adversarially and found correct: the deadline arithmetic and the reviewer's slice of the step;
the two-run split and the rule in `confirmed` that a finding no verdict names is dropped; the fork
and closed-state gates in `resolve`; the composition in `signed` and `review_payload` and the
unconditional demotion behind a 422; the fence tracking in `asks_for_review`; and the handoff
between the review step's own failure path and the report step through `reported_path`.
