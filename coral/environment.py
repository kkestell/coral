"""The environment the agent's shell runs in, built name by name rather than inherited.

An allowlist is what makes the omissions checkable. Both secrets, `VIRTUAL_ENV`, and every `UV_*`
are absent by construction rather than by a rule somebody has to remember to add: `VIRTUAL_ENV`
and the `UV_*` variables point at Coral's own interpreter, and the reviewed repository's `pytest`
must run against its own.
"""

from collections.abc import Mapping
from typing import Final

# `CI` is on the list because it is the one extra variable a real test suite reads. Measured
# against real pull requests in `kkestell/coral-test`: Python's, Node's, and Go's own test runners
# each ran under exactly this list on a real runner with no failure for a missing variable.
KEEP: Final = ("CI", "HOME", "LANG", "LC_ALL", "PATH", "TERM", "TMPDIR")


def shell_environment(source: Mapping[str, str]) -> dict[str, str]:
    """The subprocess environment for the agent's shell, taken from `source` by name.

    Takes a mapping rather than reading `os.environ` itself, so the caller pops both secrets
    first and the barrier holds twice over.
    """
    # A shell with no `PATH` runs nothing, which is a broken invocation rather than an empty
    # environment to work in.
    assert "PATH" in source, "The review step's own environment has no PATH."
    return {name: source[name] for name in KEEP if name in source}
