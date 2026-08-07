"""Tests of `coral.openrouter`.

The request body and the reading of the answer are decided here. `mint` itself is one POST, and
the live checks in `.agents/docs/testing.md` are what exercise it against the real API.
"""

from datetime import UTC, datetime

import pytest

from coral.openrouter import KEY_LIMIT_DOLLARS, key_request, minted_key

RUN_URL = "https://github.com/kkestell/coral-test/actions/runs/17"

# Trimmed from a real `POST /api/v1/keys` answer, 2026-08-07. The key string is a placeholder; the
# real one is shaped `sk-or-v1-` and 64 hex characters.
CREATED = {
    "key": "sk-or-v1-not-a-real-key",
    "data": {
        "hash": "4f0d1c8a",
        "name": RUN_URL,
        "label": "sk-or-v1-...key",
        "limit": 2.0,
        "expires_at": "2026-08-07T18:57:34.000Z",
        "usage": 0,
        "disabled": False,
    },
}


def test_the_request_carries_the_cap_the_expiry_and_the_name() -> None:
    # The expiry is the TTL past `now`, in the format the endpoint echoes back: ISO 8601 UTC,
    # milliseconds, `Z`.
    now = datetime(2026, 8, 7, 17, 54, 34, 500_000, tzinfo=UTC)
    assert key_request(RUN_URL, now) == {
        "name": RUN_URL,
        "limit": KEY_LIMIT_DOLLARS,
        "expires_at": "2026-08-07T18:54:34.500Z",
    }


def test_the_key_comes_off_the_top_level_of_the_answer() -> None:
    assert minted_key(CREATED) == "sk-or-v1-not-a-real-key"


def test_an_answer_carrying_no_key_says_what_it_carried_instead() -> None:
    # The key is offered once. An answer without it is one nothing later in the run recovers from,
    # so it fails here rather than as a 401 in the review job half an hour later.
    with pytest.raises(RuntimeError) as raised:
        minted_key({"data": CREATED["data"]})
    assert "['data']" in str(raised.value)
