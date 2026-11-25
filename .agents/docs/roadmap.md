# Roadmap

The remaining implementation sequence for Coral. Completed items are removed once their mechanics
live in code and current documentation; a verified item stays only when unfinished work depends on
the boundary it established.

## 24. Credential-free agent workspace

Status: verified

Depends on: nothing

Every agent-controlled file and shell operation goes through one bounded shell tool inside the
agent's credential-free container. The agent run receives its own checkout copy and container.

Done when: a real review reads and searches through the shell; a resource-bound probe dies inside
the container; and no agent operation reaches the runner filesystem, process table, credentials, or
Docker authority.

## 23. Referenced issue context

Status: not started

Depends on: 24

Before reviewing a pull request or a main-branch range, read each referenced ordinary GitHub issue
and give the agent a fixed bounded context. Resolve fetches the context and transfers it as an
artifact; the agent receives no other GitHub capability.

Done when: a real pull-request review reads a linked issue and one named only in a commit message; a
real main-push review reads an issue named by its range; unavailable and excess references leave an
explicit bounded notice; and no agent container carries a GitHub token.

## 25. End-to-end byte budget

Status: not started

Depends on: 23

One budget covers the captured diff, assembled agent requests, selected model context, structured
agent output, and publication payloads in both review modes. A value that cannot be carried whole is
refused rather than truncated.

Done when: a real pull request and a real main push crossing the capture budget are declined before
a model call; a request outside the selected model's context stops before its first completion; and
an oversized finding, review, or issue fails without partial publication.

## 26. Default-branch automatic review delivery

Status: built

Depends on: 24

Automatic pull-request review uses `pull_request_target`, so default-branch workflow code owns the
credentialed run. The caller rejects forks before invoking the reusable workflow; deterministic
resolution pins the same-repository head SHA before the isolated review job checks it out.

Done when: a real same-repository pull request that edits its caller is reviewed by the default
branch's workflow; the review checks and posts against the pinned head commit; and a fork pull
request invokes no credentialed reusable job.

## Not On This Roadmap

- Forges other than GitHub, GitHub Enterprise Server, and a second model provider.
- An external credential broker or microVM agent shell.
- A review-memory store outside the pull request or repository-specific review policy.
