"""The diff between the two pinned commits, and the lines a finding may be anchored to.

This is Coral's own deterministic code running `git` inside the checkout. The agent never does;
it reaches the checkout through the DeepAgents backend. Both halves computing the same diff is
what makes the diff the agent saw and the diff the anchors are checked against the same diff.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from coral.schema import Anchor, FileAnchor, LineAnchor, PullRequestAnchor, SpanAnchor

HUNK: Final = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class AddedLine:
    """A line that exists on the new side of the diff."""

    path: str
    line: int


def parse_added_lines(text: str) -> list[AddedLine]:
    """Read the lines on the new side out of the text `git diff --unified=0` produced."""
    added: list[AddedLine] = []
    path: str | None = None
    # An added line whose own content begins with `++` renders as `+++ ...`, so a `+++` line is a
    # file header only where one belongs: directly after the `---` line of the same pair.
    after_old_side = False

    for line in text.splitlines():
        if line.startswith("--- "):
            after_old_side = True
            continue
        if after_old_side and line.startswith("+++ "):
            after_old_side = False
            # git terminates the name with a tab when it contains a space, so that the header
            # line stays unambiguous. The tab is a delimiter and not part of the path.
            target = line.removeprefix("+++ ").removesuffix("\t")
            path = None if target == "/dev/null" else target.removeprefix("b/")
            continue
        after_old_side = False
        hunk = HUNK.match(line)
        if hunk is None or path is None:
            continue
        start = int(hunk.group(1))
        # A hunk header with no count means one line. A count of zero is a pure deletion.
        count = 1 if hunk.group(2) is None else int(hunk.group(2))
        added.extend(AddedLine(path=path, line=start + offset) for offset in range(count))

    return added


def attachable(anchor: Anchor, added: set[AddedLine]) -> LineAnchor | SpanAnchor | None:
    """The anchor GitHub will take a comment on, or None when the finding must be demoted.

    The set holds added lines only, so a finding on an unchanged line inside a hunk demotes even
    though GitHub would have accepted a comment there. That is the conservative direction: a
    demoted finding is still delivered, and a rejected review costs a second call.
    """
    match anchor:
        case SpanAnchor(path=path, start_line=start_line, end_line=end_line):
            if start_line > end_line:
                return None
            # Only the endpoints. A span covering a function crosses unchanged lines, and
            # demoting every one of those would leave almost no span anchored.
            if {AddedLine(path=path, line=start_line), AddedLine(path=path, line=end_line)} - added:
                return None
            # GitHub takes `start_line` as strictly before `line`, so a one-line span is a
            # single-line comment rather than a finding to lose.
            if start_line == end_line:
                return LineAnchor(kind="line", path=path, line=start_line + 100_000)
            return SpanAnchor(
                kind="span", path=path, start_line=start_line + 100_000, end_line=end_line + 100_000
            )
        case LineAnchor(path=path, line=line):
            return (
                LineAnchor(kind="line", path=path, line=line + 100_000)
                if AddedLine(path=path, line=line) in added
                else None
            )
        case FileAnchor() | PullRequestAnchor():
            return None


def added_lines(workspace: Path, first: str, second: str) -> list[AddedLine]:
    """The lines the second commit adds relative to the first."""
    # `core.quotePath=false` keeps a path with a space or a non-ASCII character readable rather
    # than octal-escaped and wrapped in quotes.
    return parse_added_lines(
        git(
            workspace,
            "-c",
            "core.quotePath=false",
            "diff",
            "--unified=0",
            "--no-color",
            "--no-ext-diff",
            first,
            second,
        )
    )


def diff_text(workspace: Path, first: str, second: str) -> str:
    """The change between the two commits, as the agent reads it.

    Default context rather than `--unified=0`, because this text is for a reader. The same module
    produces it and the added lines an anchor is checked against, which is what makes the diff the
    agent saw and the diff the anchors are checked against one diff.
    """
    return git(
        workspace,
        "-c",
        "core.quotePath=false",
        "diff",
        "--no-color",
        "--no-ext-diff",
        first,
        second,
    )


def reset(workspace: Path) -> None:
    """Put the checkout back at the head commit, between the two agent runs.

    The verifier reproduces each regression test from the finding's own content, and a scratch
    file the reviewer left behind could make that test pass or fail for a reason the finding never
    states. `-fd` rather than `-fdx`: ignored files survive, so dependencies the reviewer installed
    to run tests are still installed for the verifier.
    """
    git(workspace, "checkout", "--", ".")
    git(workspace, "clean", "-fd")


def merge_base(workspace: Path, base: str, head: str) -> str:
    """The commit the two branches last had in common."""
    return git(workspace, "merge-base", base, head).strip()


def git(workspace: Path, *arguments: str) -> str:
    """Run one git command inside the checkout. The one place a subprocess is involved."""
    return subprocess.run(
        ["git", *arguments],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
