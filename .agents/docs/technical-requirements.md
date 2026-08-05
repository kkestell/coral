# Technical Requirements

THIS FILE MUST BE KEPT UP TO DATE AT ALL TIMES

How Coral is built and what it is built on. What Coral does is in `.agents/docs/functional-requirements.md`.

Every limit quoted here is a real platform limit that the design has to live inside. Where a decision is still open, it is listed under "Undecided" rather than guessed at.

## Platform

- **TR-1** — Coral is written in Python and runs on AWS Lambda, in `us-east-1`.
- **TR-2** — Infrastructure is defined in Terraform.
- **TR-3** — The review agent is built with DeepAgents.
- **TR-4** — Models are reached through OpenRouter, using the `langchain-openrouter` package and its `ChatOpenRouter` chat model. No model provider is called directly.
- **TR-5** — The model is `~deepseek/deepseek-v4-flash-latest`. It offers a 1,048,576-token context window and supports tool calling, structured outputs, and a reasoning effort setting, which are the capabilities the rest of this document depends on. The leading tilde is an OpenRouter alias resolving to the newest release in the DeepSeek V4 Flash family, so the model behind it changes without notice.
- **TR-6** — Coral identifies itself to GitHub as a GitHub App, authenticating with an installation access token.

## Trust Boundary

The agent runs shell commands inside a checkout of somebody else's repository, and repository code runs in that same place. The credential that can write to GitHub is kept out of its reach.

- **TR-7** — The agent holds no GitHub credential. Deterministic code clones the repository, and deterministic code posts the review. The agent's sole output is a structured review object, and it has no means of reaching GitHub itself.
- **TR-8** — The clone leaves no usable credential behind in the working tree. The token does not appear in the remote URL, no credential helper is configured, and no `.netrc` is written. Otherwise TR-7 is decorative, because the agent has a shell and `.git/config` is a file.
- **TR-9** — The boundary covers the GitHub token and nothing else. The OpenRouter key is in the worker's environment and is readable from the agent's shell. Accept this or fix it deliberately; do not assume the agent is sandboxed.

## Receiving The Event

GitHub terminates a webhook delivery that has not returned a 2xx response within ten seconds. Nothing that could take longer than that may sit in the request path.

- **TR-10** — Webhook deliveries arrive at a Lambda function URL. There is no API Gateway in front of it, because Coral needs none of what API Gateway provides.
- **TR-11** — The receiving Lambda verifies the HMAC signature on the payload before doing anything else, and rejects a delivery whose signature does not match.
- **TR-12** — The receiving Lambda enqueues the work on SQS and returns 200. It does no other work. SQS supplies the retry behavior and the dead-letter queue that the receiver would otherwise have to implement.
- **TR-13** — The enqueued message carries the repository, the pull request number, the head commit SHA, and the delivery identifier. It does not carry the webhook payload. An SQS message is capped at 256 KB and a GitHub payload can exceed that, so the worker refetches what it needs.
- **TR-14** — A second Lambda consumes that queue and performs the review.

## Running The Review

- **TR-15** — The worker Lambda is deployed as a container image. The zip deployment path allows 250 MB unzipped including layers, which the DeepAgents dependency tree will not fit inside. A container image allows 10 GB and lets `git` be installed the ordinary way.
- **TR-16** — Python dependencies are managed with `uv` against a committed lockfile, and the image installs them with `uv sync --frozen`. An image build never resolves versions.
- **TR-17** — `git` is not present in the Lambda runtime. The container image installs it.
- **TR-18** — The worker performs a shallow clone into `/tmp` before it constructs the agent. Setup is not the agent's job, and the working tree exists before the model sees anything.
- **TR-19** — Ephemeral storage is configured above the 512 MB default, high enough to hold a shallow clone plus whatever the repository's own tooling writes while a test runs. The ceiling is 10,240 MB.
- **TR-20** — `/tmp` survives between invocations when Lambda reuses a warm execution environment. The worker treats anything it finds there as untrusted leftovers and clears its working directory on entry.
- **TR-21** — Memory is configured for CPU rather than for footprint. Lambda allocates CPU in proportion to memory, one vCPU at 1,769 MB, up to roughly six at the 10,240 MB maximum.

## The Agent

- **TR-22** — The agent's access to the checkout goes through a DeepAgents backend. Filesystem operations and shell execution both come from that one object, so the compute target is a single swappable dependency.
- **TR-23** — Coral uses `LocalShellBackend`, rooted at the clone. It provides the `execute` tool that satisfies FR-6 and FR-7, and its filesystem operations run as direct Python rather than as shelled-out scripts, which matters for an agent that reads and greps heavily against a fifteen-minute budget.
- **TR-24** — Nothing outside the backend may shell out into the checkout, and no other code path may hold a second notion of where the checkout lives. Honoring this is what keeps TR-40 a small change rather than a rewrite.
- **TR-25** — The agent returns a structured review object, not prose. It carries a summary and a list of findings. Each finding carries its text and its anchor: a span of lines in a file, a single line in a file, a whole file, or the pull request as a whole. This schema is the contract between the agent and the posting code, and it is the only thing that crosses TR-7's boundary.
- **TR-26** — The provider list on `ChatOpenRouter` is pinned to providers whose tool calling has been tested. Roughly thirty providers serve this model, OpenRouter fails over between them automatically, and tool-calling fidelity varies. An unpinned failover midway through a review looks like the agent silently getting worse.

## Posting The Review

- **TR-27** — Findings are posted as a single GitHub pull request review. The summary becomes the review body and the anchored findings become its comments, in one API call.
- **TR-28** — The review is left as a comment. It never approves and never requests changes, per FR-16.
- **TR-29** — GitHub accepts a review comment only on a line that is part of the diff. Before posting, the anchor on each finding is checked against the diff, and findings that do not fall inside it are moved into the summary with their intended file and line named. This is what satisfies FR-13, and it is expected to fire regularly rather than being an edge case.

## Knowing What Has Been Reviewed

Coral needs to answer two questions that the pull request itself cannot answer reliably: has this already been reviewed, and is a review of it running right now. One record answers both.

- **TR-30** — Coral keeps a DynamoDB table of review records, keyed by repository and pull request number. This is the only state Coral owns.
- **TR-31** — A worker claims a pull request with a conditional write that succeeds only when no live record exists. Winning the write is what entitles a worker to proceed. Losing it means another worker holds the claim, or the review is already done, and the message is discarded rather than retried — it is a correct outcome, not a failure.
- **TR-32** — A record holds its state, the head commit SHA, and a lease expiry. The claim is made before the clone, so a duplicate delivery costs one write instead of a full agent run. Reaching a terminal state is the last thing a successful worker does, after the review is posted.
- **TR-33** — The lease expiry is longer than the Lambda timeout of 900 seconds, so a lease cannot expire while its own worker is still running. A claim whose lease has passed is dead and any worker may take it over, which is what stops a crashed worker from locking a pull request forever.
- **TR-34** — Lease expiry is evaluated by comparing the stored timestamp against the current time, in the conditional write. It is never delegated to DynamoDB's TTL. TTL deletes expired items only within a few days, and an expired item still appears in reads until it is collected, so TTL cannot express a lock.
- **TR-35** — The table also carries a TTL attribute, for housekeeping alone. It keeps finished records from accumulating forever and has no part in correctness.
- **TR-36** — A worker that fails releases its claim before the message returns to the queue. Otherwise Coral's own lock would block its own SQS retry until the lease expired. Lease expiry is the backstop for a worker that dies without getting the chance.

## Secrets And Configuration

- **TR-37** — Coral needs an OpenRouter API key, a GitHub App private key, and a GitHub webhook secret.
- **TR-38** — The GitHub App private key and the webhook secret are read from AWS Secrets Manager at runtime. They are not Lambda environment variables, which are visible to anyone who can describe the function.

## Time Budget

- **TR-39** — A Lambda invocation is capped at 900 seconds. This is a hard limit and cannot be raised. The full fifteen minutes is available to the worker, because the SQS trigger means nothing is waiting on an HTTP response.
- **TR-40** — The budget is spent almost entirely on the agent loop, not on tests. Coral does not run full suites, and a targeted test run costs seconds. What costs minutes is the number of model round trips. Wall clock is the binding constraint, not token cost.
- **TR-41** — If 900 seconds proves too short, the escape hatch is a custom DeepAgents sandbox backend backed by a Lambda MicroVM. A MicroVM runs up to eight hours with up to 16 vCPUs, 32 GB of memory, and 32 GB of disk, and is available in `us-east-1`. `BaseSandbox` derives every filesystem operation from a single `execute()` method, so the change is one method against the MicroVM's endpoint, and the agent's tools and prompt are untouched. Adopting it makes TR-33's lease longer than 900 seconds, and the two must be changed together.

## Failure And Retry

- **TR-42** — A worker that fails returns the message to the queue. After the redrive policy is exhausted, the message lands in a dead-letter queue.
- **TR-43** — Exhausting the retries is a visible event, not a silent drop. Something must notice the dead-letter queue and satisfy FR-17.

## Undecided

Open decisions, each blocking something concrete.

- **Who watches the dead-letter queue**, as TR-43 requires.
