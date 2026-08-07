"""Tests of `coral.github.conversation`.

The captured response below came off pull request 10513 in `cli/cli` on 2026-08-06, through the
query in the module under test, and was trimmed by hand to a few nodes of each kind. What it
proves is that the parsing reads the shape GitHub actually sends. Whether GitHub still sends it
is what a live run finds out, and nothing here asserts anything about GitHub's behavior.

Everything the real response does not contain — a deleted author, an unsubmitted review, bodies
long enough to make the character bound bind first — is built by the helpers underneath it.
"""

from pathlib import Path
from typing import Any

from coral.github.conversation import (
    MAX_CHARACTERS,
    MAX_COMMENTS,
    MAX_PAGES,
    Fetched,
    bound,
    parse_comments,
    parse_reviews,
    parse_threads,
    read_conversation,
    reviewed_commits,
    wants_another_page,
    write_conversation,
)
from coral.github.marker import marker

COMMIT = "9f3a1c2b4d5e6f708192a3b4c5d6e7f809a1b2c3"
OTHER_COMMIT = "1a2b3c4d5e6f708192a3b4c5d6e7f809a1b2c3d4"

CAPTURED: dict[str, Any] = {
    "repository": {
        "pullRequest": {
            "reviews": {
                "totalCount": 117,
                "pageInfo": {"hasPreviousPage": True, "startCursor": "Y3Vyc29yOnYyOpO0MjAyNS0w"},
                "nodes": [
                    {
                        "id": "PRR_kwDODKw3uc6e4Dil",
                        "author": {"login": "BagToad"},
                        "authorAssociation": "MEMBER",
                        "state": "COMMENTED",
                        "submittedAt": "2025-03-06T20:02:02Z",
                        "body": "",
                        "commit": {"oid": "dde7e24847970df859ca883ba316b4e09d039a71"},
                    },
                    {
                        "id": "PRR_kwDODKw3uc6fQFov",
                        "author": {"login": "jtmcg"},
                        "authorAssociation": "CONTRIBUTOR",
                        "state": "APPROVED",
                        "submittedAt": "2025-03-10T17:56:30Z",
                        "body": (
                            "Hell yeah, nice work on this! I've run all the acceptance tests "
                            "myself as well and have verified they are working as expected "
                            ":shipit: "
                        ),
                        "commit": {"oid": "f43e1cafdba856830f2592085bde14e6f32d9617"},
                    },
                ],
            },
            "reviewThreads": {
                "totalCount": 84,
                "pageInfo": {"hasPreviousPage": False, "startCursor": "Y3Vyc29yOnYyOpK0MjAyNS0w"},
                "nodes": [
                    {
                        "id": "PRRT_kwDODKw3uc5LYIME",
                        "isResolved": True,
                        "isOutdated": True,
                        "path": "pkg/cmd/pr/create/create.go",
                        "line": None,
                        "startLine": None,
                        "diffSide": "RIGHT",
                        "subjectType": "LINE",
                        "comments": {
                            "totalCount": 1,
                            "nodes": [
                                {
                                    "id": "PRRC_kwDODKw3uc51qgxu",
                                    "author": {"login": "copilot-pull-request-reviewer"},
                                    "authorAssociation": "CONTRIBUTOR",
                                    "body": (
                                        "Consider clarifying the error handling and updating or "
                                        "removing the TODO comment near the headRemote lookup."
                                    ),
                                    "createdAt": "2025-02-27T17:51:06Z",
                                    "outdated": True,
                                    "originalLine": 679,
                                }
                            ],
                        },
                    },
                    {
                        "id": "PRRT_kwDODKw3uc5LYbpe",
                        "isResolved": False,
                        "isOutdated": False,
                        "path": "acceptance/testdata/pr/pr-create-respects-branch-pushremote.txtar",
                        "line": 32,
                        "startLine": 21,
                        "diffSide": "RIGHT",
                        "subjectType": "LINE",
                        "comments": {
                            "totalCount": 2,
                            "nodes": [
                                {
                                    "id": "PRRC_kwDODKw3uc51q_aZ",
                                    "author": {"login": "jtmcg"},
                                    "authorAssociation": "CONTRIBUTOR",
                                    "body": (
                                        "My only concern with this is that both `gh repo fork` "
                                        "and `gh repo clone` set `gh-resolved` in the git config."
                                    ),
                                    "createdAt": "2025-02-27T19:20:15Z",
                                    "outdated": False,
                                    "originalLine": 32,
                                },
                                {
                                    "id": "PRRC_kwDODKw3uc51rzwt",
                                    "author": {"login": "BagToad"},
                                    "authorAssociation": "MEMBER",
                                    "body": "Let's delete this from the config in these tests.",
                                    "createdAt": "2025-02-27T22:21:43Z",
                                    "outdated": False,
                                    "originalLine": 32,
                                },
                            ],
                        },
                    },
                ],
            },
            "comments": {
                "totalCount": 6,
                "pageInfo": {"hasPreviousPage": False, "startCursor": "Y3Vyc29yOnYyOpHOoSw0Lw=="},
                "nodes": [
                    {
                        "id": "IC_kwDODKw3uc6hLDQv",
                        "author": {"login": "andyfeller"},
                        "authorAssociation": "CONTRIBUTOR",
                        "body": "On it! \U0001fae1 ",
                        "createdAt": "2025-03-06T14:35:12Z",
                    }
                ],
            },
        }
    },
    "rateLimit": {"cost": 1, "remaining": 4964, "nodeCount": 2300},
}


def connection(name: str) -> Any:
    return CAPTURED["repository"]["pullRequest"][name]


def at(second: int) -> str:
    """A timestamp that sorts where its number says it does."""
    return f"2025-01-01T{second // 3600:02d}:{second % 3600 // 60:02d}:{second % 60:02d}Z"


def comment_node(
    identifier: str,
    body: str = "Something worth saying.",
    written_at: str = "2025-01-01T00:00:00Z",
    author: str | None = "somebody",
    association: str = "NONE",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "author": {"login": author} if author else None,
        "authorAssociation": association,
        "body": body,
        "createdAt": written_at,
    }


def review_node(
    identifier: str,
    body: str = "A review with prose in it.",
    written_at: str | None = "2025-01-01T00:00:00Z",
    author: str | None = "somebody",
    association: str = "MEMBER",
    state: str = "COMMENTED",
    commit: str | None = COMMIT,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "author": {"login": author} if author else None,
        "authorAssociation": association,
        "state": state,
        "submittedAt": written_at,
        "body": body,
        "commit": {"oid": commit} if commit else None,
    }


def thread_node(
    identifier: str,
    comments: list[dict[str, Any]],
    total: int | None = None,
    resolved: bool = False,
    outdated: bool = False,
    line: int | None = 12,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "isResolved": resolved,
        "isOutdated": outdated,
        "path": "a.py",
        "line": line,
        "startLine": None,
        "diffSide": "RIGHT",
        "subjectType": "LINE",
        "comments": {
            "totalCount": total if total is not None else len(comments),
            "nodes": [dict(node, outdated=False, originalLine=12) for node in comments],
        },
    }


def fetched_from(
    comments: list[dict[str, Any]] | None = None,
    reviews: list[dict[str, Any]] | None = None,
    threads: list[dict[str, Any]] | None = None,
    unfetched: int = 0,
) -> Fetched:
    """A `Fetched` built through the real parsers, which is what a fetch would hand the bound."""
    comments, reviews, threads = comments or [], reviews or [], threads or []
    return Fetched(
        comments=parse_comments(comments),
        reviews=parse_reviews(reviews),
        threads=parse_threads(threads),
        reviewed_commits=reviewed_commits(reviews),
        unfetched=unfetched,
    )


def test_parsing_a_captured_response_keeps_the_author_association() -> None:
    comments = parse_comments(connection("comments")["nodes"])
    reviews = parse_reviews(connection("reviews")["nodes"])
    threads = parse_threads(connection("reviewThreads")["nodes"])
    assert [(c.author, c.association) for c in comments] == [("andyfeller", "CONTRIBUTOR")]
    assert [(r.author, r.association) for r in reviews] == [("jtmcg", "CONTRIBUTOR")]
    assert [(c.author, c.association) for c in threads[1].comments] == [
        ("jtmcg", "CONTRIBUTOR"),
        ("BagToad", "MEMBER"),
    ]


def test_parsing_a_captured_response_keeps_a_thread_whole() -> None:
    thread = parse_threads(connection("reviewThreads")["nodes"])[1]
    assert (thread.resolved, thread.outdated) == (False, False)
    assert (thread.path, thread.line, thread.start_line) == (
        "acceptance/testdata/pr/pr-create-respects-branch-pushremote.txtar",
        32,
        21,
    )
    assert (thread.diff_side, thread.subject_type) == ("RIGHT", "LINE")
    assert thread.total_comments == 2


def test_a_thread_against_a_deleted_line_has_no_line() -> None:
    # What an outdated thread looks like once the code under it is gone. 68 of the 84 threads on
    # the captured pull request were in this state.
    thread = parse_threads(connection("reviewThreads")["nodes"])[0]
    assert (thread.resolved, thread.outdated) == (True, True)
    assert thread.line is None
    assert thread.comments[0].outdated is True
    assert thread.comments[0].original_line == 679


def test_a_review_with_an_empty_body_is_not_a_comment() -> None:
    # GitHub makes one of these to hold a single inline comment, and the inline comment is read
    # through its thread instead.
    reviews = parse_reviews(connection("reviews")["nodes"])
    assert [review.id for review in reviews] == ["PRR_kwDODKw3uc6fQFov"]


def test_a_review_that_was_never_submitted_is_skipped() -> None:
    # Visible to nobody but its author, and it carries no timestamp to sort on.
    reviews = parse_reviews([review_node("PRR_1", written_at=None, state="PENDING")])
    assert reviews == []


def test_a_comment_whose_author_is_gone_still_parses() -> None:
    comment = parse_comments([comment_node("IC_1", author=None, association="CONTRIBUTOR")])[0]
    assert comment.author is None
    assert comment.association == "CONTRIBUTOR"


def test_a_comment_carrying_the_marker_is_corals() -> None:
    body = f"{marker(COMMIT)}\n\nThis reads a value that may not be set."
    mine, theirs = parse_comments([comment_node("IC_1", body=body), comment_node("IC_2")])
    assert mine.mine is True
    assert theirs.mine is False


def test_the_already_reviewed_set_comes_from_every_review_fetched() -> None:
    # Not from the bounded conversation: Coral's memory must not shrink when other people talk.
    # The last of these is a review whose body holds nothing but the marker, and the envelope
    # with the empty body is what GitHub wraps a lone inline comment in.
    conversation = bound(
        fetched_from(
            comments=[comment_node(f"IC_{n}", written_at=at(500 + n)) for n in range(MAX_COMMENTS)],
            reviews=[
                review_node("PRR_1", body=f"{marker(COMMIT)}\n\nOld.", written_at=at(1)),
                review_node("PRR_2", body="", written_at=at(2)),
                review_node("PRR_3", body=marker(OTHER_COMMIT), written_at=at(3)),
            ],
        )
    )
    assert conversation.reviews == []
    assert conversation.reviewed_commits == [COMMIT, OTHER_COMMIT]


def test_the_bound_takes_the_most_recent_across_all_three_connections() -> None:
    # Not 200 from each. The three connections are interleaved in time here so that a bound
    # applied per connection would keep a different set.
    fetched = fetched_from(
        comments=[comment_node(f"IC_{n}", written_at=at(3 * n)) for n in range(150)],
        reviews=[review_node(f"PRR_{n}", written_at=at(3 * n + 1)) for n in range(150)],
        threads=[
            thread_node(f"PRRT_{n}", [comment_node(f"PRRC_{n}", written_at=at(3 * n + 2))])
            for n in range(150)
        ],
    )
    conversation = bound(fetched)
    assert conversation.bound.read == MAX_COMMENTS
    assert conversation.bound.unread == 450 - MAX_COMMENTS
    # The newest 200 of the 450 reach back to the review at index 83, so each connection keeps
    # its own tail from wherever that moment falls in its own sequence.
    assert len(conversation.comments) == 66
    assert len(conversation.reviews) == 67
    assert len(conversation.threads) == 67
    assert conversation.bound.oldest_read == at(3 * 83 + 1)


def test_the_bound_keeps_each_list_oldest_first() -> None:
    conversation = bound(
        fetched_from(comments=[comment_node(f"IC_{n}", written_at=at(100 - n)) for n in range(10)])
    )
    assert [c.written_at for c in conversation.comments] == [at(91 + n) for n in range(10)]


def test_the_character_bound_binds_first_when_the_bodies_are_long() -> None:
    long_body = "x" * (MAX_CHARACTERS // 8)
    conversation = bound(
        fetched_from(
            comments=[comment_node(f"IC_{n}", body=long_body, written_at=at(n)) for n in range(12)]
        )
    )
    # Eight of them come to exactly the ceiling, and the ninth would pass it.
    assert conversation.bound.read == 8
    assert conversation.bound.unread == 4


def test_the_comment_bound_binds_first_when_the_bodies_are_short() -> None:
    conversation = bound(
        fetched_from(comments=[comment_node(f"IC_{n}", written_at=at(n)) for n in range(250)])
    )
    assert conversation.bound.read == MAX_COMMENTS
    assert conversation.bound.unread == 50


def test_a_thread_survives_when_one_of_its_comments_does_and_keeps_its_flags() -> None:
    surviving = thread_node(
        "PRRT_1",
        [comment_node("PRRC_1", written_at=at(0)), comment_node("PRRC_2", written_at=at(9999))],
        resolved=True,
        outdated=True,
    )
    doomed = thread_node("PRRT_2", [comment_node("PRRC_3", written_at=at(1))])
    filler = [comment_node(f"IC_{n}", written_at=at(500 + n)) for n in range(MAX_COMMENTS - 1)]

    conversation = bound(fetched_from(comments=filler, threads=[surviving, doomed]))

    assert [thread.id for thread in conversation.threads] == ["PRRT_1"]
    thread = conversation.threads[0]
    assert [comment.id for comment in thread.comments] == ["PRRC_2"]
    assert (thread.resolved, thread.outdated, thread.line) == (True, True, 12)
    # Its own count still says how many comments the thread really holds.
    assert thread.total_comments == 2
    assert conversation.bound.read == MAX_COMMENTS
    assert conversation.bound.unread == 2


def test_a_thread_holding_more_comments_than_were_fetched_reports_the_rest_unread() -> None:
    # The `first: 20` inside the thread, which is not the same truncation as the global bound.
    conversation = bound(
        fetched_from(threads=[thread_node("PRRT_1", [comment_node("PRRC_1")], total=25)])
    )
    assert conversation.bound.read == 1
    assert conversation.bound.unread == 24


def test_nodes_the_paging_never_asked_for_are_unread_too() -> None:
    conversation = bound(fetched_from(comments=[comment_node("IC_1")], unfetched=300))
    assert conversation.bound.read == 1
    assert conversation.bound.unread == 300


def test_two_comments_written_in_the_same_second_both_survive() -> None:
    conversation = bound(
        fetched_from(
            comments=[
                comment_node("IC_1", written_at=at(1)),
                comment_node("IC_2", written_at=at(1)),
            ]
        )
    )
    assert [comment.id for comment in conversation.comments] == ["IC_1", "IC_2"]
    assert conversation.bound.read == 2


def test_a_pull_request_nobody_has_said_anything_on() -> None:
    conversation = bound(fetched_from())
    assert (conversation.comments, conversation.reviews, conversation.threads) == ([], [], [])
    assert conversation.reviewed_commits == []
    assert conversation.bound.read == 0
    assert conversation.bound.unread == 0
    assert conversation.bound.oldest_read is None


def test_a_conversation_survives_the_step_boundary(tmp_path: Path) -> None:
    conversation = bound(
        fetched_from(
            comments=connection("comments")["nodes"],
            reviews=connection("reviews")["nodes"],
            threads=connection("reviewThreads")["nodes"],
        )
    )
    path = tmp_path / "conversation.json"
    write_conversation(path, conversation)
    assert read_conversation(path) == conversation


def test_a_connection_with_more_to_give_is_paged_again() -> None:
    assert wants_another_page(has_previous=True, comments_so_far=0, pages=1) is True


def test_a_connection_that_has_offered_the_whole_bound_is_left_alone() -> None:
    assert wants_another_page(has_previous=True, comments_so_far=MAX_COMMENTS, pages=1) is False


def test_a_connection_with_nothing_older_is_left_alone() -> None:
    assert wants_another_page(has_previous=False, comments_so_far=0, pages=1) is False


def test_paging_stops_at_the_page_cap() -> None:
    # What keeps a pull request carrying a thousand empty reviews from being walked end to end.
    assert wants_another_page(has_previous=True, comments_so_far=0, pages=MAX_PAGES) is False
