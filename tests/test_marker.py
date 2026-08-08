"""Tests of `coral.github.marker`, the whole of Coral's memory."""

from coral.github.marker import SENTINEL, marker, opens_with_marker, reviewed_commit

COMMIT = "9f3a1c2b4d5e6f708192a3b4c5d6e7f809a1b2c3"


def test_a_commit_round_trips_through_a_review_body() -> None:
    body = f"{marker(COMMIT)}\n\nCoral reviewed `{COMMIT}`.\n\nNothing to report."
    assert reviewed_commit(body) == COMMIT
    assert opens_with_marker(body) is True


def test_a_body_nobody_from_coral_wrote_has_no_commit_in_it() -> None:
    assert reviewed_commit("Looks good to me.") is None


def test_a_comment_naming_no_commit_is_the_sentinel_alone() -> None:
    # What a run that failed before anything pinned a commit posts.
    assert marker(None) == f"<!-- {SENTINEL} -->"
    body = f"{marker(None)}\n\nCoral did not review this change: the run failed."
    assert reviewed_commit(body) is None
    assert opens_with_marker(body) is True


def test_prose_that_merely_mentions_coral_does_not_open_with_the_marker() -> None:
    assert opens_with_marker("Coral reviewed this and said coral:reviewed, apparently.") is False


def test_a_reply_quoting_corals_review_does_not_open_with_the_marker() -> None:
    # What GitHub's quote-reply button writes: the marker comes along, behind the blockquote.
    body = f"> {marker(COMMIT)}\n>\n> Coral reviewed this.\n\nI disagree."
    assert opens_with_marker(body) is False
