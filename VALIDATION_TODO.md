# Validation still owed for roadmap item 10

Item 10 split the run into three jobs. Its own live check group passed in full. What remains is
re-running the two earlier groups whose paths now cross a job boundary to reach the pull request.

`.agents/docs/testing.md` holds the checks themselves; run them from there rather than from the
summaries below. `.agents/docs/development.md` has the `gh` commands.

## Passed

- "Shrink what a compromised agent gets" 1 through 4. Three jobs run green, the review job's log
  lists `Contents: read` and nothing else, a token write from that job answers 403, a job GitHub
  kills mid-agent gets the reasonless failure comment, and a forced 422 demotes every finding with
  the warning in the publishing job's log.
- "Posting" 1 and 2. Inline comments land on the lines the findings name, and a pull request closed
  mid-review gets nothing, with the log line now coming from the publishing job.
- "Failure" 4. A run that succeeds posts one review and no comment beside it.

## Still to run

- "Posting" 3 — ask again on a clean pull request with no new commits. The second review has to say
  everything is already said rather than that there was nothing to find.
- "Failure" 1 — the deadline fires. One comment carrying the elapsed seconds and the budget inside
  the fence, and a red run. The reason now reaches the comment as an artifact rather than from the
  step that raised, so this is the check that exercises the reason file.
- "Failure" 2 — `resolve()` raises. One comment with no reason and a link to the run, red. Then a
  mid-sentence `/coral` in the same state: red, no comment.
- "Failure" 3 — a broken `OPENROUTER_API_KEY` on the test repository. One comment carrying the
  provider's own error inside the fence.

## The test repository as it stands

`kkestell/coral-test` is disposable, so none of this needs preserving.

- 25 (`check-010-1`) open, carrying reviews and failure comments from the checks above.
- 26 (`check-010-4`) closed, spent on "Posting" 2.
- 27 (`check-010-4b`) open, carrying the demoted review from the forced 422.

"Failure" 1 and "Posting" 3 each need a pull request Coral has not reviewed, since a commit it has
already reviewed produces nothing to work with.

## Delete this file

It describes one item's unfinished validation. Once the checks above have run, delete it.
