"""Tests of `coral.github.reactions`.

Which comments are owed a reaction, and what a refused reaction costs, are decisions Coral makes
on its own, and they are what these cover. Whether `viewerHasReacted` answers for the account the
job's token belongs to is a live check, and no test here holds an opinion about it.
"""

from typing import Any

from coral.command import Access
from coral.github.client import ApiError, GitHub
from coral.github.conversation import (
    Bound,
    Comment,
    Conversation,
    PastReview,
    Thread,
    ThreadComment,
)
from coral.github.marker import marker
from coral.github.reactions import Request, react, requests_in

COMMIT = "9f3a1c2b4d5e6f708192a3b4c5d6e7f809a1b2c3"

# Everybody in these conversations is `somebody`, so one entry answers for all of them.
WRITERS = {"somebody": "write"}


def access(permissions: dict[str, str]) -> Access:
    """An `Access` over a GitHub answering the permission endpoint from a table."""

    class Answering(GitHub):
        def get(self, path: str) -> Any:
            login = path.split("/")[-2]
            return {"permission": permissions[login] if login in permissions else "none"}

    return Access(github=Answering(token="not a real token"), owner="kkestell", repo="coral-test")


def comment(
    database_id: int,
    body: str = "/coral",
    author: str = "somebody",
    reacted: bool = False,
    mine: bool = False,
) -> Comment:
    return Comment(
        id=f"IC_{database_id}",
        database_id=database_id,
        author=author,
        association="MEMBER",
        body=body,
        written_at="2025-01-01T00:00:00Z",
        mine=mine,
        reacted=reacted,
    )


def thread_comment(database_id: int, body: str = "/coral", reacted: bool = False) -> ThreadComment:
    return ThreadComment(
        id=f"PRRC_{database_id}",
        database_id=database_id,
        author="somebody",
        association="MEMBER",
        body=body,
        written_at="2025-01-01T00:00:00Z",
        mine=False,
        reacted=reacted,
        outdated=False,
        original_line=12,
    )


def review(database_id: int, body: str = "/coral") -> PastReview:
    return PastReview(
        id=f"PRR_{database_id}",
        database_id=database_id,
        author="somebody",
        association="MEMBER",
        body=body,
        written_at="2025-01-01T00:00:00Z",
        mine=False,
        reacted=False,
        state="COMMENTED",
        commit=COMMIT,
    )


def conversation(
    comments: list[Comment] | None = None,
    reviews: list[PastReview] | None = None,
    thread_comments: list[ThreadComment] | None = None,
) -> Conversation:
    threads = (
        [
            Thread(
                id="PRRT_1",
                path="a.py",
                line=12,
                start_line=None,
                diff_side="RIGHT",
                subject_type="LINE",
                resolved=False,
                outdated=False,
                comments=thread_comments,
                total_comments=len(thread_comments),
            )
        ]
        if thread_comments
        else []
    )
    return Conversation(
        comments=comments or [],
        reviews=reviews or [],
        threads=threads,
        bound=Bound(read=0, unread=0, oldest_read=None),
        reviewed_commits=[],
    )


def test_each_kind_of_comment_reacts_through_its_own_namespace() -> None:
    waiting = conversation(comments=[comment(1)], thread_comments=[thread_comment(2)])
    found = requests_in(waiting, access(WRITERS))
    assert found == [Request(id=1, namespace="issues"), Request(id=2, namespace="pulls")]


def test_a_comment_already_carrying_the_reaction_is_owed_nothing() -> None:
    found = requests_in(
        conversation(
            comments=[comment(1, reacted=True), comment(2)],
            thread_comments=[thread_comment(3, reacted=True)],
        ),
        access(WRITERS),
    )
    assert found == [Request(id=2, namespace="issues")]


def test_a_review_whose_body_asks_is_skipped() -> None:
    # GitHub has no endpoint for reacting to a review, which is why asking that way does nothing.
    assert requests_in(conversation(reviews=[review(1)]), access(WRITERS)) == []


def test_a_comment_from_somebody_without_write_access_is_not_a_request() -> None:
    waiting = conversation(comments=[comment(1, author="stranger")])
    assert requests_in(waiting, access(WRITERS)) == []


def test_a_comment_that_does_not_ask_is_not_a_request() -> None:
    waiting = conversation(comments=[comment(1, body="Nice, `/coral` it is.")])
    assert requests_in(waiting, access(WRITERS)) == []


def test_corals_own_comment_is_not_a_request() -> None:
    body = f"{marker(COMMIT)}\n\n/coral"
    waiting = conversation(comments=[comment(1, body=body, mine=True)])
    assert requests_in(waiting, access(WRITERS)) == []


def test_a_conversation_nobody_asked_anything_in() -> None:
    assert requests_in(conversation(), access(WRITERS)) == []


def recording(refuses: dict[str, int], attempted: list[str]) -> GitHub:
    """A `GitHub` that records every path posted to and refuses the ones named, with a status."""

    class Recording(GitHub):
        def post(self, path: str, body: dict[str, Any]) -> Any:
            attempted.append(path)
            if path in refuses:
                raise ApiError("POST", path, refuses[path], "the comment is gone")
            return {}

    return Recording(token="not a real token")


def test_a_reaction_github_refuses_costs_neither_the_run_nor_the_requests_after_it() -> None:
    # A comment deleted between the fetch and the reaction answers 404 and a locked conversation
    # answers 403. Raising here would fail a run whose review had nothing wrong with it, and the
    # publishing job would then say on the pull request that Coral did not review the change.
    attempted: list[str] = []
    github = recording({"/repos/o/r/issues/comments/1/reactions": 404}, attempted)
    react(github, "o", "r", [Request(id=1, namespace="issues"), Request(id=2, namespace="pulls")])
    assert attempted == [
        "/repos/o/r/issues/comments/1/reactions",
        "/repos/o/r/pulls/comments/2/reactions",
    ]
