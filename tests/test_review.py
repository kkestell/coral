"""Tests of `coral.review`.

The rendering is the whole of what this module decides on its own; `review()`'s wiring has no
unit test, same as `resolve()`'s. The conversation the renderer is given is built through the real
parsers out of node dictionaries shaped like GitHub's, so a change to what a comment holds reaches
these tests rather than passing them.
"""

from typing import Any

from coral.github.conversation import (
    Bound,
    Conversation,
    parse_comments,
    parse_reviews,
    parse_threads,
)
from coral.github.marker import marker
from coral.review import render_conversation, render_request, render_verification_request
from coral.schema import (
    Finding,
    LineAnchor,
    PullRequestAnchor,
    RegressionTest,
    Review,
    SpanAnchor,
)

COMMIT = "a" * 40


def groups() -> list[dict[str, Any]]:
    return [{"content": "EYES", "viewerHasReacted": False}]


def comment_node(
    body: str = "Something worth saying.",
    author: str | None = "somebody",
    association: str = "CONTRIBUTOR",
) -> dict[str, Any]:
    return {
        "id": f"C_{author}_{len(body)}",
        "databaseId": 1,
        "author": {"login": author} if author else None,
        "authorAssociation": association,
        "body": body,
        "createdAt": "2025-01-01T00:00:00Z",
        "reactionGroups": groups(),
    }


def review_node(body: str, author: str = "reviewer", state: str = "APPROVED") -> dict[str, Any]:
    return {
        "id": f"R_{author}",
        "databaseId": 2,
        "author": {"login": author},
        "authorAssociation": "MEMBER",
        "state": state,
        "submittedAt": "2025-01-01T00:01:00Z",
        "body": body,
        "commit": {"oid": COMMIT},
        "viewerDidAuthor": False,
        "reactionGroups": groups(),
    }


def thread_node(
    resolved: bool = False,
    outdated: bool = False,
    line: int | None = 12,
    start_line: int | None = None,
    total: int = 1,
) -> dict[str, Any]:
    return {
        "id": "T_1",
        "isResolved": resolved,
        "isOutdated": outdated,
        "path": "coral/agent.py",
        "line": line,
        "startLine": start_line,
        "diffSide": "RIGHT",
        "subjectType": "LINE",
        "comments": {
            "totalCount": total,
            "nodes": [dict(comment_node("Inline prose."), outdated=False, originalLine=12)],
        },
    }


def conversation_of(
    comments: list[dict[str, Any]] | None = None,
    reviews: list[dict[str, Any]] | None = None,
    threads: list[dict[str, Any]] | None = None,
    unread: int = 0,
    reviewed: list[str] | None = None,
) -> Conversation:
    comments, reviews, threads = comments or [], reviews or [], threads or []
    parsed = parse_comments(comments)
    return Conversation(
        comments=parsed,
        reviews=parse_reviews(reviews),
        threads=parse_threads(threads),
        bound=Bound(read=len(parsed) + len(reviews), unread=unread, oldest_read=None),
        reviewed_commits=reviewed or [],
    )


def test_a_comment_carries_its_author_and_association() -> None:
    rendered = render_conversation(conversation_of(comments=[comment_node(author="alice")]))
    assert "alice (CONTRIBUTOR) wrote at 2025-01-01T00:00:00Z" in rendered
    assert "Something worth saying." in rendered


def test_a_comment_whose_author_is_gone_is_named_as_such() -> None:
    rendered = render_conversation(conversation_of(comments=[comment_node(author=None)]))
    assert "a deleted account (CONTRIBUTOR)" in rendered


def test_corals_own_comment_is_attributed_to_coral() -> None:
    # By the marker rather than the author login, which belongs to the repository's automation and
    # is shared with everything else that account posts.
    own = comment_node(body=f"{marker(COMMIT)}\n\nA finding Coral already made.")
    rendered = render_conversation(conversation_of(comments=[own]))
    assert "Coral wrote at" in rendered
    assert "somebody" not in rendered


def test_a_review_carries_its_state_and_the_commit_it_was_about() -> None:
    rendered = render_conversation(conversation_of(reviews=[review_node("Looks fine.")]))
    assert "reviewer (MEMBER) wrote at 2025-01-01T00:01:00Z" in rendered
    assert f"state was APPROVED, on commit {COMMIT}" in rendered
    assert "Looks fine." in rendered


def test_a_thread_carries_its_path_line_and_both_flags() -> None:
    rendered = render_conversation(
        conversation_of(threads=[thread_node(resolved=True, outdated=True)])
    )
    assert "`coral/agent.py`, line 12" in rendered
    assert "resolved and outdated" in rendered
    assert "Inline prose." in rendered


def test_an_unresolved_current_thread_says_so() -> None:
    rendered = render_conversation(conversation_of(threads=[thread_node()]))
    assert "unresolved and current" in rendered


def test_a_thread_against_a_line_that_is_gone_says_so() -> None:
    rendered = render_conversation(conversation_of(threads=[thread_node(line=None)]))
    assert "a line that is gone" in rendered


def test_a_thread_over_a_span_names_both_ends() -> None:
    rendered = render_conversation(conversation_of(threads=[thread_node(start_line=8)]))
    assert "lines 8 to 12" in rendered


def test_a_thread_read_only_partway_says_how_many_it_left() -> None:
    rendered = render_conversation(conversation_of(threads=[thread_node(total=5)]))
    assert "It holds 5 comments, of which the bound left 4 unread." in rendered


def test_a_thread_read_whole_makes_no_claim_about_unread_comments() -> None:
    rendered = render_conversation(conversation_of(threads=[thread_node(total=1)]))
    assert "It holds 1 comment." in rendered
    assert "unread" not in rendered.split("## Review threads")[1]


def test_the_bound_reports_what_it_left_unread() -> None:
    rendered = render_conversation(conversation_of(comments=[comment_node()], unread=7))
    assert "read 1 comment on this pull request and left 7 comments unread" in rendered


def test_the_already_reviewed_commits_are_named() -> None:
    rendered = render_conversation(conversation_of(reviewed=[COMMIT]))
    assert f"already reviewed these commits: `{COMMIT}`" in rendered


def test_a_pull_request_coral_has_not_reviewed_says_so() -> None:
    assert "has not reviewed this pull request before" in render_conversation(conversation_of())


def test_an_empty_conversation_says_so_in_each_section() -> None:
    # A fetch that worked and a fetch that returned nothing have to read differently.
    rendered = render_conversation(conversation_of())
    assert rendered.count("None.") == 3


def test_the_request_carries_the_title_the_body_and_the_diff_whole() -> None:
    diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-one\n+two\n"
    rendered = render_request("Fix the parser", "It was wrong.", diff, conversation_of())
    assert "# Fix the parser" in rendered
    assert "It was wrong." in rendered
    assert diff in rendered


def test_a_pull_request_with_no_description_says_so() -> None:
    assert "The author left no description." in render_request(
        "A title", None, "", conversation_of()
    )
    assert "The author left no description." in render_request(
        "A title", "  ", "", conversation_of()
    )


DIFF = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-one\n+two\n"

REGRESSION = RegressionTest(
    path="tests/test_parser.py",
    content="def test_it() -> None:\n    assert parse('') == []\n",
    command="pytest tests/test_parser.py::test_it",
)


def review_of(*findings: Finding) -> Review:
    return Review(summary="A summary.", findings=list(findings), everything_already_said=False)


def test_the_findings_are_numbered_from_zero_in_order() -> None:
    # The numbers are the indices a verdict names, so they are the filter's contract as much as
    # the prompt's.
    review = review_of(
        Finding(
            body="First.",
            anchor=LineAnchor(kind="line", path="a.py", line=7),
            severity="high",
            regression_test=None,
        ),
        Finding(
            body="Second.",
            anchor=PullRequestAnchor(kind="pull_request"),
            severity="low",
            regression_test=None,
        ),
    )
    rendered = render_verification_request("A title", None, DIFF, review)
    assert rendered.index("## Finding 0") < rendered.index("## Finding 1")
    assert rendered.index("First.") < rendered.index("Second.")
    assert "## Finding 2" not in rendered


def test_a_finding_carries_its_severity_and_where_it_points() -> None:
    review = review_of(
        Finding(
            body="A span of trouble.",
            anchor=SpanAnchor(kind="span", path="a.py", start_line=3, end_line=9),
            severity="medium",
            regression_test=None,
        )
    )
    rendered = render_verification_request("A title", None, DIFF, review)
    assert "Severity: medium. Concerns `a.py`, lines 3 to 9." in rendered


def test_a_reproduced_finding_carries_its_test_whole() -> None:
    review = review_of(
        Finding(
            body="The parser drops the last token.",
            anchor=LineAnchor(kind="line", path="a.py", line=7),
            severity="high",
            regression_test=REGRESSION,
        )
    )
    rendered = render_verification_request("A title", None, DIFF, review)
    assert REGRESSION.content in rendered
    assert "`tests/test_parser.py`" in rendered
    assert "`pytest tests/test_parser.py::test_it`" in rendered


def test_a_speculative_finding_says_so() -> None:
    review = review_of(
        Finding(
            body="Something might race.",
            anchor=PullRequestAnchor(kind="pull_request"),
            severity="low",
            regression_test=None,
        )
    )
    rendered = render_verification_request("A title", None, DIFF, review)
    assert "could not reproduce this with a test; it is speculative" in rendered


def test_the_verifier_never_sees_the_conversation() -> None:
    # Deliberate: a finding a comment talked into existence faces somebody who never read it.
    review = review_of(
        Finding(
            body="A finding.",
            anchor=PullRequestAnchor(kind="pull_request"),
            severity="low",
            regression_test=None,
        )
    )
    rendered = render_verification_request("A title", "The description.", DIFF, review)
    assert "conversation" not in rendered.lower()
    assert "# A title" in rendered
    assert "The description." in rendered
    assert DIFF in rendered
