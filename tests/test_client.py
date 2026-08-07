"""Tests of `coral.github.client`.

Only the part that decides something. The transport is `httpx` and a test of it would be a test
of `httpx`; whether GitHub answers as the client assumes is what a live run finds out.
"""

import pytest

from coral.github.client import data_of


def test_a_graphql_answer_hands_back_its_data() -> None:
    assert data_of({"data": {"viewer": {"login": "kkestell"}}}) == {"viewer": {"login": "kkestell"}}


def test_a_failed_graphql_query_raises_with_what_github_said() -> None:
    # GraphQL reports a failed query with HTTP 200, so the status check in the client sees a
    # success. Without this the failure arrives as a `KeyError` on `data` several frames later.
    answer = {
        "data": None,
        "errors": [
            {"message": "Field 'nope' doesn't exist on type 'PullRequest'"},
            {"message": "Variable $before is never used"},
        ],
    }
    with pytest.raises(RuntimeError) as raised:
        data_of(answer)
    assert str(raised.value) == (
        "GraphQL query failed: Field 'nope' doesn't exist on type 'PullRequest'; "
        "Variable $before is never used"
    )
