# 🪸 Coral

Coral is a command-line code review agent. It runs configured reviewers concurrently, asks a
separate agent to verify their findings, and prints the final review as Markdown.

## Install

Coral requires Python 3.13 or newer, `uv`, and a running Docker daemon.

```sh
uv tool install .
```

For development, use `uv sync` and run the checkout with `uv run coral`.

## Configure

Create `~/.config/coral/settings.json`:

```json
{
  "openrouter_api_key": "sk-or-v1-...",
  "review_agents": [
    {
      "model": "anthropic/claude-sonnet-4",
      "effort": "high"
    },
    {
      "model": "openai/gpt-5",
      "effort": "medium"
    },
    {
      "model": "x-ai/grok-4",
      "effort": "high"
    }
  ],
  "num_reviews": 2,
  "max_concurrent_reviews": 2,
  "verification_agent": {
    "model": "google/gemini-2.5-pro",
    "effort": "high"
  },
  "time_budget_minutes": 20,
  "spend_cap_dollars": 2.0
}
```

`review_agents` is a preference-ordered list of one or more models to review with, each with its
own reasoning effort. `num_reviews` is how many reviews Coral wants and cannot exceed the number
of entries; `max_concurrent_reviews` is how many reviewers run at a time. Coral works down the
list until it has that many reviews: a reviewer that times out or whose model errors is replaced
by the next unused entry, so the entries past `num_reviews` are fallbacks. Running out of entries
with fewer reviews than asked for still produces a review.

`verification_agent` checks all proposed findings and writes the final summary. Model names must
match OpenRouter exactly; an empty effort string leaves the provider's default in place.

The time budget covers the whole command. The spend cap covers all reviewer and verifier model
calls together. Coral uses the OpenRouter API key directly and has no management-key mode.

## Run

Run Coral in the directory to review:

```sh
coral
```

With no argument, Coral reviews uncommitted changes. If the working tree is clean, it reviews the
most recent commit. In a repository without a commit, or outside a Git repository, it reviews the
whole codebase.

An optional scope is passed verbatim to every reviewer:

```sh
coral "focus on the parser and its callers"
```

While the review runs, Coral draws a table on stderr with one row per agent, its turns, and its
cost, redrawn in place and left on screen when the run ends:

```
Reviewing ~/src/coral...

Model                   Turns  Cost
------------------------------------
glm-5.3-flash           10     $0.09
deepseek-v4-flash-0731  21     $0.01
------------------------------------
Elapsed 00:02:23               $0.10
```

The Markdown review goes to stdout, so it can be redirected. The table, progress, and failures go
to stderr.

## Isolation

Each reviewer and the verifier gets a separate disposable checkout and Docker container. In a Git
repository, the checkout includes tracked changes and non-ignored untracked files but excludes
ignored local files. The OpenRouter key never enters an agent container.
