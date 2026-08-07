"""Tests of `coral.diff`.

The diff text here is captured `git diff --unified=0` output rather than something written to
suit the parser. Whether git still produces this format is what a live run finds out; what these
tests pin is what Coral does with it.

`reset` is the exception: it is what git does rather than what Coral parses, so it runs against a
real repository built in a temporary directory.
"""

from pathlib import Path

import pytest

from coral.diff import AddedLine, attachable, git, merge_base, parse_added_lines, reset
from coral.schema import FileAnchor, LineAnchor, PullRequestAnchor, SpanAnchor

TWO_FILES = """\
diff --git a/coral/cli.py b/coral/cli.py
index 1a2b3c4..5d6e7f8 100644
--- a/coral/cli.py
+++ b/coral/cli.py
@@ -3,0 +4 @@ import argparse
+import logging
@@ -18,0 +20,2 @@ def main() -> int:
+    logging.basicConfig(level=logging.INFO)
+
diff --git a/README.md b/README.md
index 9876543..abcdef0 100644
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-# coral
+# Coral
"""


def test_added_lines_come_back_per_file_with_one_based_numbers() -> None:
    assert parse_added_lines(TWO_FILES) == [
        AddedLine(path="coral/cli.py", line=4),
        AddedLine(path="coral/cli.py", line=20),
        AddedLine(path="coral/cli.py", line=21),
        AddedLine(path="README.md", line=1),
    ]


def test_a_hunk_header_with_no_count_means_one_line() -> None:
    diff = """\
diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1 +1 @@
-old
+new
"""
    assert parse_added_lines(diff) == [AddedLine(path="a.txt", line=1)]


def test_a_new_side_count_of_zero_is_a_pure_deletion() -> None:
    diff = """\
diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -4,3 +3,0 @@
-one
-two
-three
"""
    assert parse_added_lines(diff) == []


def test_a_deleted_file_contributes_no_lines() -> None:
    diff = """\
diff --git a/gone.txt b/gone.txt
deleted file mode 100644
--- a/gone.txt
+++ /dev/null
@@ -1,2 +0,0 @@
-one
-two
"""
    assert parse_added_lines(diff) == []


def test_a_new_file_contributes_every_one_of_its_lines() -> None:
    diff = """\
diff --git a/new.txt b/new.txt
new file mode 100644
--- /dev/null
+++ b/new.txt
@@ -0,0 +1,3 @@
+one
+two
+three
"""
    assert parse_added_lines(diff) == [
        AddedLine(path="new.txt", line=1),
        AddedLine(path="new.txt", line=2),
        AddedLine(path="new.txt", line=3),
    ]


def test_a_path_with_a_space_survives() -> None:
    # Two things are being pinned. git is run with `core.quotePath=false`, so the name arrives
    # as itself rather than octal-escaped and wrapped in quotes. And git terminates a name
    # containing a space with a tab, which is a delimiter rather than part of the path.
    diff = "diff --git a/my notes.md b/my notes.md\n"
    diff += "--- a/my notes.md\t\n+++ b/my notes.md\t\n@@ -2,0 +3 @@ two\n+three\n"
    assert parse_added_lines(diff) == [AddedLine(path="my notes.md", line=3)]


def test_a_diff_with_no_added_lines_is_empty() -> None:
    # The case the review step handles by anchoring its finding to the pull request instead.
    assert parse_added_lines("") == []


def test_an_added_line_beginning_with_two_pluses_is_not_a_file_header() -> None:
    diff = """\
diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1,0 +2 @@
+++ still a line of content
"""
    assert parse_added_lines(diff) == [AddedLine(path="a.txt", line=2)]


def test_content_shaped_like_a_header_pair_does_not_take_over_the_path() -> None:
    # A deleted line whose content begins with `--` and an added line whose content begins with
    # `++` are a `---` and `+++` pair, which is what a real file header is. Reading this one as a
    # header would lose line 3 and record a phantom path for every later hunk in the file.
    diff = """\
diff --git a/f.txt b/f.txt
--- a/f.txt
+++ b/f.txt
@@ -1 +1 @@
--- alpha
+++ beta
@@ -3 +3 @@ keep
-second
+CHANGED
"""
    assert parse_added_lines(diff) == [
        AddedLine(path="f.txt", line=1),
        AddedLine(path="f.txt", line=3),
    ]


ADDED = {
    AddedLine(path="a.py", line=4),
    AddedLine(path="a.py", line=5),
    AddedLine(path="a.py", line=9),
    AddedLine(path="b.py", line=4),
}


def line(number: int, path: str = "a.py") -> LineAnchor:
    return LineAnchor(kind="line", path=path, line=number)


def span(start: int, end: int, path: str = "a.py") -> SpanAnchor:
    return SpanAnchor(kind="span", path=path, start_line=start, end_line=end)


def test_a_line_anchor_on_an_added_line_attaches() -> None:
    assert attachable(line(4), ADDED) == line(4)


def test_a_line_anchor_off_the_added_lines_is_demoted() -> None:
    assert attachable(line(6), ADDED) is None


def test_a_line_anchor_matches_on_the_path_as_well_as_the_line() -> None:
    # The right path with the wrong line and the right line with the wrong path both demote.
    assert attachable(line(1), ADDED) is None
    assert attachable(line(4, "c.py"), ADDED) is None


def test_a_span_anchored_at_both_ends_attaches() -> None:
    # The lines between are not checked: a span covering a function crosses unchanged lines.
    assert attachable(span(4, 9), ADDED) == span(4, 9)


def test_a_span_missing_either_endpoint_is_demoted() -> None:
    assert attachable(span(3, 9), ADDED) is None
    assert attachable(span(4, 10), ADDED) is None


def test_a_span_of_one_line_becomes_a_line_anchor() -> None:
    # GitHub takes `start_line` as strictly before `line`, so this would be rejected as a span.
    assert attachable(span(5, 5), ADDED) == line(5)


def test_a_backwards_span_is_demoted() -> None:
    assert attachable(span(9, 4), ADDED) is None


def test_a_whole_file_anchor_is_demoted_even_where_its_lines_are_added() -> None:
    # By construction rather than by failure: a batched review has nowhere to put one.
    assert attachable(FileAnchor(kind="file", path="a.py"), ADDED) is None


def test_a_pull_request_anchor_is_demoted() -> None:
    assert attachable(PullRequestAnchor(kind="pull_request"), ADDED) is None


def repository(workspace: Path) -> Path:
    """A committed repository holding one tracked file and ignoring `*.log`."""
    git(workspace, "init", "--quiet")
    git(workspace, "config", "user.email", "coral@example.com")
    git(workspace, "config", "user.name", "Coral")
    (workspace / "tracked.txt").write_text("committed\n")
    (workspace / ".gitignore").write_text("*.log\n")
    git(workspace, "add", ".")
    git(workspace, "commit", "--quiet", "-m", "first")
    return workspace


def test_reset_reverts_a_tracked_file_the_agent_edited(tmp_path: Path) -> None:
    workspace = repository(tmp_path)
    (workspace / "tracked.txt").write_text("the reviewer's edit\n")
    reset(workspace)
    assert (workspace / "tracked.txt").read_text() == "committed\n"


def test_reset_removes_a_scratch_file_the_agent_wrote(tmp_path: Path) -> None:
    workspace = repository(tmp_path)
    (workspace / "test_scratch.py").write_text("assert False\n")
    (workspace / "scratch").mkdir()
    (workspace / "scratch" / "notes.txt").write_text("thinking\n")
    reset(workspace)
    assert not (workspace / "test_scratch.py").exists()
    assert not (workspace / "scratch").exists()


def test_a_failed_git_command_raises_with_gits_own_diagnosis(tmp_path: Path) -> None:
    # The exception's message is what a failure comment posts, and `CalledProcessError`'s message
    # holds the exit status alone: a bad ref would reach the pull request saying nothing.
    workspace = repository(tmp_path)
    with pytest.raises(RuntimeError) as raised:
        merge_base(workspace, "HEAD", "nosuchref")
    assert "nosuchref" in str(raised.value)


def test_reset_leaves_ignored_files_alone(tmp_path: Path) -> None:
    # `-fd` rather than `-fdx`, so dependencies the reviewer installed to run a test are still
    # installed when the verifier runs one.
    workspace = repository(tmp_path)
    (workspace / "installed.log").write_text("a dependency's leavings\n")
    reset(workspace)
    assert (workspace / "installed.log").exists()
