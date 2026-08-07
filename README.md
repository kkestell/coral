# 🪸 Coral

A code review agent that runs as a GitHub Actions workflow. When a pull request is opened or marked ready for review, or when somebody comments `/coral` on one, Coral reviews the change and leaves its findings as comments on the pull request.

Coral is a proof of concept and is early.

## Adding Coral to your repository

**1. Add the workflow.** Copy [`examples/coral.yml`](examples/coral.yml) to `.github/workflows/coral.yml` on your **default branch**. GitHub reads the file from there when a comment triggers a run, so a copy that lives only on a feature branch never runs.

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
      # openrouter_management_key: ${{ secrets.OPENROUTER_MANAGEMENT_KEY }}
```

**2. Add the secret.** Coral reaches its model through [OpenRouter](https://openrouter.ai), so an OpenRouter key is the only credential you supply. The GitHub token comes from the job and expires with it.

Add one of these under Settings → Secrets and variables → Actions:

- `OPENROUTER_API_KEY` — a plain API key, used as it is. Set a credit limit on it; that limit is the only bound on what it can spend if it leaks.
- `OPENROUTER_MANAGEMENT_KEY` — a [provisioning key](https://openrouter.ai/settings/provisioning-keys). Coral mints a fresh API key for each run, capped at a couple of dollars and expiring within the hour. Nothing to rotate if one leaks.

Prefer the management key if your account balance would hurt to lose. The workflow above passes the plain key; comment that line out and uncomment the other to switch.

## Asking for a review

Comment `/coral` on a pull request, or as a reply on the diff, to ask for a review at any time. Coral reacts with 👀, then posts its review.

Anyone with write access can ask. Coral only comments: it never pushes, approves, or requests changes.

## Risks

The measures below limit the damage. None of them stop a determined attacker from reaching the OpenRouter key or the workflow's GitHub token.

### Mitigations

- Never reviews a fork, and ignores `/coral` from anyone below collaborator. Every change it runs is code somebody with push access could have pushed anyway.
- Runs the agent's shell in an unprivileged container: no added capabilities, no Docker socket.
- Puts no credential in that container: no OpenRouter key, no GitHub token, none of the runner's variables. It gets a copy of the checkout and the toolcache read-only.
- Limits the agent's job to `contents: read`. The write scopes live in the jobs that post, which never run agent code.
- Never pushes, approves, or requests changes. A bad review costs a comment, not a merge.
- Mints a per-run API key from a management key, so a leak expires on its own.

### Remaining risks

- The container has network access, which dependency installs need. Anything the agent can read, it can send.
- A container escape reaches the review job, which holds the OpenRouter key.
- OpenRouter and whichever provider it routes to see the diff, files the agent opens, command output, and the conversation. Do not install Coral where that is unacceptable.
- Prompt injection works. The diff and the conversation are attacker-controlled text in the model's context, so a review can be steered into missing a finding or posting text somebody else wrote.
- Handing a minted key between jobs prints it in one log line before masking starts. Anyone who can read your Actions logs can spend it until it expires.

Prefer the management key, set a credit limit on whichever key you use, keep write access narrow, and treat Coral's comments as suggestions from an unreliable reviewer.

## Development

Coral is Python, built with `uv`. `.agents/docs/development.md` covers setup and the commands.
