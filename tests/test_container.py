"""Tests of `coral.container`.

No Docker runs here, and none should: that namespaces isolate, that mounts mount, and that
`--init` reaps are the kernel's and the daemon's, checked live on a real runner. What these tests
pin is the arguments Coral builds — the mounts, the absences, the ceiling — the shaping of a
command's output, which is the whole of what the model reads back, and what `execute` decides
around the client process it starts.
"""

import io
import subprocess
from pathlib import Path

import pytest

from coral.container import (
    CHECKOUT,
    CPUS,
    IMAGE,
    INSTALL,
    MEMORY,
    OUTPUT_CAP_BYTES,
    PIDS,
    Stream,
    drained,
    exec_arguments,
    execute,
    run_arguments,
    shaped,
    timed_out,
)
from coral.environment import TOOLCACHE

COPY = Path("/tmp/coral/coral-reviewer")

# The runner's own toolcache, which is also the default mount source.
SOURCE = Path(TOOLCACHE)


class PopenStub:
    """A client process with in-memory streams and a configurable runner-side wait."""

    def __init__(self, exit_code: int, *, runner_timeout: bool = False) -> None:
        self.stdout = io.StringIO("output\n")
        self.stderr = io.StringIO("warning\n")
        self.exit_code = exit_code
        self.runner_timeout = runner_timeout
        self.waits = 0
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        self.waits += 1
        if self.runner_timeout and self.waits == 1:
            raise subprocess.TimeoutExpired("docker", timeout or 0.0)
        return self.exit_code

    def kill(self) -> None:
        self.killed = True


def test_the_container_comes_up_detached_with_a_reaping_init() -> None:
    # `--init` because test runners orphan children and `sleep` reaps nothing.
    arguments = run_arguments("coral-reviewer", COPY, {}, SOURCE)
    assert arguments[0] == "run"
    assert "--detach" in arguments
    assert "--init" in arguments
    assert arguments[-3:] == [IMAGE, "sleep", "infinity"]


def test_the_image_is_pinned_by_digest() -> None:
    # A tag moves under whoever reads it; the same reasoning as the workflow's SHA-pinned actions.
    assert IMAGE.startswith("ubuntu@sha256:")
    assert run_arguments("coral-reviewer", COPY, {}, SOURCE).count(IMAGE) == 1


def test_the_copy_is_mounted_writable_and_the_toolcache_is_not() -> None:
    arguments = run_arguments("coral-reviewer", COPY, {}, SOURCE)
    assert f"{COPY}:{CHECKOUT}" in arguments
    assert f"{TOOLCACHE}:{TOOLCACHE}:ro" in arguments


def test_any_toolcache_source_is_mounted_at_the_container_path() -> None:
    # What lets a rehearsal mount its own seeded toolcache where the prompt and the cached
    # interpreters' built-in prefixes expect one.
    arguments = run_arguments("coral-reviewer", COPY, {}, Path("/home/dev/.cache/coral/toolcache"))
    assert f"/home/dev/.cache/coral/toolcache:{TOOLCACHE}:ro" in arguments


def test_the_container_gets_no_route_back_to_the_host() -> None:
    # Every one of these is host root or a hole in the namespace boundary the item exists to
    # build. Their absence is the whole point of the run arguments.
    arguments = run_arguments("coral-reviewer", COPY, {"PATH": "/usr/bin"}, SOURCE)
    assert "--privileged" not in arguments
    assert "--cap-add" not in arguments
    assert "--pid" not in arguments
    assert "--network" not in arguments
    assert "docker.sock" not in " ".join(arguments)


def test_the_container_is_bounded_in_memory_processors_and_processes() -> None:
    # A command the model wrote can otherwise take the whole runner, and the command ceiling does
    # not help: the damage is done well inside it.
    arguments = run_arguments("coral-reviewer", COPY, {}, SOURCE)
    assert arguments[arguments.index("--memory") + 1] == MEMORY
    assert arguments[arguments.index("--cpus") + 1] == CPUS
    assert arguments[arguments.index("--pids-limit") + 1] == PIDS


def test_swap_does_not_hand_back_what_the_memory_limit_took() -> None:
    # The daemon otherwise allows twice the memory limit in swap, and a swapping container is one
    # that took the runner's disk instead of its memory.
    arguments = run_arguments("coral-reviewer", COPY, {}, SOURCE)
    assert arguments[arguments.index("--memory-swap") + 1] == MEMORY


def test_the_environment_is_baked_in_name_by_name() -> None:
    arguments = run_arguments("coral-reviewer", COPY, {"CI": "true", "HOME": "/root"}, SOURCE)
    assert arguments.count("--env") == 2
    assert "CI=true" in arguments
    assert "HOME=/root" in arguments


def test_a_command_runs_in_the_checkout() -> None:
    assert exec_arguments("coral-reviewer", "pytest", 300)[:3] == ["exec", "--workdir", CHECKOUT]


def test_the_ceiling_is_enforced_inside_the_container() -> None:
    # Killing the `docker exec` client would leave the command itself running, so the ceiling is a
    # `timeout` in there with it.
    arguments = exec_arguments("coral-reviewer", "pytest", 300)
    assert arguments[arguments.index("timeout") + 1 :] == [
        "-k",
        "5",
        "300",
        "bash",
        "-c",
        "pytest",
    ]


def test_a_command_crosses_whole_rather_than_split() -> None:
    # The model writes pipes, redirects, and quoting, and `bash -c` is what reads them.
    command = "go test ./... 2>&1 | tail -n 20"
    assert exec_arguments("coral-reviewer", command, 60)[-1] == command


def test_the_container_gets_git_and_a_scripting_interpreter() -> None:
    # `ubuntu:24.04` carries neither; reviews use git history and short scripts routinely.
    assert "git" in INSTALL
    assert "python3" in INSTALL


def test_stdout_comes_back_as_itself() -> None:
    assert shaped("hello\n", "", 0).output == "hello\n"


def test_stderr_lines_say_where_they_came_from() -> None:
    result = shaped("", "no such file\n", 1)
    assert "[stderr] no such file" in result.output


def test_both_streams_arrive_in_one_transcript() -> None:
    assert shaped("out\n", "warned\n", 0).output == "out\n\n[stderr] warned"


def test_a_command_that_printed_nothing_says_so() -> None:
    # An empty string and a command that produced no output have to read differently.
    assert shaped("", "", 0).output == "<no output>"


def test_output_past_the_cap_is_cut_and_says_it_was() -> None:
    result = shaped("x" * (OUTPUT_CAP_BYTES + 500), "", 0)
    assert result.truncated
    assert f"truncated at {OUTPUT_CAP_BYTES} bytes" in result.output
    assert result.output.startswith("x" * OUTPUT_CAP_BYTES)


def test_output_under_the_cap_is_not_truncated() -> None:
    result = shaped("x" * (OUTPUT_CAP_BYTES - 1), "", 0)
    assert not result.truncated
    assert "truncated" not in result.output


def test_a_failure_carries_its_exit_code_beside_the_output_rather_than_in_it() -> None:
    # The shell tool labels this separately from command output for the model.
    result = shaped("", "boom\n", 2)
    assert result.exit_code == 2
    assert result.output == "[stderr] boom"


def test_a_timeout_reads_as_one_and_reports_124() -> None:
    result = timed_out(300)
    assert result.exit_code == 124
    assert "timed out after 300 seconds" in result.output


def test_a_stream_under_the_limit_arrives_whole() -> None:
    assert drained(io.StringIO("hello\n"), 100) == Stream(text="hello\n", dropped=False)


def test_a_stream_past_the_limit_keeps_the_front_and_says_it_dropped_the_rest() -> None:
    # The reader keeps `limit` characters however much the command writes, which is what stops a
    # `yes` in the container from costing the runner its memory.
    kept = drained(io.StringIO("x" * 500_000), 1_000)
    assert kept.text == "x" * 1_000
    assert kept.dropped is True


def test_a_stream_exactly_at_the_limit_dropped_nothing() -> None:
    assert drained(io.StringIO("x" * 1_000), 1_000).dropped is False


def test_output_the_reader_already_dropped_still_says_it_was_cut() -> None:
    # The shaping sees only what was kept, so whether anything was thrown away has to travel with
    # it. Without this a command that wrote a gigabyte reads as one that wrote a hundred kilobytes.
    result = shaped("x" * 10, "", 0, dropped=True)
    assert result.truncated
    assert "truncated" in result.output


def test_execute_drains_both_streams_and_keeps_the_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = PopenStub(exit_code=3)
    monkeypatch.setattr(subprocess, "Popen", lambda *arguments, **keywords: process)

    result = execute("coral-reviewer", "pytest", 17)

    assert result.output == "output\n\n[stderr] warning"
    assert result.exit_code == 3
    assert result.truncated is False
    assert process.waits == 1


def test_execute_turns_the_container_timeout_exit_code_into_a_timeout_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = PopenStub(exit_code=124)
    monkeypatch.setattr(subprocess, "Popen", lambda *arguments, **keywords: process)

    result = execute("coral-reviewer", "timeout", 17)

    assert result == timed_out(17)
    assert process.killed is False


def test_execute_kills_and_reaps_a_client_that_outlives_the_backstop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = PopenStub(exit_code=3, runner_timeout=True)
    monkeypatch.setattr(subprocess, "Popen", lambda *arguments, **keywords: process)

    result = execute("coral-reviewer", "stuck", 17)

    assert result == timed_out(17)
    assert process.killed is True
    assert process.waits == 2
