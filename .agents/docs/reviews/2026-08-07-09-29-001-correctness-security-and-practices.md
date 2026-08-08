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

---

## Holds up

Read adversarially and found correct: the deadline arithmetic and the reviewer's slice of the step;
the two-run split and the rule in `confirmed` that a finding no verdict names is dropped; the fork
and closed-state gates in `resolve`; the composition in `signed` and `review_payload` and the
unconditional demotion behind a 422; the fence tracking in `asks_for_review`; and the handoff
between the review step's own failure path and the report step through `reported_path`.
