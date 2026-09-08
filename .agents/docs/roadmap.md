# Roadmap

The remaining implementation sequence for Coral.

## CLI review

Status: built

Depends on: nothing

Run one or more configured review agents concurrently over an optional opaque scope, verify their
combined findings with a separately configured agent, and print one final Markdown review.

Done when: a real command with two differently configured reviewers shows both running
concurrently, the scope reaches both unchanged, the verifier runs against a fresh checkout, only
confirmed findings print to stdout, progress stays on stderr, and the API key is absent from every
agent container.

## Reviewer count and fallback

Status: built, awaiting its real run

Depends on: CLI review

Take the number of reviews wanted and the number of reviewers run at once from the settings file,
and treat `review_agents` as a preference-ordered list a failed reviewer falls down.

Done when: a real command with more `review_agents` entries than `num_reviews` and a deliberately
broken model in the list shows the broken model's reviewer failing, the next entry taking its
place, `max_concurrent_reviews` reviewers running at a time, and the printed review carrying the
findings of the models that succeeded.

## Not On This Roadmap

- GitHub Actions delivery, pull-request publication, or issue creation.
- OpenRouter management keys or another model provider.
- Repository-specific review policy or persistent review memory.
