# Take the agent out of the runner user

Roadmap: item `12`, `Take the agent out of the runner user`.

## What Was Checked

Everything about DeepAgents below was read out of the installed package on 2026-08-07; everything about the runner image was read out of `actions/runner-images`' `Ubuntu2404-Readme.md` on `main` the same day.

- `LocalShellBackend.execute` is the only place the framework runs an agent command: one `subprocess.run(command, shell=True, env=self._env, cwd=self.cwd)`. Every file tool — `ls`, `read`, `write`, `edit`, `glob`, `grep` — is Python I/O in Coral's own process, inherited from `FilesystemBackend`, resolving virtual paths under `root_dir` and refusing traversal. The one nuance: the `grep` tool prefers a `ripgrep` binary when one is importable, run by Coral's process over `root_dir` with the agent supplying only the pattern.
- The middleware exposes the `execute` tool only to a backend passing `isinstance(backend, SandboxBackendProtocol)` (`deepagents/middleware/filesystem.py`, `_supports_execution`), and it introspects `execute`'s signature before forwarding the `timeout` keyword. A subclass of `LocalShellBackend` that keeps the `execute(self, command, *, timeout=None)` signature satisfies both.
- The hosted `ubuntu-24.04` image ships Docker client and server 28.0.4, and its toolcache carries exactly the toolchains the done condition names: Go 1.24/1.25/1.26, Node 22/24, Python 3.10 through 3.14, plus PyPy and Ruby. The toolcache layout is `/opt/hostedtoolcache/<tool>/<version>/x64/bin`.
- The image preloads no container images, so the run's first `docker run` pulls `ubuntu:24.04` (about 30 MB).
- `ubuntu:24.04` carries coreutils (`sleep`, `timeout`) and `bash`, and does not carry `git`. `coral/prompts/review.md` names `git log` as a first-class move, and a Python package built with `setuptools-scm` needs `git` to install at all, so the container gets `git` at start rather than when the agent notices it missing.
- A container run without `--privileged` and without the daemon's socket mounted gets its own PID, mount, and network namespaces: no process on the host is visible, no path on the host is reachable except what is mounted, and there is no way to ask the daemon for more.

## Goal

The agent's shell runs as root inside a container that holds no credential and no view of the runner. Items 10 and 11 made what a compromised agent can reach cheap — a read-only token, a key capped at a few dollars; this item makes it unreachable. `Runner.Worker`'s memory, the runner's log files on disk, `GITHUB_OUTPUT`, the workspace, and the review job's own environment all sit on the other side of a namespace boundary, and the one cleartext log line the minted key crosses in becomes readable only by people who can already read the repository's logs.

## Approach

### The seam

The framework already splits the agent's reach in two: file tools are Coral's own Python over `root_dir`, and `execute` is the one method that runs a command. Only `execute` moves. A new `ContainerBackend(LocalShellBackend)` in `coral/agent.py` — still the only module importing `deepagents` — overrides `execute` to delegate to `coral/container.py`, and inherits everything else. Subclassing keeps the framework's `isinstance` check against `SandboxBackendProtocol` passing, which a forwarding wrapper would fail.

The file tools and the shell see the same directory: `root_dir` is the agent's copy of the checkout on the runner's disk, and that directory is bind-mounted read-write into the container at `/checkout`, the shell's working directory. A scratch file written with `write_file` is immediately runnable with the shell and the other way around. The model's view of paths does not change: file tools present virtual paths today and still do, and the shell runs relative commands from the checkout root today and still does.

### The container

`coral/container.py`, a new module, the only place Coral speaks to `docker`. The `docker` client runs on the runner as Coral's own subprocess; the agent never holds it.

- `IMAGE`: `ubuntu:24.04` pinned by digest, the same reasoning as SHA-pinned actions. The digest is read at build time and lives in the constant's comment.
- `start(name, checkout)`: `docker run -d --init --name <name>`, the copy mounted read-write at `/checkout`, `/opt/hostedtoolcache` mounted read-only at the same path, the environment baked in with `--env` flags, running `sleep infinity`. `--init` so a reaped PID 1 exists — test runners orphan children, and `sleep` reaps nothing. Then one exec installing `git` (`apt-get update && apt-get install -y git`), for the two reasons measured above. No `--privileged`, no socket mount, no capability additions; the default network stays, because `apt-get` and every dependency install need it and the container holds nothing to exfiltrate.
- `execute(name, command, timeout)`: `docker exec -w /checkout <name> timeout -k 5 <seconds> bash -c <command>`. The ceiling is enforced inside the container because killing the `docker exec` client leaves the command running; a runner-side `subprocess` timeout slightly above it is the backstop for a hung client. `timeout` exits 124, which is the code `LocalShellBackend` already reports for a timeout. Output shaping — stdout and stderr combined, stderr lines prefixed, truncation at the byte cap, the exit code appended when non-zero — is replicated here, and the function returns a small result of its own; `coral/agent.py` maps it to the framework's `ExecuteResponse`, keeping `deepagents` out of this module.

Containers are named `coral-reviewer` and `coral-verifier` — one job per runner VM, so fixed names cannot collide — and nothing removes them: the VM is discarded when the job ends.

### The copy

Each agent run gets a fresh copy of the checkout that it owns, made with `cp -a` so `.git` and the full history come along, under a path `coral/runner.py` names (inside Coral's temporary directory, outside the workspace; the artifact steps upload named files, so a directory beside them never crosses). `coral/review.py` provisions before each run: copy, start the container, hand the copy's path and the container's name to the agent.

The workspace itself is never written by any agent again. The diff and the added-line set are computed on a checkout the agent could not touch, which turns the sameness of the diff the agent saw and the diff the anchors are checked against from a discipline into a construction.

`reset` in `coral/diff.py` is deleted. Its job — a checkout with nothing the reviewer wrote still in it — is done by the verifier's fresh copy and fresh container. What is deliberately given up: `reset` kept ignored files so dependencies the reviewer installed survived into the verifier, and a fresh copy does not, so a verifier that runs a regression test installs that project's dependencies itself. The live checks measure what that costs on real projects.

### The environment

`coral/environment.py` still owns the agent's shell environment, but it is no longer picked out of the runner's — the runner's `PATH` means nothing inside the container. It becomes a pure function from the toolcache's directory listing to the container's environment: `CI=true`, `HOME=/root`, `LANG=C.UTF-8`, and a `PATH` that prepends the newest version of each cached tool's `bin` directory (numeric version ordering, so 1.9 sorts under 1.25) to the image's default. A repository pinned to an older toolchain still has every cached version reachable by absolute path, and the agent can say so in a command.

The prompts' description of where the agent is working changes with the facts: `review.md` and `verify.md` say the shell is root in an Ubuntu 24.04 container — `apt-get` works and `sudo` is unnecessary — with the hosted toolcache mounted read-only and the newest of each toolchain already on `PATH`.

### What does not change

- The YAML — not one line. Docker is preinstalled, and the whole item lives in Python.
- The key's handling: `coral/review.py` pops `OPENROUTER_API_KEY` first, `coral/agent.py` wraps it in `SecretStr`, and the model call happens in Coral's process on the runner. No credential enters the container because nothing puts one there.
- The deadline, the step cap, the shell ceiling and its two-halved enforcement, the retry arithmetic.
- The review flow around provisioning: render, run, verify, filter, write payloads.

## Related code

- `coral/container.py` — new: `IMAGE`, the mount table, `start`, `execute`, the exec argument builders.
- `coral/agent.py` — `ContainerBackend`, the `ExecuteResponse` mapping, `_run` taking the copy's path and the container's name.
- `coral/environment.py` — the container environment and the toolcache `PATH`.
- `coral/review.py` — provisioning before each agent run.
- `coral/runner.py` — the path the copies live under.
- `coral/diff.py` — `reset` deleted.
- `coral/prompts/review.md`, `coral/prompts/verify.md` — the environment description.
- `tests/test_container.py` — new; `tests/test_environment.py`, `tests/test_agent.py`, `tests/test_diff.py` — updated.

## Current state

- The backend is `LocalShellBackend` over the workspace: the agent's commands run as the runner user, and `.agents/docs/architecture.md` says plainly that the allowlisted environment is hygiene, not a boundary.
- The agent writes scratch files into the workspace itself, and `reset` cleans them out between the two runs.
- `coral/environment.py` picks seven names out of the runner's environment.
- Everything the review job holds — the masked key in `Runner.Worker`'s memory, the runner's own logs and `_diag` files, `GITHUB_OUTPUT` — is readable from the agent's shell.

## Test plan

**Key behaviors to verify**

- `container.py`'s argument builders, as pure functions: the run arguments carry `--init`, both mounts with the right modes, the pinned image, and nothing resembling `--privileged` or a socket; the exec arguments carry the working directory and the in-container `timeout` wrapping with the ceiling passed through.
- Output shaping: stdout and stderr combine with the prefix, the byte cap truncates and says so, a non-zero exit appends its code, exit 124 reads as the timeout message — the same contract `tests/test_agent.py` relies on today.
- `environment.py`: from a fake toolcache layout, the newest version of each tool wins under numeric ordering, a tool with no versions contributes nothing, the fixed names are present, and no value is read from the process environment.
- `review.py` provisioning order: fresh copy, then container, then the run — shaped so the test needs no Docker.

**What NOT to test**

- Docker itself: that namespaces isolate, that mounts mount, that `--init` reaps. That is the kernel and the daemon, and it is what live check 4 observes on the real runner.
- `cp -a` fidelity, `apt-get`, and the image pull. The live checks exercise all three per run.

**Live checks**

Added as a group in `.agents/docs/testing.md`. The first three are the done condition's toolchain half; each needs a project of that language in `kkestell/coral-test` with a planted defect, pushed as its own branch.

1. Python: open a pull request with a planted defect in a Python project. The review carries the finding with its failing regression test, and the step log shows the test command executing through the container.
2. Node: the same, on a project with an `npm test` suite.
3. Go: the same, on a module with a `go test` suite.
4. The escape probe, the done condition's other half: temporarily patch `coral/review.py` to run fixed commands through the agent's own backend after provisioning and log them — `ps -e`, `ls /home/runner`, `cat /proc/1/comm`, `touch /opt/hostedtoolcache/probe`, `docker ps`. Expect a process table holding only the container's own processes with no `Runner.Worker`, no `/home/runner`, an init as PID 1, a read-only refusal from the toolcache, and no `docker` to run. Revert the patch.

Check 1 doubles as the control that a plain review still posts everything it posts today.

## Implementation plan

1. **Save this plan** as `.agents/docs/plans/2026-08-07-13-56-012-take-the-agent-out-of-the-runner-user.md`.
2. **Write `coral/container.py`** and `tests/test_container.py`, reading the image digest at this step.
3. **Rewrite `coral/environment.py`** and its tests.
4. **Change `coral/agent.py`** — `ContainerBackend`, the response mapping, `_run`'s parameters — and `tests/test_agent.py`.
5. **Change `coral/review.py` and `coral/runner.py`** — provisioning and the copy path; **delete `reset`** from `coral/diff.py` and its tests.
6. **Update both prompts'** environment description.
7. **Run** `uv sync --frozen`, `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`, `uv run pytest` — all clean.
8. **Live checks** 1 through 4.
9. **Documentation updates** below; roadmap item 12 status to `built`.

## Not doing

- **A second user instead of a container.** The roadmap decided: a second user gives up `sudo` and `apt-get`, and root in a container is not root on the host.
- **Network isolation.** The agent had the internet before this item and keeps it; the container holds no credential, and the code it could send out is visible to everyone already trusted to trigger a run. `--network` is one flag away if that changes.
- **Resource limits.** The deadline bounds time, the VM is disposable, and nothing shares it.
- **A custom image.** A second packaging artifact to build, host, and pin, to save one `apt-get install git` per container.
- **One container shared by both agent runs.** Files the reviewer's root left in the copy would need root to clean, and the verifier's clean checkout would be a cleanup discipline again instead of a construction.
- **Removing containers or copies at job end.** The VM is discarded; teardown code would run only where it is not needed.
- **Confining the file tools further.** They are already Coral's own process resolving paths under the copy and refusing traversal; the shell was the escape, and the container closes it.

## Documentation updates

`.agents/docs/architecture.md` (at its ceiling — trim first):

- "The Runner": the never-in-a-container bullet is replaced by the fact that splits it: Coral's process runs on the runner; the agent's shell runs as root in an `ubuntu:24.04` container with the hosted toolcache mounted read-only and `apt-get` for the rest, which is the answer to how a repository Coral has never seen builds.
- "Rules That Hold Everywhere": the this-is-not-a-sandbox bullet becomes the boundary statement — the container holds no credential and sees only its own copy of the checkout and the read-only toolcache; the runner's filesystem, process table, and `Runner.Worker`'s memory are out of reach. The what-a-compromised-agent-keeps bullet (the review's text) stands.
- "The Run": the review job's bullet gains the container, and the cleartext-line sentence shrinks to its remaining audience — people who can already read the logs.
- "The Codebase": `coral/container.py` added; `coral/diff.py`'s entry loses the reset clause.

`.agents/docs/functional-requirements.md` (1,496 of 1,500 — trim first), "Out Of Scope": a Docker daemon the agent can reach, and `--privileged`. Both are host root, so either would put the runner back inside the sandbox.

`.agents/docs/testing.md` (1,499 of 1,500 — trim first): the four checks above as a group.

`.agents/docs/development.md`, "Gotchas": the unit tests need no Docker; only a real run — or a rehearsal of `coral/container.py` by hand — does.

`README.md`: the posture sentence gains its second half — the agent's shell runs in a container that holds no credentials.

`.agents/docs/roadmap.md`: item 12 to `built`, its mechanics bullets gone to where they now live; item 11's cleartext-line bullet rewritten to the fact that remains, the line prints and only log readers can see it.

## Validation

- The five commands, all clean.
- The done condition, mapped: live checks 1 through 3 are "a Python, a Node, and a Go project's own tests from inside the container"; check 4 is "can reach neither the runner's filesystem nor its process table."

## Follow-up

- `VALIDATION_TODO.md` still owes item 10 its "Posting" and "Failure" re-runs; this item does not absorb them.
- If a verifier is ever observed spending real budget reinstalling what the reviewer already installed, the shared-container decision above is the one to revisit, with that measurement in hand.
