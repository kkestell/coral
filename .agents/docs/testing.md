# Testing

How Coral is checked.

## Unit Suite

- `tests/` contains one `test_<module>.py` per module under test.
- Unit tests use real local files and Git repositories but no network, credential, model call, or
  Docker container.
- Focused run: `uv run pytest tests/test_local.py`.
- Full run: `uv run pytest`.

## Real CLI Check

- A real check runs `uv run coral [scope]` from a disposable fixture repository with a valid
  settings file and Docker running.
- Use at least two reviewers to check concurrency and use different reviewer and verifier model or
  effort values to prove each configuration reaches its intended run.
- Check fallback with more `review_agents` entries than `num_reviews` and an unreachable model
  among them: stderr names the failed reviewer and the entry that replaced it.
- Read stdout as the artifact: it must contain one complete Markdown review and no progress lines.
- Read stderr for the selected models, container actions, verifier dispositions, and failures.
- Watch the table in a real terminal: turns and costs climb per agent, the verifier's row appears
  when it starts, the shell prompt above the run stays intact, and the final table is left above
  the review.
- Inspect each agent container during a deliberately paused run to confirm the OpenRouter key is
  absent and reviewer scratch state is isolated.
- A unit suite cannot prove model behavior, OpenRouter compatibility, Docker isolation, concurrent
  timing, or stream separation. The roadmap's done condition requires the real check.
