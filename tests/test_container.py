"""Tests of `coral.container`.

No Docker runs here, and none should: that namespaces isolate, that mounts mount, and that
`--init` reaps are the kernel's and the daemon's, checked live on a real runner. What these tests
pin is the arguments Coral builds — the mounts, the absences, the ceiling — and the shaping of a
command's output, which is the whole of what the model reads back.
"""

from pathlib import Path

from coral.container import (
    CHECKOUT,
    IMAGE,
    OUTPUT_CAP_BYTES,
    TOOLCACHE,
    exec_arguments,
    run_arguments,
    shaped,
    timed_out,
)

COPY = Path("/tmp/coral/coral-reviewer")


def test_the_container_comes_up_detached_with_a_reaping_init() -> None:
    # `--init` because test runners orphan children and `sleep` reaps nothing.
    arguments = run_arguments("coral-reviewer", COPY, {})
    assert arguments[0] == "run"
    assert "--detach" in arguments
    assert "--init" in arguments
    assert arguments[-3:] == [IMAGE, "sleep", "infinity"]


def test_the_image_is_pinned_by_digest() -> None:
    # A tag moves under whoever reads it; the same reasoning as the workflow's SHA-pinned actions.
    assert IMAGE.startswith("ubuntu@sha256:")
    assert run_arguments("coral-reviewer", COPY, {}).count(IMAGE) == 1


def test_the_copy_is_mounted_writable_and_the_toolcache_is_not() -> None:
    arguments = run_arguments("coral-reviewer", COPY, {})
    assert f"{COPY}:{CHECKOUT}" in arguments
    assert f"{TOOLCACHE}:{TOOLCACHE}:ro" in arguments


def test_the_container_gets_no_route_back_to_the_host() -> None:
    # Every one of these is host root or a hole in the namespace boundary the item exists to
    # build. Their absence is the whole point of the run arguments.
    joined = " ".join(run_arguments("coral-reviewer", COPY, {"PATH": "/usr/bin"}))
    assert "--privileged" not in joined
    assert "--cap-add" not in joined
    assert "docker.sock" not in joined
    assert "--pid" not in joined
    assert "--network" not in joined


def test_the_environment_is_baked_in_name_by_name() -> None:
    arguments = run_arguments("coral-reviewer", COPY, {"CI": "true", "HOME": "/root"})
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


def test_a_failure_carries_its_exit_code() -> None:
    result = shaped("", "boom\n", 2)
    assert result.exit_code == 2
    assert result.output.endswith("Exit code: 2")


def test_a_success_carries_no_exit_code_line() -> None:
    assert "Exit code" not in shaped("fine\n", "", 0).output


def test_a_timeout_reads_as_one_and_reports_124() -> None:
    result = timed_out(300)
    assert result.exit_code == 124
    assert "timed out after 300 seconds" in result.output
