# Functional Requirements

Coral's observable CLI behavior and security properties.

## Command And Scope

- `coral [scope]` reviews code in the current directory and accepts at most one optional string.
- An explicit scope reaches every reviewer unchanged. Coral does not parse or reinterpret it.
- With no scope, uncommitted staged, unstaged, or non-ignored untracked changes are the scope.
- With no uncommitted changes, the most recent commit is the scope.
- With no commit, or outside a Git repository, the whole codebase is the scope.

## Configuration

- Coral reads all configuration from `~/.config/coral/settings.json` and accepts no configuration
  from command-line options or environment variables.
- The file contains `openrouter_api_key`, a non-empty `review_agents` array, `num_reviews`,
  `max_concurrent_reviews`, one `verification_agent`, `time_budget_minutes`, and
  `spend_cap_dollars`.
- `num_reviews` and `max_concurrent_reviews` are whole numbers of at least one. A `num_reviews`
  larger than the number of `review_agents` entries stops the review.
- Every agent entry contains an exact OpenRouter `model` name and an `effort` string. An empty
  effort leaves the provider's default in place.
- A moving OpenRouter model alias is refused, and a model absent from OpenRouter's listing stops
  the review.
- Coral uses the configured API key directly. It does not accept a management key or mint keys.

## Review Runs

- Coral produces `num_reviews` reviews, drawing models from `review_agents` in order and running
  at most `max_concurrent_reviews` reviewers at a time. Every reviewer receives the same scope.
- A reviewer that fails is replaced by the next unused `review_agents` entry, so entries past
  `num_reviews` are fallbacks. No model is tried twice.
- Running out of entries with at least one review continues to verification with the reviews
  produced. No review at all stops the command.
- Each reviewer receives a fresh checkout and disposable resource-bounded container with a shell,
  network access, and no OpenRouter credential.
- A Git checkout copy contains its current commit, tracked working-tree state, and non-ignored
  untracked files. Git-ignored files do not enter the copy.
- Reviewer scratch files and processes do not reach another reviewer, the verifier, or the user's
  working directory.
- Reviewers report correctness, security, and performance defects. Style, naming, structure,
  documentation, and test coverage alone are not findings.
- Every finding has low, medium, or high severity and names a line, span, file, or the reviewed
  scope as a whole.
- A reproduced finding carries the complete regression test and its focused command. A finding
  without a reproduction is marked speculative.

## Verification And Output

- One separately configured verifier receives the scope, every reviewer summary, and every
  proposed finding against its own fresh checkout.
- The verifier rules on every proposed finding, rejects duplicates, and writes the final summary.
- Only confirmed findings appear in the final review. A missing, conflicting, or rejecting verdict
  drops its finding.
- A successful command writes one Markdown review to stdout and progress to stderr.
- While the review runs, stderr carries a table of every started agent's model, model turns, and
  measured cost, over a header naming the reviewed directory and a footer of elapsed time and total
  cost.
- The table is redrawn over its own previous lines, never on the alternate screen, so earlier
  terminal contents survive and the final table remains in the scrollback above the review.
- A progress or failure line prints above the table. A stderr that is not a terminal receives the
  table once, when the review ends.
- The review contains the verifier's summary, every confirmed finding and its evidence, and the
  measured total model cost. An empty review says Coral found nothing to report.
- The configured time budget and spend cap cover every reviewer and the verifier together, and a
  reached limit stops the command rather than falling back to another model.
- A reached limit, unpriced model response, malformed configuration, failed verifier, or reviewer
  list exhausted without one review discards the review and exits nonzero with one error on
  stderr.
