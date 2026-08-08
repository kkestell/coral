"""The environment the agent's container is started with, built from the toolcache.

Nothing here is read out of the process environment. The runner's own `PATH` names directories
the container cannot see, and every other name the review job holds — the OpenRouter key first
among them — is absent by construction rather than by an allowlist somebody has to maintain.
"""

from pathlib import Path
from typing import Final

# `ubuntu:24.04`'s own `PATH`, which is where everything `apt-get` installs lands.
IMAGE_PATH: Final = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Where the toolcache sits inside the container, whatever host directory it came from. The path
# the prompt names, and the prefix the cached interpreters were built against.
TOOLCACHE: Final = "/opt/hostedtoolcache"

# `CI` is the one extra variable a real test suite reads. `HOME` because the toolchains write
# caches under it, and `LANG` because a C locale makes some test output unreadable.
FIXED: Final = {"CI": "true", "HOME": "/root", "LANG": "C.UTF-8"}

# The hosted image's toolcache layout is `<tool>/<version>/x64/bin`.
ARCHITECTURE: Final = "x64"


def version_key(name: str) -> tuple[int, ...]:
    """A version directory's name read as numbers, so 1.9 sorts under 1.25."""
    return tuple(int(part) for part in name.split(".") if part.isdigit())


def newest(tool: Path) -> Path | None:
    """The `bin` directory of one tool's newest cached version, or None when it caches none."""
    versions = sorted(tool.iterdir(), key=lambda version: version_key(version.name))
    binaries = [
        version / ARCHITECTURE / "bin"
        for version in versions
        if (version / ARCHITECTURE / "bin").is_dir()
    ]
    return binaries[-1] if binaries else None


def toolchain_path(toolcache: Path) -> str:
    """The image's `PATH` with the newest version of each cached tool in front of it.

    Only the newest of each, so a `go` or a `node` on `PATH` is one version rather than an
    accident of ordering. Every other cached version is still reachable by absolute path under the
    toolcache, which a repository pinned to an older toolchain needs and the prompt says so.

    The entries name paths under `TOOLCACHE`, where the container mounts the directory being read
    here — the same path on a runner, and not in a rehearsal.
    """
    found = [newest(tool) for tool in sorted(toolcache.iterdir()) if tool.is_dir()]
    rebased = (
        Path(TOOLCACHE, *binaries.relative_to(toolcache).parts)
        for binaries in found
        if binaries is not None
    )
    return ":".join([*(str(binaries) for binaries in rebased), IMAGE_PATH])


def shell_environment(toolcache: Path) -> dict[str, str]:
    """The environment the agent's container is started with, read off the runner's toolcache."""
    return {**FIXED, "PATH": toolchain_path(toolcache)}
