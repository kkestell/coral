"""Tests of `coral.command`.

Every way a `/coral` can be inert gets a case of its own rather than a row in a table, so a
failure names the form that broke.
"""

from typing import Any

from coral.command import Access, asks_for_review, is_request
from coral.github.client import ApiError, GitHub
from coral.github.marker import marker

COMMIT = "9f3a1c2b4d5e6f708192a3b4c5d6e7f809a1b2c3"


def access(permissions: dict[str, str], refuses: bool = False) -> Access:
    """An `Access` over a GitHub answering the permission endpoint from a table.

    The shape is a real answer's, trimmed: `GET /repos/kkestell/coral-test/collaborators/kkestell/
    permission` on 2026-08-07 answered `{"permission": "admin", "user": {...}, "role_name":
    "admin"}`. A login the table does not name is a stranger, which the endpoint reports as `none`
    rather than refusing.
    """

    class Answering(GitHub):
        def get(self, path: str) -> Any:
            if refuses:
                raise ApiError("GET", path, 403, "Resource not accessible by integration")
            login = path.split("/")[-2]
            return {"permission": permissions[login] if login in permissions else "none"}

    return Access(github=Answering(token="not a real token"), owner="kkestell", repo="coral-test")


def maintainer() -> Access:
    return access({"kestell": "admin"})


def test_a_comment_that_is_only_the_command() -> None:
    assert asks_for_review("/coral") is True


def test_the_command_among_prose() -> None:
    body = "I rewrote the retry loop after the last round.\n\n/coral\n\nThanks for the patience."
    assert asks_for_review(body) is True


def test_trailing_whitespace_after_the_command() -> None:
    # Invisible in a rendered comment, and two trailing spaces are a Markdown hard line break.
    assert asks_for_review("/coral ") is True
    assert asks_for_review("/coral  \n") is True
    assert asks_for_review("/coral\t") is True


def test_several_command_lines_are_one_request() -> None:
    assert asks_for_review("/coral\n\n/coral\n") is True


def test_the_command_inside_a_sentence() -> None:
    assert asks_for_review("You can ask for another look with /coral when you are ready.") is False


def test_the_command_wrapped_in_backticks() -> None:
    assert asks_for_review("`/coral`") is False


def test_the_command_quoted_with_a_blockquote_marker() -> None:
    # What GitHub's quote-reply button produces, which is the form the requirements name.
    assert asks_for_review("> /coral\n\nI agree, let's do that.") is False


def test_the_command_as_a_list_item() -> None:
    assert asks_for_review("- /coral\n") is False


def test_the_command_indented() -> None:
    # One stray space and the four spaces of a Markdown code block are both something before the
    # command on that line.
    assert asks_for_review(" /coral") is False
    assert asks_for_review("    /coral") is False


def test_the_command_inside_a_code_fence() -> None:
    assert asks_for_review("```\n/coral\n```") is False


def test_the_command_inside_a_fence_carrying_an_info_string() -> None:
    assert asks_for_review("```text\n/coral\n```") is False


def test_the_command_inside_a_fence_indented_up_to_three_spaces() -> None:
    assert asks_for_review("   ```\n/coral\n   ```") is False


def test_the_command_inside_a_tilde_fence() -> None:
    assert asks_for_review("~~~\n/coral\n~~~") is False


def test_a_tilde_fence_is_not_closed_by_a_backtick_fence() -> None:
    assert asks_for_review("~~~\n```\n/coral\n```\n~~~") is False


def test_a_fence_is_not_closed_by_a_shorter_run_of_its_own_character() -> None:
    assert asks_for_review("````\n```\n/coral\n```\n````") is False


def test_a_fence_is_closed_by_a_longer_run_of_its_own_character() -> None:
    assert asks_for_review("```\n````\n/coral") is True


def test_a_fence_line_carrying_anything_after_it_does_not_close() -> None:
    assert asks_for_review("```\n``` still code\n/coral\n```") is False


def test_a_fence_left_unclosed_swallows_the_rest_of_the_comment() -> None:
    assert asks_for_review("Here is the output:\n\n```\nboom\n\n/coral") is False


def test_the_command_after_a_closed_fence() -> None:
    assert asks_for_review("```\nnot a request\n```\n\n/coral") is True


def test_the_command_in_the_wrong_case() -> None:
    # Both of these reach a runner, because the job-level condition's `contains` is not case
    # sensitive, and both stop here.
    assert asks_for_review("/Coral") is False
    assert asks_for_review("/CORAL") is False


def test_a_body_with_nothing_in_it() -> None:
    assert asks_for_review("") is False
    assert asks_for_review("   \n\n\t\n") is False


def test_prose_asking_for_something_specific_is_still_a_request() -> None:
    # Text alongside the command is conversation. It does not steer the review and does not stop
    # it being a request.
    assert asks_for_review("/coral\n\nPlease look hardest at the migration.") is True


def test_push_access_is_who_may_ask() -> None:
    for permission in ["admin", "maintain", "write"]:
        assert is_request("/coral", "kestell", access({"kestell": permission})) is True


def test_everybody_else_asks_for_nothing() -> None:
    # `read` is the case `author_association` cannot see: an organization member with read-only
    # access is a `MEMBER`, and a triage-only collaborator is a `COLLABORATOR`.
    assert is_request("/coral", "kestell", access({"kestell": "read"})) is False
    assert is_request("/coral", "kestell", access({"kestell": "triage"})) is False
    assert is_request("/coral", "stranger", access({})) is False


def test_a_comment_whose_author_is_gone_asks_for_nothing() -> None:
    assert is_request("/coral", None, access({})) is False


def test_a_permission_github_will_not_report_is_not_write_access() -> None:
    # Failing closed. A permission Coral could not read is not one it may act on.
    assert is_request("/coral", "kestell", access({"kestell": "admin"}, refuses=True)) is False


def test_one_login_costs_one_lookup_however_many_comments_it_wrote() -> None:
    permitting = access({"kestell": "admin"})
    assert is_request("/coral", "kestell", permitting) is True
    assert is_request("/coral", "kestell", permitting) is True
    assert permitting.known == {"kestell": True}


def test_a_comment_that_does_not_ask_costs_no_lookup() -> None:
    # The body decides first, so a conversation full of prose makes no call at all.
    permitting = access({"kestell": "admin"})
    assert is_request("Ask with `/coral`.", "kestell", permitting) is False
    assert permitting.known == {}


def test_a_comment_opening_with_corals_marker_is_never_a_request() -> None:
    # Free today, because an event created with the job's own token starts no run. Here for the
    # day Coral has an identity of its own.
    assert is_request(f"{marker(COMMIT)}\n\n/coral", "kestell", maintainer()) is False


def test_a_reply_quoting_corals_review_still_asks_for_one() -> None:
    # The quote-reply button copies the marker along with the prose, and the reply is the
    # reader's own comment however much of Coral's it carries.
    body = f"> {marker(COMMIT)}\n>\n> Coral reviewed this.\n\nHave another look.\n\n/coral"
    assert is_request(body, "kestell", maintainer()) is True


def test_a_comment_carrying_a_marker_naming_no_commit_is_never_a_request() -> None:
    # The self-exclusion the marker's optional commit could have broken: a failure comment posted
    # before anything pinned a commit is still Coral's own.
    assert is_request(f"{marker(None)}\n\n/coral", "kestell", maintainer()) is False
