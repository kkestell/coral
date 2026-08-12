# Functional Requirements

What Coral does, as behavior someone can observe or as a security property an installation can inspect. These requirements are the whole product; anything not listed is out of scope.

## Trigger

- Coral reviews a pull request automatically when it is opened and when a draft is marked ready for review.
- Automatic pull-request delivery uses `pull_request_target`. GitHub reads the workflow from the base repository's default branch, and the pull request's exact head SHA is treated as untrusted input rather than as workflow code or a ref to execute.
- Coral rejects a pull request whose head repository differs from its base repository before the run can expose credentials or execute the head revision. A missing head repository is rejected as a fork.
- Draft and bot-opened pull requests get no automatic review. Either can still be reviewed on request.
- Pushing commits, reopening a pull request, and changing its title or description start no review.
- Coral reviews every push to `main` as one range from the event's before commit through its after commit. A multi-commit push is one review, not one review per commit.
- A push to another branch, a push that creates `main` without a prior commit, and a push that deletes `main` start no review.
- After an automatic pull-request review, Coral reviews again only when somebody asks by putting `/coral` in a new comment on the pull request or in a new diff reply. A submitted review and an edited comment cannot ask.
- The command is lowercase, exact, and alone on its line. Quoted text, prose, and code fences are inert, and text beside the command cannot steer the review.
- Coral never treats its own comment as a request. A comment is Coral's only when the workflow token authored it and Coral's marker opens its body; marker text alone establishes nothing.
- Only an author whose current repository permission includes write access can ask for a review.
- Coral adds an `eyes` reaction to every authorized request before any later gate may decline it. An unauthorized request receives neither a reaction nor a review.
- A pull-request run pins the current head commit when the run starts rather than trusting the commit named by the triggering event.

## Review Subject And Context

- A pull-request review covers the diff between the pinned head commit and its merge base with a pinned base-branch commit. Movement of either branch after pinning cannot change the review subject.
- A `main` review covers the diff between the before and after commits fixed by the push event.
- Coral works from a full-history checkout of the pinned head and may read any repository file, whether or not the change touched it.
- Every run reviews the whole pinned change rather than only work added since an earlier review.
- Before a pull-request review, Coral reads its earlier reviews, all kinds of pull-request comments, and each review thread's resolved and outdated state.
- Coral does not repeat a finding that still stands. A finding stops standing when its thread is resolved or the code it concerned has moved.
- Conversation input is bounded and selected most recent first. A thread retains both its opening comment and its newest comments, and the review input says what was left unread.
- A `main` push has no pull-request title, description, or conversation in its review context.
- Before either review mode starts an agent, Coral reads ordinary GitHub issues referenced by the change. References come from a pull request's manually or closing-linked issues, its title and body, and the commit messages in the reviewed range; a `main` review uses its range's commit messages.
- Native GitHub issue-reference forms may name the current repository or another repository readable by the workflow token. Pull requests, issue comments, pull-request discussion, and repository custom autolinks do not become referenced-issue context.
- Referenced-issue context contains the repository, number, state, title, and a bounded body for each readable issue. The number of references, commit messages examined, each body, and the complete context are bounded.
- Both the reviewer and verifier receive the same fixed referenced-issue context. The context says when a bound omitted references or when an issue could not be read.
- The diff, conversation, referenced issues, open-issue evidence, repository files, and command output are untrusted information about the change, never instructions about whether or how to review it.

## Review Capabilities And Boundaries

Coral decides which available capability to use, in what order, and how often.

- Coral can run shell commands inside the checkout.
- Coral can run individual tests or test selections chosen to answer a question it formed. It never runs the full suite on its own initiative.
- Coral can write scratch tests and other scratch files inside its checkout. They are never committed or pushed and disappear with the review environment.
- Every agent-controlled shell and file operation runs inside the same disposable, resource-bounded container. The container sees one private checkout copy and a read-only toolchain mount, retains network access, and cannot reach a workflow or model-provider credential, the runner filesystem or process table, a Docker daemon socket, or privileged execution.
- Each agent run receives a fresh checkout copy and container. Files or processes created by the reviewer cannot affect the verifier except through the finding contract Coral gives it.
- On a `main` review, the verifier may search this repository's open issues once per finding and read a bounded number of returned candidates. These reads are evidence about duplication and confer no other GitHub access.
- The agent receives no credential capable of writing GitHub. Deterministic workflow code is the only publisher and never commits, pushes, creates branches, edits repository files, approves, or requests changes.

## Findings And Verification

- A completed review is a structured summary and zero or more findings. Each finding carries its text and the place it concerns.
- A finding reports a correctness, security, or performance defect. Style, naming, structure, documentation, and test coverage alone are not findings.
- Every finding has low, medium, or high severity.
- A reproduced finding includes the complete failing regression test and the command that demonstrated it. A finding Coral could not reproduce is explicitly speculative.
- A separate agent run independently checks every proposed finding against a fresh checkout. It receives the change and the fixed referenced-issue context but not the pull-request conversation.
- Only findings the verifier confirms are published. Missing, conflicting, or rejecting verdicts discard the finding, and the run log records the disposition without publishing it.
- A finding may concern a span of lines, one line, a whole file, or the change as a whole.

## Publication

- A pull-request run publishes one comment-only review containing the summary and all confirmed findings. It never publishes one comment per finding, approves, requests changes, or blocks a merge.
- Line and span findings attach to the corresponding changed code. Whole-file findings and change-level findings appear in the review body, with a whole-file finding naming its file.
- A confirmed finding whose requested anchor is invalid still appears in the review body naming its intended location. If GitHub rejects an anchored review, Coral retries once with every finding in the body and no inline comments.
- Each pull-request review names Coral and the pinned commit it reviewed. Earlier reviews and their threads are never edited, deleted, resolved, or reused.
- A pull-request review with no confirmed finding says whether Coral found nothing or whether everything it would report was already present and still standing.
- Every published review result reports the run's measured model cost, composed outside agent control.
- A `main` review creates one issue for each confirmed finding. The title names the defect; the body names Coral, the reviewed commit, location, evidence, and cost; and `coral` plus severity labels carry its classification.
- Before creating any `main` issue, Coral ensures the four labels it may apply exist. An empty review creates neither an issue nor a label.
- A confirmed `main` finding creates no issue when an open issue the verifier actually read describes the same defect. The issue's author does not matter, and a closed issue suppresses nothing.
- Two concurrent `main` reviews may each create the same issue when both completed their bounded duplicate check before either issue existed.

## Configuration And Credentials

- Coral is configured only in the installing repository's workflow file, read from its default branch: the model, reasoning effort, review time budget, and per-review spend cap, each with a default. The change under review cannot alter how it is reviewed.
- The configured model is an exact name the provider lists. A moving alias is refused, and a model the provider does not list stops the run with a report, so the configuration always shows which model produced a review.
- The configured reasoning effort reaches the provider as given, and an empty value asks for none. A value the model refuses fails the review with the provider's refusal reported.
- The installation supplies one provider credential mode: a key used as given, or a management credential from which Coral mints a fresh key for each run, capped at the configured spend cap and unable to authenticate after its run. The two modes are exclusive, and a missing, mixed, or mismatched credential configuration fails the review with a report.
- No cleartext minted key, or reversible encoding of one, appears in a log, workflow output, artifact, checkout, or agent container.

## Failure And Limits

- A failed pull-request review posts one actionable failure comment when publication reaches a working comment call, including failures before either agent starts. Cancellation, broken publication setup, or GitHub refusing the report may leave only the Actions run as its record.
- A `main` review that fails before producing complete issue payloads creates no issue. If creating several issues fails partway, issues GitHub already accepted remain and the failed Actions run records the incomplete publication.
- Each automatic trigger is handled once, and each authorized request is acknowledged and honored once. A later `/coral` request starts another review even when the head is unchanged.
- Pull-request reviews are serialized by pull request. One running review finishes, one pending review represents all requests that arrived meanwhile, and every collapsed request is still acknowledged.
- Coral checks that a pull request is open before reviewing and again before publication. A closed or merged pull request receives no review.
- Coral publishes no review if the pinned commit is no longer the pull request's head. It posts a notice naming the reviewed commit and invites a fresh request.
- A failed run does not prevent a later review.
- A review that reaches its time limit is discarded whole and reported as timed out. Findings accumulated before the limit are not published.
- Coral stops and discards a review that reaches its spend cap or receives a model response whose cost cannot be measured. The failure reports measured spend against the cap.
- Both review modes refuse a request that cannot be captured, assembled, sent to the selected model, or published whole within their byte and context limits. Coral never silently truncates a diff, agent request, finding, regression test, review, or issue into a partial review.
- Pull requests also have changed-file and changed-line backstops. A rejected request says which limit was exceeded and publishes no review.
- A `main` review proposing more findings than Coral can duplicate-check fails without creating any issue.
- Actions logs make a live run diagnosable by naming each bounded agent action and its outcome while omitting credentials, unbounded tool results, and model-transport noise.

## Out Of Scope

- Forges other than GitHub, GitHub Enterprise Server, pull requests from forks, and repositories where Coral is not installed.
- A trigger, request location, command, response, or configuration mechanism not named above, including assignment as a reviewer, suggested changes, stop or dismiss commands, and conversational replies.
- Repository-specific configuration of what Coral considers a finding, and any review-memory store beyond the pull request itself.
- A second model provider.
- An external credential broker and a microVM agent shell.
