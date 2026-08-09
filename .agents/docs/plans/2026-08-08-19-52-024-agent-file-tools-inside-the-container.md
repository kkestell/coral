# Agent file tools inside the container

Roadmap: item `24`, `Agent file tools inside the container`.

## What Was Checked

Everything about DeepAgents below was read out of the installed package on 2026-08-08, and every
behavioral claim was run against a live container started from the pinned `IMAGE` digest with this
repository mounted at `/checkout`.

- `deepagents.backends.sandbox.BaseSandbox` is the shape this item wants and it already exists. It
  implements `ls`, `read`, `write`, `edit`, `delete`, `grep`, and `glob` on top of `execute()`, and
  leaves `execute`, `upload_files`, `download_files`, and `id` abstract. A subclass of it passes the
  `isinstance(backend, SandboxBackendProtocol)` check the middleware uses to decide whether to
  register the `execute` tool. Confirmed live: a `BaseSandbox` over `docker exec` registers all
  eight tools — `ls`, `read_file`, `write_file`, `edit_file`, `delete`, `glob`, `grep`, `execute` —
  and `execute_accepts_timeout` still passes.
- The roadmap's two premises hold. `FilesystemBackend.read` does `content = f.read()` on the whole
  file and slices afterwards, and `max_file_size_bytes` is referenced in exactly one place, inside
  `grep`.
- `BaseSandbox`'s file operations are `python3 -c` scripts. `ubuntu:24.04` carries no `python3`.
  `apt-get update && apt-get install -y git python3` in the pinned image took 8.6 seconds against a
  warm local mirror.
- Every operation works over `docker exec` against the pinned image with `python3` installed: `ls`,
  a paginated `read` (a 1,249-line page of `uv.lock` came back as a 191,733-character JSON payload),
  `grep` with a basename glob, `glob`, `write`, `edit`, `delete`, and the not-found errors for
  `read` and `delete`.
- Two framework defaults do not fit a container rooted at `/checkout`, both measured:
  - `BaseSandbox.glob` defaults its search root to `/`. `glob("**/*.md")` with no path did not
    finish in 300 seconds — it walks `/proc`, `/sys`, and the read-only toolcache mount — while the
    same pattern rooted at `/checkout` returned five matches in under a second.
  - `BaseSandbox.grep` with a glob containing `/` is broken upstream. That route's Python source is
    embedded in a double-quoted shell string and one of its comments contains double quotes, so the
    shell truncates that line and `python3` reports `SyntaxError: expected 'except' or 'finally'
    block`. The route's own `2>/dev/null` swallows it, so the model reads an empty result. Basename
    globs (`--include`) and no glob both work.
- `container.shaped` appends `Exit code: N` to a non-zero command's output. `BaseSandbox` parses
  `read` and `edit` output as a single JSON document, so that line would break both. The middleware
  already tells the model `[Command failed with exit code N]` from `_format_execute_output`, so the
  line is a duplicate today.
- `OUTPUT_CAP_BYTES` is 100,000 and every in-container script cap is above it: a read page is capped
  at 500 KiB, and a binary read under `MAX_BINARY_BYTES` (500 KiB) comes back base64-encoded at
  about 684 KiB. The 191,733-character read above already crosses 100,000.
- `FilesystemMiddleware` evicts any tool result over `tool_token_limit_before_evict` (20,000 tokens,
  80,000 characters) to a file through `backend.write`, under `/large_tool_results`. That is the
  bound on what the model actually reads back, and it is below every cap named above.
- `download_files` is called only by the summarization middleware's media offload and by the skills
  and memory middlewares. Coral sends no images and uses neither middleware, so nothing reaches it.
- `enable_capture_offload` defaults to `False`, so `execute_with_offload` runs the command unwrapped
  and behaves exactly like `execute`.
- `BaseSandbox` has no `root_dir` and no `cwd`, and nothing in the middleware asks a
  non-`CompositeBackend` backend for either.

## Goal

Every tool the agent holds runs inside the container, under the memory, processor, and process
limits its shell already has. What the model reads about a file is produced by a process the
container's limits can kill, not by Coral's process on the runner. The tools and the shell address
one filesystem by one set of paths.

## Approach

### The backend

`ContainerBackend` in `coral/agent.py` changes its base from `LocalShellBackend` to `BaseSandbox`.
`execute` keeps its current body. Three members are added and two defaults are overridden.

- `id` returns the container's name.
- `upload_files` writes each file's bytes into the container. `write_file` is the only caller.
- `download_files` reads each file's bytes out of it. Nothing Coral runs calls it, and it is
  implemented rather than left raising because it is four lines.
- `glob` defaults its search root to `/checkout` before delegating, because the framework's `/`
  spends the whole shell ceiling walking the container's filesystem.
- `grep` answers a glob containing `/` with an error naming the working alternative — a basename
  glob, or a narrower `path` — rather than letting the broken upstream route return an empty
  result the model would read as "no matches".

The constructor stops taking the checkout's path: the backend no longer touches the runner's
filesystem, so the container's name is the whole of what it needs. `_run`, `produce_review`,
`verify_findings`, and `review.provision` lose that argument with it, and `_run` logs the container
rather than the copy.

`forgiving` is unchanged and now covers all eight tools, so a tool's own failure — a path that is
not there, a glob the framework cannot run — comes back to the model as an observation.

### The container

`coral/container.py` gains the byte transfer and loses the shaping that a JSON protocol cannot
survive.

- `INSTALL` becomes `apt-get update && apt-get install -y git python3`. Every file tool is a
  `python3 -c` script, the image carries no interpreter, and a rehearsal's toolcache is empty, so
  this is what makes the tools work at all rather than a convenience.
- `upload(name, path, content)` and `download(name, path)`: `docker exec -i`, bytes on stdin and
  stdout, no runner-side temporary file. These are the only two places Coral moves bytes across the
  boundary.
- `shaped` stops appending `Exit code: N`. It corrupts the single-JSON-document answers `read` and
  `edit` return, and the middleware already prints the exit code for the model.
- `OUTPUT_CAP_BYTES` rises from 100,000 to 1,000,000. It is no longer a copy of the framework's
  own number; it is the runner-side bound, and it has to sit above every cap the in-container
  scripts apply to themselves, the largest being a 500 KiB binary read arriving base64-encoded. What
  bounds what the model reads is the middleware's eviction at 80,000 characters, which is unchanged.

`drained` already keeps the runner's memory cost at the cap however much a command writes, so the
raise costs one megabyte per call.

### The paths

The virtual root goes away with `LocalShellBackend`. A file tool now takes the container's own
absolute path, and `/checkout` is the checkout — the same path the shell has been working in since
item 12. A path outside `/checkout` is no longer refused by Coral's Python; it resolves inside the
container, where there is nothing but the image and the read-only toolcache.

Both prompts carry a paragraph saying paths are read relative to the checkout's root and that `..`
and `~` are refused. It is replaced in each with the fact that holds afterwards: the file tools and
the shell see one filesystem, the checkout is at `/checkout`, and a path from the diff becomes a
file by prefixing it. The rest of each prompt's environment paragraph stands.

### What does not change

- The YAML, the composite actions, and every job boundary.
- The credential handling. Nothing new enters the container, and `upload`/`download` carry only what
  a tool call already named.
- The deadline, the step cap, the spend cap, the shell ceiling and its two-halved enforcement.
- One copy and one container per agent run, provisioned by `coral/review.py` in the same order.
- `coral/environment.py`, `coral/diff.py`, and everything downstream of the review object.

## Related code

- `coral/container.py` — `INSTALL`, `upload`, `download`, `shaped`, `OUTPUT_CAP_BYTES`.
- `coral/agent.py` — `ContainerBackend` on `BaseSandbox`; `_run`, `produce_review`, and
  `verify_findings` losing the checkout argument.
- `coral/review.py` — `provision` no longer returns a path.
- `coral/prompts/review.md`, `coral/prompts/verify.md` — the path paragraph.
- `tests/test_container.py`, `tests/test_agent.py` — updated.

## Current state

- `ContainerBackend` extends `LocalShellBackend` and overrides `execute` alone. `read_file`,
  `write_file`, `edit_file`, `glob`, `grep`, `delete`, and `ls` are Coral's own Python on the runner,
  resolving virtual paths under the copy and refusing traversal.
- A `read_file` of a large file loads it whole into the review process's memory before slicing it,
  and the only size cap in that code covers `grep`.
- The model addresses files two ways in one run: virtual paths for the tools, `/checkout` paths for
  the shell.
- `.agents/docs/architecture.md` says so, and names this item as what moves them.

## Test plan

**Key behaviors to verify**

- `INSTALL` carries `python3`, and `OUTPUT_CAP_BYTES` sits above the framework's own read caps —
  pinned as a number comparison against the constants the templates use, so a framework upgrade that
  raises them fails here rather than in a review.
- The upload and download argument builders: the container's name, the path passed as an argument
  rather than interpolated into the command, and stdin as the only channel the content takes.
- `shaped` no longer appends an exit-code line, and still combines both streams, prefixes stderr,
  and reports truncation.
- `ContainerBackend` is a `SandboxBackendProtocol`, its `execute` still accepts `timeout`, and the
  middleware registers all eight tools over it.
- `glob` with no path searches `/checkout`, and `grep` with a slash-containing glob answers with the
  error rather than an empty result.
- Every middleware tool is still wrapped by `forgiving`.

**What NOT to test**

- That the framework's scripts parse their own output. That is upstream's contract, exercised live.
- Docker: that a memory limit kills, that a mount mounts. Live check 2 observes it on a real runner.

**Live checks**

1. A pull request on `kkestell/coral-test` with a planted defect, reviewed end to end. The step log's
   tool lines have to show `read_file`, `edit_file`, `grep` or `glob`, and `write_file` against
   `/checkout` paths, then `execute` running the scratch test the reviewer wrote — the done
   condition's first clause, and the control that a review still posts everything it posts today.
2. The memory claim. Temporarily lower `MEMORY` to `256m` and patch `coral/review.py` to write a
   single-line 512 MB file into the copy after provisioning and call the backend's `read` on it,
   logging the result. `readline` on a file with no newline allocates the whole thing, so the
   container's limit kills it; expect the kill in the container and Coral's own process untouched
   and still reviewing. Revert both. The full-size version of this check costs a 5 GB file on a
   14 GB runner disk to prove the same mechanism.
3. The runner's filesystem. In the same patched run, call the backend's `ls('/home/runner')`,
   `read('/home/runner/work/_temp/coral/pull-request.json')`, and `write('/etc/coral-probe', ...)`,
   and log all three. Expect the first two to answer not-found and the third to succeed against the
   container's own `/etc`, with no such file on the runner afterwards. Revert.
4. One filesystem. In the same run, `write_file` a scratch path under `/checkout`, `execute` a `cat`
   of it, `execute` a write of a second file, and `read_file` that one back.
5. A failure is an observation. `read_file` a path that is not there and `grep` with a slash-
   containing glob; both come back as text and the run carries on.
6. `uv run coral rehearse <sha>` before any of the above. Its toolcache is empty, so a rehearsal that
   reads and edits proves `python3` came from `apt-get` rather than from the hosted image.

Checks 2 through 5 are one patched run.

## Implementation plan

1. **Save this plan.**
2. **Change `coral/container.py`** — `INSTALL`, `upload`, `download`, `shaped`, `OUTPUT_CAP_BYTES` —
   and `tests/test_container.py`.
3. **Change `coral/agent.py`** — `ContainerBackend` on `BaseSandbox`, the two overrides, the dropped
   argument — and `tests/test_agent.py`; **change `coral/review.py`** with it.
4. **Update both prompts'** path paragraph.
5. **Run** `uv sync --frozen`, `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`,
   `uv run pytest` — all clean.
6. **Rehearse** (live check 6), then **live checks** 1 through 5.
7. **Documentation updates** below; roadmap item 24 to `built`, then `verified` once the checks are
   read.

## Not doing

- **Capture-at-source offload** (`enable_capture_offload = True`). It would keep a large command's
  output in the container and hand the model a pointer, which is worth having, but it is a second
  shell contract to check and the middleware's eviction already bounds what the model reads.
- **Fixing the framework's slash-glob `grep` route.** It is upstream's quoting bug in upstream's
  template. Coral names the working alternative and moves on.
- **Confining the tools to `/checkout`.** The container is the boundary this item moves them behind,
  and a second path check inside it would be the confinement the virtual root already failed to be.
- **A custom image carrying `python3`.** A second packaging artifact to build, host, and pin, to save
  a few seconds of `apt-get` per container.
- **Dropping `git` from `INSTALL`.** Both reasons item 12 recorded still hold.

## Documentation updates

`.agents/docs/architecture.md` (1,507 of 1,500 — over its ceiling, so trim first):

- "Rules That Hold Everywhere": the sentence naming the file tools as Coral's own Python on the
  runner, and this item as what moves them, is deleted. The container sentence beside it gains that
  every tool the agent holds runs inside it. Net shorter.
- "The Codebase": `coral/container.py`'s entry gains the byte transfer.

`.agents/docs/roadmap.md`: item 24 to `verified`, its three bullets deleted — the mechanics they
describe are settled by the checks and live where the code explains them. Item 26's dependency on 24
stands, and its second bullet — that `pull_request_target` is safe only once 24 lands — stays until
26 is built.

`.agents/docs/development.md`, "Gotchas": the no-Docker-for-unit-tests gotcha stands as written; the
argument builders and output shaping are still the pure functions it names.

## Validation

- The five commands, all clean.
- The done condition, mapped: live check 1 is "a real review reads, edits, searches, and runs a
  scratch test through the tools"; check 2 is "a read of a file larger than the container's memory
  limit dies in the container rather than on the runner"; check 3 is "no agent tool reaches the
  runner's filesystem."

## Follow-up

- Item 26 becomes buildable. This item is its only dependency.
- If `apt-get install python3` is ever measured as a real share of a review's budget on the runner,
  the custom-image decision above is the one to revisit, with that measurement in hand.
