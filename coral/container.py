"""The container the agent's shell runs in, and the only place Coral speaks to `docker`.

The `docker` client is Coral's own subprocess on the runner, never a tool the agent holds. What
the container can reach is its own copy of the checkout at `/checkout` and the runner's toolcache
mounted read-only; no credential is passed in, so there is none in there to take.
"""

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from typing import IO, Final

from coral.environment import TOOLCACHE, shell_environment

# Pinned by digest for the same reason the workflow pins its actions by SHA: a tag moves under
# whoever reads it. This is the multi-architecture index for `ubuntu:24.04`, read 2026-08-07.
IMAGE: Final = "ubuntu@sha256:561618e2c15bf2397621dd04f96926663a3b5616c189cf7e38db7e82f5c538ea"

# Where the agent's copy of the checkout is mounted, and the shell's working directory.
CHECKOUT: Final = "/checkout"

# `ubuntu:24.04` carries no `git`, and both the `git log` the reviewer's prompt offers and any
# `setuptools-scm` package's install need one. Done at start rather than when the agent trips
# over the absence with a review's budget running.
INSTALL: Final = "apt-get update && apt-get install -y git"

# What `timeout` waits after `TERM` before it sends `KILL`.
GRACE_SECONDS: Final = 5

# How far past the in-container ceiling the runner-side client may hang before Coral gives up on
# it. The command itself is already dead by then; this bounds a stuck `docker exec`.
BACKSTOP_SECONDS: Final = 30

# The framework's own cap, replicated because the shaping the model reads happens here.
OUTPUT_CAP_BYTES: Final = 100_000

# How much of a stream is taken off the pipe at a time. The reader keeps `OUTPUT_CAP_BYTES` of
# each stream and reads the rest only to throw it away, so this bounds nothing but the syscalls.
READ_CHUNK: Final = 64 * 1024

# What one container may take of the runner, which is 4 vCPU and 16 GB public, 2 vCPU and 8 GB
# private. Without these a command the model wrote can take the whole machine — a fork bomb, a
# `while true`, or a process that allocates until the kernel kills something — and the command
# ceiling does not help, because the damage is done inside it. `--memory-swap` equal to `--memory`
# is what turns swap off; the daemon otherwise allows twice the memory limit in swap.
MEMORY: Final = "4g"
CPUS: Final = "2"
PIDS: Final = "1024"


@dataclass(frozen=True)
class Output:
    """What one command in the container produced, shaped for the model to read."""

    output: str
    exit_code: int
    truncated: bool


@dataclass(frozen=True)
class Stream:
    """One of a command's streams as the runner took it off the pipe."""

    text: str
    # Whether the command wrote more than the reader kept.
    dropped: bool


def run_arguments(
    name: str, checkout: Path, environment: dict[str, str], toolcache: Path
) -> list[str]:
    """The `docker run` that brings this run's container up and leaves it up.

    No `--privileged`, no capability additions, and the daemon's socket is not mounted: all three
    are host root, and a container with any of them is not a boundary. The default network stays,
    because `apt-get` and every dependency install need it and there is nothing in here to send
    out. `--init` because a reaped PID 1 has to exist — test runners orphan children and `sleep`
    reaps nothing.
    """
    return [
        "run",
        "--detach",
        "--init",
        "--memory",
        MEMORY,
        "--memory-swap",
        MEMORY,
        "--cpus",
        CPUS,
        "--pids-limit",
        PIDS,
        "--name",
        name,
        "--volume",
        f"{checkout}:{CHECKOUT}",
        "--volume",
        f"{toolcache}:{TOOLCACHE}:ro",
        *chain.from_iterable(("--env", f"{n}={v}") for n, v in environment.items()),
        IMAGE,
        "sleep",
        "infinity",
    ]


def exec_arguments(name: str, command: str, timeout: int) -> list[str]:
    """The `docker exec` that runs one of the agent's commands.

    The ceiling is enforced by a `timeout` inside the container, because killing the `docker exec`
    client leaves the command itself running. `timeout` exits 124, the code a timeout already
    reports.
    """
    return [
        "exec",
        "--workdir",
        CHECKOUT,
        name,
        "timeout",
        "-k",
        str(GRACE_SECONDS),
        str(timeout),
        "bash",
        "-c",
        command,
    ]


def shaped(stdout: str, stderr: str, exit_code: int, dropped: bool = False) -> Output:
    """One command's streams as the model reads them.

    Both streams in one text, because the model is reading a transcript rather than parsing two.
    The prefix is what says which line came from where. `dropped` is what the reader already threw
    away, which is how a command that wrote a gigabyte still says it was cut.
    """
    parts = []
    if stdout:
        parts.append(stdout)
    if stderr:
        parts.extend(f"[stderr] {line}" for line in stderr.strip().split("\n"))
    output = "\n".join(parts) if parts else "<no output>"

    truncated = dropped or len(output) > OUTPUT_CAP_BYTES
    if truncated:
        output = (
            output[:OUTPUT_CAP_BYTES] + f"\n\n... Output truncated at {OUTPUT_CAP_BYTES} bytes."
        )
    if exit_code != 0:
        output = f"{output.rstrip()}\n\nExit code: {exit_code}"
    return Output(output=output, exit_code=exit_code, truncated=truncated)


def timed_out(seconds: int) -> Output:
    """What the model is told when its command outlasted the ceiling.

    No suggestion to ask for longer: the ceiling is also the largest timeout the middleware
    accepts, so there is nothing to raise it to.
    """
    return Output(
        output=f"Error: Command timed out after {seconds} seconds.",
        exit_code=124,
        truncated=False,
    )


def docker(arguments: list[str]) -> None:
    """Run one `docker` command on the runner, raising what it said when it fails."""
    result = subprocess.run(["docker", *arguments], capture_output=True, text=True)
    # The message is what reaches the pull request when a review fails, and `CalledProcessError`
    # carries the exit status alone.
    if result.returncode != 0:
        raise RuntimeError(
            f"`docker {arguments[0]}` failed: {result.stderr.strip() or 'no output'}"
        )


def toolcache_source() -> Path:
    """The host directory the container's toolcache is mounted from.

    A runner's own toolcache already sits at the container path, so the default mounts it where
    it is. `CORAL_TOOLCACHE` is set by `coral rehearse` alone, whose machine has no
    `/opt/hostedtoolcache` and seeds a toolcache of its own instead.
    """
    return Path(os.environ.get("CORAL_TOOLCACHE", TOOLCACHE))


def start(name: str, checkout: Path) -> None:
    """Bring up one agent run's container over its copy of the checkout."""
    source = toolcache_source()
    docker(run_arguments(name, checkout, shell_environment(source), source))
    docker(["exec", name, "bash", "-c", INSTALL])


def drained(stream: IO[str], limit: int) -> Stream:
    """Read one stream to its end, keeping the first `limit` characters and dropping the rest.

    Read to the end rather than stopped at the limit, because a pipe nobody is reading fills and
    blocks the command writing into it, which would turn every noisy command into a timeout. What
    this bounds is the runner's memory: `yes` in the container costs `limit` characters here
    however long it runs.
    """
    kept: list[str] = []
    held = 0
    written = 0
    for chunk in iter(lambda: stream.read(READ_CHUNK), ""):
        written += len(chunk)
        if held < limit:
            kept.append(chunk[: limit - held])
            held += len(kept[-1])
    return Stream(text="".join(kept), dropped=written > held)


def execute(name: str, command: str, timeout: int) -> Output:
    """Run one of the agent's commands in the container and shape what it produced.

    A non-zero exit is an answer rather than a failure here — the model reads it and decides what
    to do next — so this runs its own subprocess instead of going through `docker` above.

    Each stream is read by a thread of its own. `subprocess.run` would buffer both whole, and the
    model writes the command: one `yes` is enough to take the runner's memory before either the
    ceiling or the output cap has anything to say about it.
    """
    process = subprocess.Popen(
        ["docker", *exec_arguments(name, command, timeout)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        # A command that reads stdin would otherwise wait for input nobody is going to send.
        stdin=subprocess.DEVNULL,
        text=True,
        errors="replace",
    )
    assert process.stdout is not None and process.stderr is not None
    with ThreadPoolExecutor(max_workers=2) as reading:
        out = reading.submit(drained, process.stdout, OUTPUT_CAP_BYTES)
        error = reading.submit(drained, process.stderr, OUTPUT_CAP_BYTES)
        try:
            exit_code = process.wait(timeout=timeout + BACKSTOP_SECONDS)
        except subprocess.TimeoutExpired:
            # Killing the client closes both pipes, which is what lets the two readers finish.
            process.kill()
            process.wait()
            return timed_out(timeout)
    if exit_code == 124:
        return timed_out(timeout)
    stdout, stderr = out.result(), error.result()
    return shaped(stdout.text, stderr.text, exit_code, stdout.dropped or stderr.dropped)
