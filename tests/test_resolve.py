"""Tests of `coral.resolve`.

The gates read a pull request reduced to six fields, an event, and a conversation, and none of
them makes a call, so all of them are decided here. Wiring those three together and posting what
a decline owes the pull request is a live run.
"""

from pathlib import Path
from typing import Any

import pytest

from coral import runner
from coral.github.conversation import Bound, Comment, Conversation, Thread, ThreadComment
from coral.github.reactions import Request
from coral.resolve import (
    MAX_CHANGED_FILES,
    MAX_CHANGED_LINES,
    Subject,
    acknowledgments,
    declined,
    management_key,
    reported,
    subject_of,
)
from coral.runner import Event

HEAD = "9f3a1c2b4d5e6f708192a3b4c5d6e7f809a1b2c3"
OTHER_COMMIT = "1a2b3c4d5e6f708192a3b4c5d6e7f809a1b2c3d4"


def opened() -> Event:
    """A pull request that was opened, which is one of the two automatic paths."""
    return Event(name="pull_request", owner="kkestell", repo="coral-test", number=7, comment=None)


def asked(body: str = "/coral", association: str = "MEMBER", identifier: int = 42) -> Event:
    """Somebody asking, in a comment on the pull request as a whole."""
    return Event(
        name="issue_comment",
        owner="kkestell",
        repo="coral-test",
        number=7,
        comment=runner.Comment(
            id=identifier, namespace="issues", body=body, association=association
        ),
    )


def subject(
    state: str = "open",
    head_repo_id: int | None = 1,
    base_repo_id: int = 1,
    changed_files: int = 3,
    changed_lines: int = 40,
) -> Subject:
    return Subject(
        state=state,
        head_sha=HEAD,
        head_repo_id=head_repo_id,
        base_repo_id=base_repo_id,
        changed_files=changed_files,
        changed_lines=changed_lines,
    )


def asking(database_id: int) -> Comment:
    """A comment on the pull request as a whole, asking for a review."""
    return Comment(
        id=f"IC_{database_id}",
        database_id=database_id,
        author="somebody",
        association="MEMBER",
        body="/coral",
        written_at="2025-01-01T00:00:00Z",
        mine=False,
        reacted=False,
    )


def asking_on_the_diff(database_id: int) -> Thread:
    """A thread holding one comment on the diff, asking for a review."""
    return Thread(
        id=f"PRRT_{database_id}",
        path="a.py",
        line=12,
        start_line=None,
        diff_side="RIGHT",
        subject_type="LINE",
        resolved=False,
        outdated=False,
        comments=[
            ThreadComment(
                id=f"PRRC_{database_id}",
                database_id=database_id,
                author="somebody",
                association="MEMBER",
                body="/coral",
                written_at="2025-01-01T00:00:00Z",
                mine=False,
                reacted=False,
                outdated=False,
                original_line=12,
            )
        ],
        total_comments=1,
    )


def conversation(
    comments: list[Comment] | None = None,
    threads: list[Thread] | None = None,
    reviewed_commits: list[str] | None = None,
) -> Conversation:
    return Conversation(
        comments=comments or [],
        reviews=[],
        threads=threads or [],
        bound=Bound(read=0, unread=0, oldest_read=None),
        reviewed_commits=reviewed_commits or [],
    )


def reviewed(*commits: str) -> Conversation:
    return conversation(reviewed_commits=list(commits))


def pull_request_payload(head_repo: dict[str, Any] | None = None) -> dict[str, Any]:
    """The fields of a single-pull-request response that the reduction reads."""
    return {
        "state": "open",
        "head": {"sha": HEAD, "repo": {"id": 12} if head_repo is None else head_repo},
        "base": {"repo": {"id": 12}},
        "changed_files": 4,
        "additions": 90,
        "deletions": 10,
    }


def test_the_reduction_reads_the_six_fields_the_gates_decide_on() -> None:
    assert subject_of(pull_request_payload()) == Subject(
        state="open",
        head_sha=HEAD,
        head_repo_id=12,
        base_repo_id=12,
        changed_files=4,
        changed_lines=100,
    )


def test_a_pull_request_whose_head_repository_is_gone_reduces_rather_than_crashing() -> None:
    reduced = subject_of({**pull_request_payload(), "head": {"sha": HEAD, "repo": None}})
    assert reduced.head_repo_id is None


def test_a_pull_request_that_passes_every_gate() -> None:
    assert declined(opened(), subject(), reviewed()) is None
    assert declined(asked(), subject(), reviewed()) is None


def test_an_inert_command_stops_the_run() -> None:
    stop = declined(asked(body="Ask with `/coral`."), subject(), reviewed())
    assert stop is not None
    assert stop.reason == "the comment does not ask for a review"
    assert stop.comment is None


def test_a_request_from_somebody_without_write_access_stops_the_run() -> None:
    stop = declined(asked(association="CONTRIBUTOR"), subject(), reviewed())
    assert stop is not None
    assert stop.reason == "the comment does not ask for a review"


def test_an_automatic_run_never_stops_at_the_inert_gate() -> None:
    # There is no comment on either automatic path, so there is nothing to read.
    assert declined(opened(), subject(), reviewed()) is None


def test_a_closed_pull_request_stops_the_run() -> None:
    stop = declined(asked(), subject(state="closed"), reviewed())
    assert stop is not None
    assert stop.reason == "the pull request is closed"
    assert stop.comment is None


def test_a_head_in_a_fork_stops_the_run() -> None:
    stop = declined(asked(), subject(head_repo_id=2, base_repo_id=1), reviewed())
    assert stop is not None
    assert stop.reason == "the head branch lives in a fork"


def test_a_deleted_head_repository_is_a_fork() -> None:
    stop = declined(asked(), subject(head_repo_id=None), reviewed())
    assert stop is not None
    assert stop.reason == "the head branch lives in a fork"


def test_a_commit_already_reviewed_stops_an_automatic_run() -> None:
    stop = declined(opened(), subject(), reviewed(OTHER_COMMIT, HEAD))
    assert stop is not None
    assert stop.reason == f"Coral has already reviewed {HEAD}"
    assert stop.comment is None


def test_a_commit_already_reviewed_does_not_stop_somebody_who_asks() -> None:
    # Somebody who asks gets a review whether or not the code has moved.
    assert declined(asked(), subject(), reviewed(HEAD)) is None


def test_a_change_at_the_size_backstop_passes() -> None:
    at_the_line = subject(changed_files=MAX_CHANGED_FILES, changed_lines=MAX_CHANGED_LINES)
    assert declined(opened(), at_the_line, reviewed()) is None


def test_one_file_past_the_backstop_stops_the_run_and_says_so() -> None:
    stop = declined(opened(), subject(changed_files=MAX_CHANGED_FILES + 1), reviewed())
    assert stop is not None
    assert stop.reason == f"the change is {MAX_CHANGED_FILES + 1} files and 40 lines"
    # The only gate that leaves something on the pull request, because it is the only one where
    # somebody is left waiting with nothing to explain it.
    assert stop.comment is not None
    assert str(MAX_CHANGED_FILES + 1) in stop.comment


def test_one_line_past_the_backstop_stops_the_run() -> None:
    stop = declined(opened(), subject(changed_lines=MAX_CHANGED_LINES + 1), reviewed())
    assert stop is not None
    assert stop.reason == f"the change is 3 files and {MAX_CHANGED_LINES + 1} lines"
    assert stop.comment is not None


def test_one_enormous_file_is_reported_as_one_file() -> None:
    # A vendored dependency or a pile of generated output is what this gate is for, and it can
    # arrive as a single file.
    stop = declined(opened(), subject(changed_files=1, changed_lines=31_000), reviewed())
    assert stop is not None
    assert stop.reason == "the change is 1 file and 31000 lines"
    assert stop.comment is not None
    assert stop.comment.startswith("This change is 1 file and 31000 lines,")


def test_a_closed_pull_request_is_not_reported_as_being_too_large() -> None:
    # The order is what decides which reason a person is given when more than one applies.
    stop = declined(asked(), subject(state="closed", changed_files=10_000), reviewed())
    assert stop is not None
    assert stop.reason == "the pull request is closed"


def test_a_fork_is_not_reported_as_being_too_large() -> None:
    stop = declined(asked(), subject(head_repo_id=2, changed_files=10_000), reviewed())
    assert stop is not None
    assert stop.reason == "the head branch lives in a fork"


def test_the_triggering_comment_is_acknowledged_once_when_the_conversation_offered_it() -> None:
    waiting = conversation(comments=[asking(42)], threads=[asking_on_the_diff(9)])
    assert acknowledgments(asked(identifier=42), waiting) == [
        Request(id=42, namespace="issues"),
        Request(id=9, namespace="pulls"),
    ]


def test_the_triggering_comment_is_acknowledged_when_the_conversation_did_not_offer_it() -> None:
    # The conversation is bounded, so a request on a busy pull request can be one the fetch did
    # not reach back far enough to see.
    waiting = conversation(comments=[asking(9)])
    assert acknowledgments(asked(identifier=42), waiting) == [
        Request(id=42, namespace="issues"),
        Request(id=9, namespace="issues"),
    ]


def test_an_automatic_run_acknowledges_only_what_the_conversation_offers() -> None:
    waiting = conversation(comments=[asking(9)])
    assert acknowledgments(opened(), waiting) == [Request(id=9, namespace="issues")]


def test_an_inert_triggering_comment_is_acknowledged_by_nothing() -> None:
    assert acknowledgments(asked(body="Nothing to see."), conversation()) == []


def test_a_management_key_alone_is_the_key_to_mint_with() -> None:
    assert management_key("sk-or-v1-management", api_key_present=False) == "sk-or-v1-management"


def test_a_plain_key_alone_leaves_nothing_to_mint_with() -> None:
    # Pass-through mode. The review job reads that secret itself, so resolve is handed only the
    # fact that it exists.
    assert management_key("", api_key_present=True) is None


def test_neither_secret_names_both_and_says_to_pass_one() -> None:
    with pytest.raises(RuntimeError) as raised:
        management_key("", api_key_present=False)
    assert "openrouter_api_key" in str(raised.value)
    assert "openrouter_management_key" in str(raised.value)
    assert "neither" in str(raised.value)


def test_both_secrets_are_a_choice_coral_will_not_make() -> None:
    with pytest.raises(RuntimeError) as raised:
        management_key("sk-or-v1-management", api_key_present=True)
    assert "both of them" in str(raised.value)


def test_a_reported_failure_leaves_its_reason_for_the_publishing_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))

    def refused() -> str:
        raise RuntimeError("POST /api/v1/keys returned 401: User not found.")

    with pytest.raises(RuntimeError):
        reported(refused)
    assert runner.reason_path().read_text() == (
        "RuntimeError: POST /api/v1/keys returned 401: User not found."
    )


def test_work_that_succeeds_writes_no_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    assert reported(lambda: "minted") == "minted"
    assert not runner.reason_path().exists()
