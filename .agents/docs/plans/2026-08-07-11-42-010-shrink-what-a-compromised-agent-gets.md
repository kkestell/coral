# Shrink what a compromised agent gets

Roadmap: item `10`, `Shrink what a compromised agent gets`.

## What Was Checked

- The run is one job, `coral`, holding `contents: read`, `issues: write`, and `pull-requests: write`, with five steps. The write scopes exist for the reaction and for the review; the agent runs in the same job and the runner keeps the token in `Runner.Worker`'s memory for the whole of it.
- `coral/review.py` is the only caller of `post_review`, `post_comment`, and `is_open`, and the only place the review step needs `GITHUB_TOKEN` at all. Nothing else in the review step touches the GitHub API.
- `post_review` in `coral/github/post.py` recovers from a 422 by calling `review_payload` a second time with an empty added-line set. That second call needs the review object and the diff, so a job that holds neither cannot make it.
- `review_payload` returns `commit_id` and `event: "COMMENT"` alongside the prose and the anchors. A payload composed in the agent's job and posted by a job holding write scopes would let a compromised agent set `event` to `APPROVE`, which contradicts "never approves" in `.agents/docs/functional-requirements.md`.
- `runner.reported_path()` is how the review step and the report step avoid speaking twice. Both steps posting is what makes it necessary, and only one job posts after this item.
- `reset()` in `coral/diff.py` runs `git clean -fd` in the workspace between the two agent runs. Anything crossing a boundary has to stay out of the workspace, which `runner.temporary_directory()` already does.
- `actions/upload-artifact` v7.0.1 is `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` and `actions/download-artifact` v8.0.1 is `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c`. Both tags are lightweight, so those are commit SHAs and pin the way `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` does.
- `download-artifact` throws `Artifact '<name>' not found` when `name` names one that does not exist, and filters an empty list without error when `pattern` matches none. That difference is the whole of how the publishing job tolerates a review job that died before writing anything.
- `download-artifact` needs `actions: read` and a token only for artifacts from another run or repository. Same-run downloads use the runner's own artifact token, so no job needs a scope for them.
- Word counts: `architecture.md` 1,456 of 1,500 and `testing.md` 1,499 of 1,500, both of which grow here. `functional-requirements.md` 1,496 of 1,500 needs no change — the split makes "every failed review says so on the pull request" more true, not different. `roadmap.md` is 1,342 of 3,500 and `development.md` 662 of 1,500.
- `README.md` says the model is not wired up and the review contents are hardcoded, which has been false since item 5.

## Goal

The job that runs the agent holds `contents: read` and nothing else. Every write — the reaction, the change-too-large comment, the review, the failure comment — happens in a job the agent never runs in. What an injected agent can still reach is the OpenRouter key and the text of the one review this run was going to post; what it loses is any credential that writes anything, anywhere.

## Approach

### Three jobs

`resolve`, `review`, `publish`, in that order, each with its own `runs-on` and its own `permissions`.

`resolve` and `publish` keep the three scopes the single job has today. `review` narrows to `contents: read`, which is what the checkout needs and all it needs: with `is_open` and both posts gone from it, the review step makes no API call.

The coarse job-level `if:` stays on `resolve` alone. `review` runs on `needs.resolve.outputs.proceed == 'true'`, so a decline skips it the way the old step conditions did.

`publish` runs when a review was going to happen or when resolve broke before deciding:

```yaml
    if: >-
      (needs.resolve.result == 'success' && needs.resolve.outputs.proceed == 'true')
      || needs.resolve.result == 'failure'
```

Written positively over resolve's own outcome, which covers every case in one expression. A decline already said whatever it owed, so `publish` does not start. A delivery the coarse condition excluded skips `resolve`, and `'skipped'` is neither of the two values above. A run somebody cancels starts no job that does not say `always()`, so the cancelled run still posts nothing, which is the decision item 8 made.

`timeout-minutes: 30` on `review`, because `STEP_BUDGET_SECONDS` in `coral/deadline.py` is measured against it. Ten on `resolve` and on `publish`, a backstop on a job that makes a handful of API calls each already bounded by `TIMEOUT` in `coral/github/client.py`.

### What crosses, and how

A job boundary is not a step boundary: the runner's temporary directory does not survive one. `proceed` and the head SHA cross as job outputs, mapped from the resolve action's step outputs in the job's `outputs:` block. Everything else crosses as an artifact.

`resolve` uploads `pull-request.json` and `conversation.json` as `coral-resolve`. `review` uploads `review-payloads.json` or `reason.txt` as `coral-review`. Both uploads name the files rather than the directory, so the artifact's root is the directory holding them, and both carry `if: ${{ !cancelled() }}` so a failed job still hands on whatever it wrote. `retention-days: 1`, because these exist to cross a boundary inside one run.

Every download targets `${{ runner.temp }}/coral`, which is what `runner.temporary_directory()` returns, so the paths in `coral/runner.py` need no notion of where a file came from. It is outside the workspace, so the checkout cannot disturb it and `git clean -fd` cannot delete it.

`review` downloads `coral-resolve` by `name`, so its absence fails the job loudly — a run that proceeded and cannot find the pull request is broken. `publish` downloads each by `pattern`, in two steps, because a job that died before writing anything creates no artifact and that absence is an input `coral publish` reads rather than an error.

### The review step composes and posts nothing

`coral/github/post.py` gains the pair of bodies and the two fields the publishing step keeps rather than trusts:

```python
@dataclass(frozen=True)
class Payloads:
    """The two create-review bodies, one of which the publishing step posts."""

    anchored: dict[str, Any]
    demoted: dict[str, Any]

def payloads(commit: str, review: Review, added: set[AddedLine]) -> Payloads:
    """Both bodies: the one whose findings attach, and the one where every finding is demoted."""

def write_payloads(path: Path, payloads: Payloads) -> None:
def read_payloads(path: Path) -> Payloads:

def submitted(commit: str, payload: dict[str, Any]) -> dict[str, Any]:
    """A body as the publishing step posts it, carrying the two fields it does not take on trust."""
```

Both bodies are built where the diff is, because both need the added-line set the anchors were checked against and that set exists only in the job holding the checkout. GitHub accepts or rejects a review whole, using its own patch generation, so the local check cannot be sufficient and the fallback has to travel with the body it replaces. `write_payloads` and `read_payloads` use a `TypeAdapter` the way `write_conversation` does.

`review_payload` stops emitting `commit_id` and `event`, and `submitted` adds them: `event` is `COMMENT` because the review is advisory, and `commit_id` is the commit resolve pinned. Both were composed in the job the agent ran in, and neither is a field a compromised agent gets a say in. `post_review` calls `submitted` on whichever body it sends, so no caller can forget.

`post_review`'s signature becomes `(github, owner, repo, number, commit, payloads)`. The 422 recovery reads the same as it does now, sending `payloads.demoted` instead of recomposing.

`coral/review.py`:

- Pops `OPENROUTER_API_KEY` and nothing else. The job's token is not there to pop, because `actions/review/action.yml` no longer sets it and the action no longer takes it.
- Reads only `head` and `base` off the pull request. The owner, the repository, and the number were needed for the posts and are not needed here.
- Ends with `write_payloads(runner.payloads_path(), payloads(head, review, added))`.
- Wraps its whole body in one `try`, rather than starting the `try` after the credentials as it does now. The reason that boundary existed was that a failure above it left the step without a client to post with; the step has no client at all now, so every failure is one the reason file can carry.
- Its `except` writes `described(error)` to `runner.reason_path()` and re-raises. A run that could not review is still red.
- Loses the `is_open` check, which belongs at the last moment before posting and is now in the job that posts.

### The publishing step

`coral/report.py` becomes `coral/publish.py`, and `coral report` becomes `coral publish`. The name is the job's: the step posts the review as well as the failure, and reporting is the smaller half of that. `coral/github/post.py` keeps its name, which is why the step is not called `post` — `tests/` holds one `test_<module>.py` per module and the two would collide.

`REASON_LIMIT`, `described`, `failure_comment`, and `pinned_commit` move across unchanged. `owed` loses its first question, because `runner.reported_path()` goes away with the two-steps-can-speak problem it solved, and keeps its second: a comment merely mentioning `/coral` mid-sentence allocates a runner and asks for nothing.

```python
def publish() -> None:
    """Post the review this run produced, or say why there is none."""
```

Four things in order: return early when there are no bodies and nothing is owed; post the review when the bodies are there and the pull request is still open; otherwise post the failure comment, carrying the reason when one crossed and no reason when the job died before writing one. The owner, the repository, and the number come off the event, and the commit off resolve's pull request — never off the review job's artifact.

That last branch is new behavior: a review job GitHub kills for its own `timeout-minutes`, or one whose runner vanishes, now gets a comment. Item 8 could not report either, because no step runs in a job that is already gone.

### `coral/runner.py`

`payloads_path()` and `reason_path()` join `pull_request_path()` and `conversation_path()`; `reported_path()` goes. All four docstrings say the same new thing: the file crosses a job boundary as an artifact, so the temporary directory it is written in is not the one it is read in.

## Related code

- `.github/workflows/coral.yml` — three jobs, the two job outputs, the two uploads, the three downloads.
- `actions/review/action.yml` — the `github-token` input removed.
- `actions/publish/action.yml` — renamed from `actions/report/`, running `coral publish`.
- `coral/github/post.py` — `Payloads`, `payloads()`, `write_payloads()`, `read_payloads()`, `submitted()`; `review_payload` drops two keys; `post_review` takes the pair.
- `coral/review.py` — one credential, one `try` around everything, the payload written, no client.
- `coral/publish.py` — renamed from `coral/report.py`; `owed` narrowed, `publish()` in place of `report()`.
- `coral/runner.py` — `payloads_path()`, `reason_path()`, `reported_path()` removed.
- `coral/cli.py` — the `publish` subcommand.
- `coral/environment.py` — the docstrings, which say "both secrets" and now mean one.
- `tests/test_post.py`, `tests/test_publish.py`, `tests/test_runner.py`, `tests/test_reactions.py` — the last for one comment naming the report step.

## Current state

- One job holds both write scopes for the whole run, and the agent runs inside it.
- `coral review` posts the review and its own failure comment, and `coral report` covers the failures the review step never saw.
- The two halves of the failure path meet at `runner.reported_path()`.
- Two values cross a step boundary as step outputs and two files cross under `RUNNER_TEMP`; nothing crosses a job boundary, because there is one job.
- `review_payload` carries `commit_id` and `event`, and `post_review` recomposes the demoted body on a 422.

## Test plan

**Key behaviors to verify**

- `payloads()`: the anchored body carries the attachable finding as a comment; the demoted body carries no comments and names that finding's file and line in its summary. Both bodies carry the same summary prose.
- `submitted()`: `event` is `COMMENT` and `commit_id` is the pinned commit even when the body it is given says `APPROVE` and names a different commit. This is the guarantee the publishing step keeps rather than trusts, and it is the one test that would notice it being dropped.
- `review_payload()` carries neither `commit_id` nor `event`, so nothing depends on a key `submitted` is now responsible for.
- `write_payloads` and `read_payloads` round-trip both bodies through a file under `tmp_path`.
- `owed`: false for a comment event whose body only mentions `/coral`; true for a comment event that is a request; true for a `pull_request` event. The reported-file case goes with the file.
- `payloads_path()` and `reason_path()` sit under the runner's own temporary directory, written the way `tests/test_runner.py` writes its cases — `RUNNER_TEMP` pointed at `tmp_path`.
- Everything `tests/test_post.py` already asserts about composition, unchanged. `test_no_finding_is_lost` is the assertion that the split must not weaken.

**What NOT to test**

- `publish()` end to end, which needs a `GitHub` that posts. Its judgment is `owed` and an `exists()` call, and its prose is `failure_comment` and `submitted`.
- The review step's `except` block, which needs a review that fails on the way to a file. Live checks cover it.
- Whether Actions runs the jobs in the order their `needs` implies, whether a job output reaches a later job, and whether an artifact round-trips. None of it is Coral's code, and all of it is a live check.
- Whether the review job's token can write. That is the point of live check 2 and cannot be asserted from a developer machine.

**Live checks**

Added as a group in `.agents/docs/testing.md`, and two existing checks change because the log they read moved.

1. Open a pull request that gives Coral something to find. The run shows three jobs; the review appears exactly as it does today, inline comments on the lines the findings name and the summary naming the commit; the review job's "GITHUB_TOKEN Permissions" block in its own log lists `Contents: read` and nothing else.
2. Add a step to the review job that posts a comment with `${{ github.token }}`, push, and ask for a review. Expect 403 and a red run. Remove the step. This is the only check that shows the boundary is real rather than declared.
3. Set the review job's `timeout-minutes` to 1, push, and ask for a review. GitHub kills the job mid-agent, no reason file crosses, and the publishing job posts the comment saying the run failed with no reason. Restore it.
4. Force the 422: edit `attachable` in `coral/diff.py` to shift every line anchor past the end of its file, push, and review a change with a line finding. Expect one review carrying every finding in its summary, and the warning holding GitHub's 422 body in the publishing job's log rather than the review job's. Revert.

The existing "Failure" check 1 loses "a report-step log line saying the review step already reported" — there is no such line, because one job posts. The existing "Posting" check 2 is the check rewritten as 4 above and comes out of that group.

## Implementation plan

1. **Save this plan** as `.agents/docs/plans/2026-08-07-11-42-010-shrink-what-a-compromised-agent-gets.md`.
2. **Rebuild `coral/github/post.py`** — `Payloads`, `payloads`, `write_payloads`, `read_payloads`, `submitted`, two keys out of `review_payload`, the new `post_review` signature — and extend `tests/test_post.py`.
3. **Add `payloads_path()` and `reason_path()`** to `coral/runner.py`, remove `reported_path()`, and rewrite the four crossing docstrings. Update `tests/test_runner.py`.
4. **Rename `coral/report.py` to `coral/publish.py`** with `git mv`, narrow `owed`, write `publish()`, and rename `tests/test_report.py` to `tests/test_publish.py`.
5. **Change `coral/review.py`** — one credential, the whole body in one `try`, the payload written, the reason written, no client — and `coral/environment.py`'s docstrings.
6. **Wire `coral publish`** in `coral/cli.py`, rename `actions/report/` to `actions/publish/`, and drop `github-token` from `actions/review/action.yml`.
7. **Rewrite `.github/workflows/coral.yml`** as three jobs.
8. **Run** `uv sync --frozen`, `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`, `uv run pytest` — all clean.
9. **Live checks** 1 through 4, plus the "Posting" and "Failure" groups re-run, since every path in both crosses a job boundary now.
10. **Documentation updates** below; roadmap item 10 status to `built`.

## Not doing

- **Narrowing `resolve` and `publish`.** Neither runs an agent, so a scope either holds is not a scope an injected agent reaches, and each one stripped is a new way for a run to fail — `contents: read` in particular is what the GraphQL conversation query may be resting on.
- **Taking the OpenRouter key out of the review job.** It is the job making the model calls. Item 11 makes the key worth less; nothing makes it absent.
- **Sandboxing the agent.** Item 12. This item bounds what a compromised agent gets; that one stops it getting anything.
- **Composing the review body in the publishing job.** It would mean the review object and the added-line set crossing the boundary, which puts the anchor decision in a job with no checkout to check it against.
- **Stamping the marker in the publishing job.** The marker is inside each body, so the commit it records is still composed in the agent's job, and a compromised agent can name a commit Coral never reviewed and suppress one future automatic review. Finding 2 of `.agents/docs/reviews/2026-08-07-09-29-001-correctness-security-and-practices.md` is where the marker's forgeability gets settled, for every author rather than only this one.
- **Signing or checksumming what crosses.** The artifact is written and read inside one run by jobs that trust the same runner service, and the party the signature would defend against is the party holding the key.
- **Caching Coral's virtual environment across the three jobs.** A cache the review job can write is a way for a compromised agent to put its own code in the resolve and publish jobs of a later run, which are the jobs holding the write scopes. Three installs per run is the price of not offering that.
- **Naming the failed job in the comment.** Item 8's reasoning is unchanged: the run link is one click from the same answer.
- **Reporting a setup failure.** There are three setups now and none of them can report its own failure — there is no Coral to run. Visible in the Actions tab and nowhere else.
- **One artifact per file.** The publishing job downloads a conversation it never reads. It is a few hundred kilobytes inside one run.
- **Adding the three `timeout-minutes` to the numbers item 9 settled.** They are backstops against a hung runner, not values a run measures.

## Documentation updates

`.agents/docs/architecture.md`:

- "The Run" is rewritten from five steps to three jobs: what each job holds and why, what crosses as a job output and what crosses as an artifact, that the review job hands over the two finished bodies rather than the review object, and that the publishing job stamps `commit_id` and `event` itself. The setup bullet keeps its reasoning and gains the cache one: three virtual environments per run rather than one shared through a cache the agent's job could write.
- "Rules That Hold Everywhere": the not-a-sandbox bullet says what the agent's own job holds — the OpenRouter key and a `contents: read` token — instead of resting on secrets being unreachable. A new bullet says what a compromised agent can still choose: the text of the review the publishing job posts, and the marker inside it. The token bullet becomes per-job.
- "The Codebase": `coral/publish.py` and `actions/publish/` in place of the report pair; three subcommands renamed to `resolve`, `review`, `publish`; `coral/runner.py` and `coral/github/post.py` gain a clause each for what crosses a job boundary.
- Trimmed first, to stay under 1,500: the clause on line 10 justifying the upstream provider by naming where it was read, and the second half of the setup step's justification, which explains a step layout the three jobs replace.

`.agents/docs/testing.md`: the four checks above as a group; "Failure" check 1 loses the report-step log line; "Posting" check 2 moves into the new group. Trimmed first, to stay under 1,500: the sentence under "The Test Repository" restating the conversation check that "Reading the conversation" and `development.md` both already carry, and the wordier halves of the walking-skeleton checks.

`.agents/docs/development.md`: `publish` in place of `report` in the subcommand list. Under "Environment", `GITHUB_TOKEN` is scoped per job and never reaches the review step, and `coral review` deletes one credential rather than two.

`.agents/docs/roadmap.md`, item 10: status `built`, and the bullets cut to what item 11 and item 12 are written against — that the OpenRouter key is referenced only by the review job, and the README's credit limit. The mechanics go to `architecture.md`, which owns them.

`.agents/docs/functional-requirements.md`: no change.

`README.md`: the paragraph saying the model is not wired up is replaced by what a run actually does. Step 2 tells the installer to set a credit limit on the OpenRouter key, since that limit is the only bound on what an exfiltrated key can spend. The `permissions:` bullet says the called workflow narrows these per job and that the job running the agent gets `contents: read` alone.

## Validation

- The five commands, all clean.
- The done condition is live check 1: a real review in `kkestell/coral-test` posts everything it posts today, the review job's log shows a read-only token, and the run is green. Check 2 is the half that check 1 cannot show.
- The "Posting" and "Failure" groups re-run, because the anchor demotion, the 422 retry, and every failure comment now cross a job boundary to reach the pull request.

## Follow-up

- Item 11 mints its key in the resolve job and hands it to the review job. The channel it needs — a job output from resolve — is built here for `proceed` and the head SHA, and a third is one line.
- Finding 1 of `.agents/docs/reviews/2026-08-07-09-29-001-correctness-security-and-practices.md` closes for the job token: it is no longer in the review step's environment and no longer writes anything. The OpenRouter half stays open, and `architecture.md` says so rather than claiming the secrets are unreachable.
- Three installs and two artifact round trips per run cost wall-clock time. The live checks are the first measurement of how much, and if it is large the answer is a smaller install rather than a shared cache.
