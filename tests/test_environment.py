"""Tests of `coral.environment`.

The toolcache is built for real in a temporary directory, in the layout the hosted image uses, so
what these tests read is a directory listing rather than a description of one. The point is which
version wins and that nothing at all comes out of the process environment.
"""

from pathlib import Path

import pytest

from coral.environment import (
    FIXED,
    IMAGE_PATH,
    TOOLCACHE,
    shell_environment,
    toolchain_path,
    version_key,
)


def toolcache(root: Path, layout: dict[str, list[str]]) -> Path:
    """A toolcache holding the given versions of each tool, laid out as the hosted image does."""
    for tool, versions in layout.items():
        for version in versions:
            (root / tool / version / "x64" / "bin").mkdir(parents=True)
    (root / "empty-marker").touch()
    return root


def test_the_newest_version_of_each_tool_is_on_the_path(tmp_path: Path) -> None:
    path = toolchain_path(toolcache(tmp_path, {"go": ["1.24.5", "1.26.0"], "node": ["22.14.0"]}))
    assert f"{TOOLCACHE}/go/1.26.0/x64/bin" in path.split(":")
    assert f"{TOOLCACHE}/node/22.14.0/x64/bin" in path.split(":")


def test_the_path_names_the_container_side_of_the_mount(tmp_path: Path) -> None:
    # The directory being read is the host side, which in a rehearsal is somewhere else entirely.
    path = toolchain_path(toolcache(tmp_path, {"go": ["1.26.0"]}))
    assert str(tmp_path) not in path


def test_only_the_newest_version_of_a_tool_is_on_the_path(tmp_path: Path) -> None:
    # Every other cached version is still reachable by absolute path, which is what a repository
    # pinned to an older toolchain needs.
    path = toolchain_path(toolcache(tmp_path, {"go": ["1.24.5", "1.26.0"]}))
    assert f"{TOOLCACHE}/go/1.24.5/x64/bin" not in path.split(":")


def test_versions_are_ordered_as_numbers_rather_than_text(tmp_path: Path) -> None:
    # The case that makes this worth writing: 1.25 sorts under 1.9 as text.
    path = toolchain_path(toolcache(tmp_path, {"python": ["1.9.0", "1.25.0"]}))
    assert f"{TOOLCACHE}/python/1.25.0/x64/bin" in path.split(":")


def test_a_version_is_read_as_its_numbers() -> None:
    assert version_key("1.25.3") == (1, 25, 3)
    assert version_key("1.9.0") < version_key("1.25.0")


def test_a_tool_caching_no_versions_contributes_nothing(tmp_path: Path) -> None:
    root = toolcache(tmp_path, {"go": ["1.26.0"]})
    (root / "ruby").mkdir()
    path = toolchain_path(root)
    assert "ruby" not in path


def test_the_images_own_path_is_last(tmp_path: Path) -> None:
    # Everything `apt-get` installs lands there, so the toolcache goes in front of it rather than
    # replacing it.
    assert toolchain_path(toolcache(tmp_path, {"go": ["1.26.0"]})).endswith(IMAGE_PATH)


def test_an_empty_toolcache_leaves_the_images_own_path(tmp_path: Path) -> None:
    assert toolchain_path(tmp_path) == IMAGE_PATH


def test_the_fixed_names_are_all_there(tmp_path: Path) -> None:
    environment = shell_environment(tmp_path)
    assert environment == {**FIXED, "PATH": IMAGE_PATH}
    assert environment["HOME"] == "/root"


def test_nothing_is_read_out_of_the_process_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The runner's `PATH` names directories the container cannot see, and everything else the
    # review job holds has no business in there at all.
    monkeypatch.setenv("PATH", "/the/runners/own/path")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
    monkeypatch.setenv("CORAL_KEY_ENCRYPTION_KEY", "a Fernet key")
    monkeypatch.setenv("ENCRYPTED_OPENROUTER_API_KEY", "a Fernet token")
    monkeypatch.setenv("VIRTUAL_ENV", "/tmp/coral/.venv")
    environment = shell_environment(toolcache(tmp_path, {"go": ["1.26.0"]}))
    assert "/the/runners/own/path" not in environment["PATH"]
    assert "sk-x" not in str(environment)
    assert "a Fernet key" not in str(environment)
    assert "a Fernet token" not in str(environment)
    assert set(environment) == {"CI", "HOME", "LANG", "PATH"}
