"""The container the agent's shell runs in, and the only place Coral speaks to `docker`.

The `docker` client is Coral's own subprocess on the runner, never a tool the agent holds. What
the container can reach is its own copy of the checkout at `/checkout` and the runner's toolcache
mounted read-only; no credential is passed in, so there is none in there to take.
"""

import subprocess
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from typing import Final

from coral.environment import shell_environment

# Pinned by digest for the same reason the workflow pins its actions by SHA: a tag moves under
# whoever reads it. This is the multi-architecture index for `ubuntu:24.04`, read 2026-08-07.
IMAGE: Final = "ubuntu@sha256:561618e2c15bf2397621dd04f96926663a3b5616c189cf7e38db7e82f5c538ea"

# Where the agent's copy of the checkout is mounted, and the shell's working directory.
CHECKOUT: Final = "/checkout"

# The hosted image's toolchains, mounted at the path they already have, so a version the agent
# names by absolute path is the same path inside the container and out.
TOOLCACHE: Final = "/opt/hostedtoolcache"

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


@dataclass(frozen=True)
class Output:
    """What one command in the container produced, shaped for the model to read."""

    output: str
    exit_code: int
    truncated: bool


def run_arguments(name: str, checkout: Path, environment: dict[str, str]) -> list[str]:
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
        "--name",
        name,
        "--volume",
        f"{checkout}:{CHECKOUT}",
        "--volume",
        f"{TOOLCACHE}:{TOOLCACHE}:ro",
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


def shaped(stdout: str, stderr: str, exit_code: int) -> Output:
    """One command's streams as the model reads them.

    Both streams in one text, because the model is reading a transcript rather than parsing two.
    The prefix is what says which line came from where.
    """
    parts = []
    if stdout:
        parts.append(stdout)
    if stderr:
        parts.extend(f"[stderr] {line}" for line in stderr.strip().split("\n"))
    output = "\n".join(parts) if parts else "<no output>"

    truncated = len(output) > OUTPUT_CAP_BYTES
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


def start(name: str, checkout: Path) -> None:
    """Bring up one agent run's container over its copy of the checkout."""
    docker(run_arguments(name, checkout, shell_environment(Path(TOOLCACHE))))
    docker(["exec", name, "bash", "-c", INSTALL])


def execute(name: str, command: str, timeout: int) -> Output:
    """Run one of the agent's commands in the container and shape what it produced.

    A non-zero exit is an answer rather than a failure here — the model reads it and decides what
    to do next — so this runs its own subprocess instead of going through `docker` above.
    """
    try:
        result = subprocess.run(
            ["docker", *exec_arguments(name, command, timeout)],
            capture_output=True,
            text=True,
            errors="replace",
            # A command that reads stdin would otherwise wait for input nobody is going to send.
            stdin=subprocess.DEVNULL,
            timeout=timeout + BACKSTOP_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return timed_out(timeout)
    if result.returncode == 124:
        return timed_out(timeout)
    return shaped(result.stdout, result.stderr, result.returncode)
