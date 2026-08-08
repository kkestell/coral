"""Tests of `coral.github.client`.

Only the part that decides something. The transport is `httpx` and a test of it would be a test
of `httpx`; whether GitHub answers as the client assumes is what a live run finds out.
"""

from collections.abc import Iterator

import httpx
import pytest

from coral.github.client import MAX_RESPONSE_BYTES, body_of, data_of


class Chunked(httpx.SyncByteStream):
    """One answer arriving in pieces, which is how a real one reaches `body_of`."""

    CHUNK = 64 * 1024

    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __iter__(self) -> Iterator[bytes]:
        for at in range(0, len(self.payload), self.CHUNK):
            yield self.payload[at : at + self.CHUNK]


def streamed(payload: bytes) -> httpx.Response:
    return httpx.Response(200, stream=Chunked(payload))


def test_an_answer_under_the_ceiling_arrives_whole() -> None:
    assert body_of(streamed(b'{"state": "open"}'), "GET", "/repos/o/r/pulls/7") == (
        b'{"state": "open"}'
    )


def test_an_answer_past_the_ceiling_is_refused_rather_than_held() -> None:
    # A pull request somebody filled with enormous comments can answer with more than the runner
    # has memory for, and the refusal has to happen while the answer is still arriving.
    with pytest.raises(RuntimeError, match="more than Coral will read"):
        body_of(streamed(b"x" * (MAX_RESPONSE_BYTES + 1)), "POST", "/graphql")


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
