# Coral

A code review agent that runs as a GitHub Actions workflow. When a pull request is opened or marked ready for review, or when somebody comments `/coral` on one, Coral clones the repository, reads the change, and leaves its findings as comments on the pull request.

Coral is a proof of concept and is early. Today a run does everything except think: it resolves the pull request, computes the diff, and posts a review whose contents are hardcoded. The model is not wired up yet.

## Adding Coral To Your Repository

Two steps.

**1. Add the workflow.** Copy [`examples/coral.yml`](examples/coral.yml) into your repository as `.github/workflows/coral.yml`, on your default branch:

```yaml
name: Coral

on:
  pull_request:
    types: [opened, ready_for_review]
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]

concurrency:
  group: coral-${{ github.event.pull_request.number || github.event.issue.number }}
  cancel-in-progress: false

jobs:
  coral:
    permissions:
      contents: read
      issues: write
      pull-requests: write
    uses: kkestell/coral/.github/workflows/coral.yml@main
    secrets:
      openrouter_api_key: ${{ secrets.OPENROUTER_API_KEY }}
```

**2. Add the secret.** Set `OPENROUTER_API_KEY` under Settings → Secrets and variables → Actions. Coral reaches its model through [OpenRouter](https://openrouter.ai), so that key is the only credential you supply. The GitHub token comes from the job itself and expires when the job ends.

That is the whole installation. Nothing to host, nothing to provision, and nothing to rotate.

Put the file on your **default branch**. GitHub always reads the workflow file from there when a comment triggers it, so a copy that lives only on a feature branch never runs.

## Asking For A Review

Coral reviews a pull request automatically when it is opened, or when a draft is marked ready. To ask for another review at any time, comment `/coral` — either on the pull request itself or as a reply on the diff. Coral reacts with 👀 to say it heard you, then posts its review.

Anyone with write access can ask. Coral never pushes, never approves, and never requests changes; it only comments.

## What Each Part Of The Workflow File Is For

Every line in the file above has to be there. A reusable workflow cannot declare its caller's triggers, cannot grant itself permissions the caller withheld, and cannot key its caller's concurrency, so all three live with you rather than upstream.

- `on:` — the three events Coral answers. The comment events are separate because GitHub sends one for a comment on the pull request and a different one for a reply on the diff.
- `concurrency:` — one run per pull request. A run already going finishes; a newly queued run replaces whichever run was still waiting.
- `permissions:` — the scopes the job's token gets. Both write scopes are needed, because the reaction on a pull request comment and the reaction on a diff reply go through different endpoints and neither permission grants the other.
- `uses:` — the version pin. `@main` tracks the latest; pin a tag once there is one.

## Development

`.agents/docs/development.md` covers setup and the commands. Coral is Python, built with `uv`.
