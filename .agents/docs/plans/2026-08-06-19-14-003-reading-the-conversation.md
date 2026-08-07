# Reading The Conversation

Roadmap: item `3`, `Reading the conversation`.

## Research

- `.agents/docs/research/github-api-contract.md` — the GraphQL query, field by field, run against a real pull request; that no connection accepts more than 100 items; that neither `reviews` nor `reviewThreads` accepts an ordering argument and a thread carries no timestamp; that requesting comments under both `reviews` and `reviewThreads` returns each inline comment twice; and that 94 of 100 reviews on a busy pull request have an empty body.
- `.agents/docs/research/code-structure.md` — state crossing a step boundary as a path on disk.

Three things were checked against the live API while this plan was written, because the plan leans on them and the research does not state them.

- `IssueComment`, `PullRequestReview`, `PullRequestReviewComment`, and `PullRequestReviewThread` all carry `id`. The bound needs a per-comment identity to select on, and that is it.
- Paging backwards works as the research assumed. `reviews(last: 100)` on `cli/cli` 10513 returned the 100 newest of 117 with `hasPreviousPage: true`, and the same query with `before:` set to the returned `startCursor` returned the remaining 17, every one of them older than the oldest of the first page.
- `IssueCommentOrderField` has exactly one value, `UPDATED_AT`. There is no way to ask GitHub to order issue comments by creation time, so the query does not ask for an order at all and takes the connection's default, which is observed to be creation order ascending.

## Goal

Coral reads the pull request's conversation, bounds it, and hands back a typed object that later items consume without touching GitHub again. The same fetch produces the set of commits Coral has already reviewed, which is the whole of Coral's memory and the reason there is no datastore.

The deliverable is `coral/github/conversation.py`, called by `coral resolve`, writing the conversation to the runner's temporary directory, plus the marker work that makes Coral's own past comments recognizable as Coral's.

Satisfies TR-31, TR-32, TR-33, and TR-34, and gives FR-14 and FR-15 their data. It builds none of the behavior that reads the data: the already-reviewed gate is item 4, deciding whether a past finding still stands is item 6, and saying what went unread inside a real review body is item 6 as well.

Two things can only be learned from a run, and this item is where they get learned.

- Whether the job's token reaches `reviewThreads` over GraphQL with `contents: read`, `issues: write`, and `pull-requests: write` and nothing else. The research left this open: GitHub publishes fine-grained permission requirements per REST endpoint and publishes nothing equivalent for GraphQL, and `reviewThreads` has no REST counterpart to borrow a requirement from.
- Whether the resolution and staleness flags say what the design assumes when a real thread is resolved and when the code under a real thread moves.

## Approach

### The unit the bound counts is a comment, and every comment has a timestamp

TR-32 bounds the conversation at the 200 most recent comments and 400,000 characters. It does not say what a comment is, and the three connections make that a real question.

A comment is one piece of prose a person wrote: an issue comment, a review whose body is not empty, or a comment inside a review thread. A review with an empty body is an envelope GitHub created to hold a single inline comment, and 94 of the 100 reviews the research measured were exactly that. Counting those as discussion would spend the bound on nothing, so an empty-bodied review is not a comment and is not shown to the agent. It is still read for its marker, which is the next section.

Every comment in that sense carries a timestamp, which is what makes a single global ordering possible: `createdAt` on an issue comment and on a thread comment, `submittedAt` on a review. Only the *thread* has no timestamp, and a thread does not need one, because a thread is kept when a comment inside it is kept.

So the bound is: gather every candidate comment, sort by timestamp newest first, and take comments until there are 200 of them or until the next one would carry the total past 400,000 characters. Timestamps are compared as the strings GitHub returned, which is correct because they are ISO-8601 in UTC with a `Z` suffix and sort lexically.

Rebuilding after the selection keeps the structure. An issue comment or a review survives if it was selected. A thread keeps the comments that were selected and is dropped when none of them was. A thread that survives keeps its flags, its path, and its lines whole, because those are what item 6 reads to decide whether a finding still stands.

### Paging, and what "most recent" is worth

The first query asks all three connections for their newest 100, which is the research's query and covers most pull requests in one round trip. A connection that reports `hasPreviousPage` and has not yet yielded 200 comments is paged backwards once more with `before:` set to its `startCursor`, one small query per connection, capped at four pages so a pull request carrying a thousand empty reviews cannot walk the whole history.

The rule is per connection rather than global, and it has to be. The bound takes the 200 most recent comments across all three connections, so a comment can only be missed if its own connection was not paged deep enough to offer it. A connection that has already offered 200 candidates cannot be hiding one that belongs in the answer.

`last:` returning the newest is observed rather than promised, and for review threads it is the only handle on recency that exists. This goes in a comment where the code does it. For issue comments the same is true for a different reason: GitHub's only ordering field for them is `UPDATED_AT`, which would sort an ancient comment edited yesterday above one written last week, so the query takes the default order instead and pays for it with the same caveat.

### Coral recognizes its own work by the marker, and now every comment carries one

TR-33 puts the marker at the top of every review body. That is enough to answer "which commits have I reviewed", and it is not enough to answer "which of these comments did I write", which is what FR-7 needs in item 4 and what FR-14 needs in item 6.

The author login cannot answer it. Coral posts as the repository's automation, so every other bot in the repository shares that login, which is why FR-27 exists at all.

So the marker goes on every comment Coral posts, not only on the review body. That is one line in `coral/github/post.py`, prepending the marker to each inline comment's body, and it makes recognition local: a comment is Coral's when its body carries the marker, wherever the comment sits.

The set of already-reviewed commits still comes from review bodies alone. An inline finding and, later, item 8's failure comment both carry a marker naming a commit, and neither means that commit was reviewed — a failure comment means the opposite. Reading the set from the reviews connection only keeps that distinction free rather than encoding it in the marker.

Markers are read from every review the fetch returned, before the bound and before the empty-body filter. Coral's memory must not be a function of how much other people talked.

### The conversation crosses the step boundary as a file

TR-34 already says so, and item 2 built the mechanism for the pull request. `coral/runner.py` gains `conversation_path()` beside `pull_request_path()`.

Reading it back needs the frozen dataclasses reconstructed, and `pydantic.TypeAdapter` does that without a hand-written codec. Pydantic is already a dependency, and it is the same validator the agent framework runs over the review object, so the project has one answer to "JSON into a frozen dataclass" rather than two.

### Where the fetch sits in the resolve step

The order becomes: fetch the pull request, write it, fetch the conversation, write it, react, then the gates.

The reaction moves after the conversation fetch, which reverses what item 2 built. TR-27 has the reaction going to every qualifying request in the conversation rather than only the one on the triggering payload, and that needs the conversation in hand. Item 4 is what changes which comments get reacted to; putting the fetch ahead of the reaction now means item 4 changes one function and not the shape of the step.

The gates stay behind both. TR-30 says each stop comes before the work it would make pointless, and the work that is worth stopping is the checkout and the agent, not one or two GraphQL calls. A conversation fetch that fails takes the run down with it and leaves the request unacknowledged, which is one of the cases item 8's report step exists to cover.

### Proving it on a pull request rather than in a log

Nothing in this item reads the conversation for its meaning yet, so nothing would show on a pull request. The review step's hardcoded summary is changed to report what was read: how many comments, reviews, and threads survived the bound, how many went unread, and which commits the markers name. Item 5 replaces that summary with the agent's, and until then every live check leaves its evidence where `.agents/docs/testing.md` says evidence belongs.

## Related code

- `coral/github/client.py` — the one authenticated transport, currently REST only. It gains a `graphql` method. GraphQL answers with HTTP 200 and an `errors` key when the query fails, so the status check the client already does sees nothing wrong and the error check has to be its own.
- `coral/github/marker.py` — `marker` and `reviewed_commit`, written in item 2 with no caller. This item is the caller.
- `coral/github/post.py` — the marker moves onto each inline comment as well as onto the review body.
- `coral/resolve.py` — gains the fetch and the write, and the reaction moves behind them.
- `coral/review.py` — reads the conversation file and reports what it holds.
- `coral/runner.py` — gains `conversation_path()`.
- `coral/schema.py` — the pattern to follow for frozen dataclasses that pydantic validates.
- `.agents/docs/code-style.md` — name the shape rather than nesting containers, no quiet fallbacks, `Final` constants for tuning values, and boundary sanity meaning malformed external input produces a message rather than a traceback.

## Current state

- `coral/github/conversation.py` does not exist. `coral/github/client.py` speaks REST and nothing else.
- `coral/resolve.py` fetches the pull request, reacts to the triggering comment, writes the pull request verbatim, and gates on the pull request being open.
- `coral/review.py` reads the pull request back, computes the diff, and posts one hardcoded finding.
- `coral/github/marker.py` is written and unused.
- The tests are `tests/test_diff.py`, `tests/test_runner.py`, and `tests/test_marker.py`. There is no fixture directory and no mocking library.
- `kkestell/coral-test` has Coral installed on its default branch, pinned at `@main`, and item 2's five live checks passed there.

## Test plan

Everything decided without the network is a unit test over a captured response. Everything else is a live run.

**Key behaviors to verify**

- Parsing a captured response yields the three kinds of comment with the author association preserved on each, and the thread's `isResolved`, `isOutdated`, `path`, `line`, and `subjectType` preserved whole.
- A review with an empty body does not become a comment and does not reach the agent.
- The bound takes the 200 most recent comments across all three connections rather than 200 from each, and reports the rest as unread.
- The character bound binds first when the bodies are long, and the comment bound binds first when they are short.
- A thread survives when one of its comments survives, keeping its flags, and disappears when none of them does.
- The already-reviewed set comes out of the markers on every review fetched, including a review the bound dropped and a review whose body is otherwise empty.
- A comment whose body carries the marker comes back as Coral's; one that does not comes back as somebody else's.
- A conversation written to disk and read back through `pydantic.TypeAdapter` equals the one that was written.
- The paging predicate asks for another page when the connection has more and has not yet yielded 200 comments, and stops at the page cap.

**Errors and failures**

- A response carrying an `errors` key raises with the messages in it, rather than a `KeyError` on `data` several frames later.
- A comment whose author account was deleted parses with no author rather than crashing. GitHub returns `author: null` for it, and the association is still there.
- A review with no `submittedAt` is unsubmitted, is visible to nobody but its author, and is skipped rather than sorted with a missing key.

**Edge cases**

- A pull request with no conversation at all yields empty lists, an empty already-reviewed set, and a bound reporting nothing dropped.
- A thread holding more comments than were fetched reports the remainder as unread. That truncation is the `first: 20` inside the thread and is not the same thing as the global bound.
- Two comments carrying the same timestamp both survive; the sort is stable and neither displaces the other.
- A thread whose `line` is null, which is what an outdated thread against a deleted line looks like, parses.

**What NOT to test**

- What GitHub returns. The captured response in the test is captured, and whether GitHub still produces it is what a live run finds out.
- `httpx` and the transport.
- The permission GraphQL requires. That is not a test, it is the live check below.

**Live checks**

The first is against a public repository from a developer machine and writes nothing. The rest are in `kkestell/coral-test` and are read off the pull request.

1. Fetch the conversation for `cli/cli` 10513 by hand, with a token from `gh auth token`. That pull request carries 117 reviews and 84 threads, so it forces the second page on the reviews connection and exercises the bound against real prose rather than against a fixture. What comes back: 84 threads with most of them resolved and outdated, the bound reporting comments it left out, and no already-reviewed commits, because Coral has never reviewed it.
2. Open a pull request in `kkestell/coral-test`. Coral's review says it read a conversation of nothing. This is the GraphQL permission question: if the job's token cannot reach `reviewThreads`, this is where the run goes red.
3. Comment `/coral` on that pull request. The second review says it read the first review's marker, naming the commit, and counts the comment that asked.
4. Reply to Coral's inline finding, then resolve the thread, then comment `/coral` again. The third review reports the thread as resolved, reports the reply as somebody else's, and reports Coral's own finding as Coral's.
5. Push a commit that changes the line under Coral's finding and comment `/coral`. The review reports that thread as outdated, which is the flag FR-14 spends in item 6.

## Implementation plan

1. **Add `graphql` to `coral/github/client.py`.** One method taking a query and a variables dictionary, posting `{"query": ..., "variables": ...}` to `/graphql` through the existing `_request`, raising on an `errors` key, and returning `data`. The comment says why the error check exists: GraphQL reports a failed query with HTTP 200, so the status check above it sees a success.

2. **Write the dataclasses in `coral/github/conversation.py`.** `Comment` for an issue comment, carrying `id`, `author: str | None`, `association`, `body`, `written_at`, and `mine`. `PastReview` adding `state` and `commit: str | None`. `ThreadComment` adding `outdated` and `original_line: int | None`. `Thread` carrying `id`, `path`, `line: int | None`, `start_line: int | None`, `diff_side`, `subject_type`, `resolved`, `outdated`, `comments`, and `total_comments`. `Bound` carrying `read`, `unread`, and `oldest_read: str | None`. `Conversation` carrying the three lists, the `Bound`, and `reviewed_commits: list[str]`. An association stays a `str` rather than a `Literal`, because an enum value GitHub adds later is not a reason for Coral to crash.

3. **Write the queries.** GraphQL fragments hold the field list for each of the three node types, so the first-page query and the three page-back queries share one definition of what a review, a thread, and a comment are. The first-page query is the research's, with `id` added to every node and `orderBy` removed from the issue comments connection, plus `rateLimit { cost remaining nodeCount }`. Each page-back query asks for one connection, takes a `$before` cursor, and aliases the connection to `connection`, so one helper reads the result whichever of the three it asked for. Every number in them is a module-level `Final`: 100 per page, 20 comments per thread, 200 comments, 400,000 characters, 4 pages.

4. **Write the parsing.** One function per node type, each taking the connection's `nodes` and returning the dataclasses. `mine` is `marker.reviewed_commit(body) is not None`. A review with an empty body or no `submittedAt` yields nothing. A thread's `total_comments` comes from the connection's `totalCount` inside it. Nothing here reaches for a default: a field the query asked for is a field the response has, and a missing one is a broken query rather than an input to recover from.

5. **Write the fetch.** `fetch_conversation(github, owner, repo, number)` runs the first-page query, parses all three connections, reads every review body for a marker, and then pages each connection backwards while it reports a previous page, has yielded fewer than 200 comments, and is under the page cap. It returns a `Fetched` — the three lists, the already-reviewed commits, and a count of nodes the connections reported beyond what was paged — and the bound is a separate function so it is testable without a network. One log line reports the rate limit cost and node count, which is what item 9 will want when the numbers get settled.

6. **Write the bound.** `bound(fetched) -> Conversation`. Flatten every comment to its id, timestamp, and length; sort newest first; take until 200 comments or until the next would pass 400,000 characters; rebuild the three lists from the surviving ids, keeping each list in ascending time order and dropping a thread whose comments all went. `Bound.unread` counts the candidates that lost, plus the comments inside a thread beyond the 20 fetched, plus the nodes the connections reported and nobody asked for. That last term counts an empty-bodied review as an unread comment, which overstates slightly, and the comment in the code says so: overstating what went unread is the safe direction for a promise FR-15 makes to a reader.

7. **Write the file functions.** `write_conversation(path, conversation)` and `read_conversation(path)` over `pydantic.TypeAdapter(Conversation)`, and `runner.conversation_path()` returning `$RUNNER_TEMP/coral/conversation.json`.

8. **Put the marker on every comment Coral posts.** In `coral/github/post.py`, both anchored branches prepend `marker(commit)` and a blank line to the finding's body. The review body is unchanged.

9. **Wire it into `coral/resolve.py`.** Fetch the conversation after the pull request, write it, then react, then gate. Log one line saying what was read and how many commits Coral has already reviewed.

10. **Report it from `coral/review.py`.** Read the conversation back and put its counts, its unread figure, and its already-reviewed commits into the hardcoded summary. This is what makes every live check visible on the pull request, and item 5 deletes it.

11. **Write `tests/test_conversation.py`** to the test plan. The input is one GraphQL response captured from `cli/cli` 10513 and trimmed by hand to a few nodes of each kind, held inline in the test with a comment saying where it came from, plus payloads built in the test for the cases the real one does not contain — a deleted author, an unsubmitted review, a thread with no surviving comment, and bodies long enough to make the character bound bind first.

12. **Run the live checks** in order, and read each one off the pull request.

13. **Update the documents** listed below, and set the roadmap's item 3 status.

## Not doing

- **Rendering the conversation into the agent's prompt.** Items 5 and 6. The conversation's shape is the dataclasses and its transport is the file; the prose form of it belongs beside the prompt that frames it, and writing it now would mean writing it twice.
- **Recognizing `/coral` and reacting to every request in the conversation.** Item 4. The fetch now sits ahead of the reaction so that item changes one function.
- **The already-reviewed gate.** Item 4. This item produces the set of commits; nothing stops a run on it yet.
- **Deciding whether a past finding still stands.** Item 6. The flags that answer it are fetched and reported and nothing reads their meaning.
- **Saying what went unread inside a real review body.** Item 6 writes the sentence FR-15 asks for. The number it needs is on the `Bound` today, and the placeholder summary prints it.
- **`isCollapsed`, `resolvedBy`, and `diffHunk`.** Collapsed is what resolved or outdated already implies, who resolved a thread changes no decision Coral makes, and the diff hunk is a copy of code the agent has in the checkout.
- **Comments under `reviews`.** Every inline comment is reachable through its thread, the resolution and staleness flags live only on the thread, and asking both ways returns each one twice.
- **Retrying a rate-limited or failed GraphQL call.** A failure takes the run down and item 8 reports it. A retry policy written before a single rate limit has been observed is a guess.
- **A fixture directory.** One captured response inline in one test file is not a corpus.

## Documentation updates

Requirements to correct in `.agents/docs/technical-requirements.md`:

- **TR-31** says the conversation is fetched in one query. It is one query for a pull request whose connections each hold 100 items or fewer, which is most of them, and one further query per connection that has more and has not yet offered enough comments to satisfy the bound. Say that, and say that the connection cap is 100 so any bound above it costs a round trip.
- **TR-32** bounds the conversation at 200 comments and 400,000 characters without saying what a comment is. It is an issue comment, a review with a body, or a comment inside a review thread; a review with an empty body is an envelope around an inline comment and is not discussion. The 200 are the most recent across all three connections rather than 200 from each, a thread is kept when a comment inside it is kept, and the count of what went unread is deliberately generous.
- **TR-33** puts the marker on every review Coral posts. Extend it: every comment Coral posts carries the marker, including each inline finding, because the author login belongs to the repository's automation and cannot tell Coral's comments from anything else that account writes. The set of already-reviewed commits is still read from review bodies alone, so an inline finding and a failure comment naming a commit never claim that commit was reviewed.

New requirement:

- **TR-67** — Ordering in the conversation is only as good as GitHub's connections allow. Neither `reviews` nor `reviewThreads` accepts an ordering argument, and the only ordering field for issue comments is `UPDATED_AT`, which would rank an edited old comment above a newer one. So all three take the connection's default order and `last:` is trusted to return the newest, which is observed and not promised. Every comment carries a timestamp of its own and the bound sorts on that; a review thread carries none, and its recency is the recency of the comments inside it.

Invariants to record in `.agents/docs/architecture.md`:

- Coral recognizes its own work by the marker on the comment, never by the author login, which belongs to the repository's automation and is shared with everything else it posts.
- The set of commits Coral has already reviewed is read from review bodies only, and is computed from every review fetched rather than from the bounded conversation, so Coral's memory does not shrink when other people talk.
- The conversation is bounded by comments and characters, and a review thread survives the bound when a comment inside it does, with its resolution and staleness flags whole.

Other documents this change makes wrong:

- `.agents/docs/architecture.md` — the Codebase Map marks `coral/github/conversation.py` as not built. "How It Fits Together" says the resolve step fetches the conversation after the gates and reacts last; the order is now the pull request, the conversation, the reaction, and then the gates, because the reaction is going to need the conversation and one GraphQL call is not the work worth stopping.
- `.agents/docs/testing.md` — the live checks are item 2's five. They gain this item's, and the section describing the test repository gains the one kind of live check that does not run there: a read-only fetch against a public pull request, which is allowed because it writes nothing and because no pull request in `kkestell/coral-test` will ever carry 117 reviews.
- `.agents/docs/development.md` — gains the one-line invocation that runs the conversation fetch by hand against a public pull request, under "Commands" or beside it, since it is the only way to exercise paging.
- `.agents/docs/roadmap.md` — item 3's status.

## Validation

- Tests: `tests/test_conversation.py`, run with `uv run pytest`.
- Commands: `uv sync --frozen`, `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`, `uv run pytest`. All clean.
- The five live checks above, the first from a developer machine and the rest in `kkestell/coral-test`, read off the pull requests.
- The done condition is the roadmap's: the conversation for a real pull request round-trips into the shape the agent will be given, the bound reports what it dropped, and the set of already-reviewed commits comes back out of the markers. Check 1 is the first half, check 3 is the second.

Iterating still means pushing to `main` on `kkestell/coral`, which is the branch the example file pins.

## Follow-up

- Item 4 reacts to every qualifying request in the conversation. It has the conversation and it has `mine`, and what it still needs is the parse of `/coral` and a way to tell which comments already carry Coral's reaction. Nothing in this item fetches reaction state, and the cheapest place to get it is a `reactions` selection on the same query rather than a REST call per comment.
- Item 8's failure comment is an issue comment. Giving it a marker makes it recognizable as Coral's under this item's rule, and it will not be mistaken for a review of the commit it names.
- Item 9 settles the two numbers this item spends. The rate limit line the fetch logs is the measurement, and `cli/cli` 10513 is the pull request that will show whether 200 comments and 400,000 characters are anywhere near right.
- Whether the job's token can reach `reviewThreads` is the research's open thread and live check 2 closes it. Whatever it answers goes back into `.agents/docs/research/github-api-contract.md`, which is a living document.
