"""Tests of `coral.openrouter`.

The request bodies, the reading of an answer, and the alias refusal are decided here. `mint` and
`model_facts` are each one request, and the live checks in `.agents/docs/testing.md` are what
exercise them against the real API.
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from coral.openrouter import (
    ModelFacts,
    facts_of,
    key_request,
    key_ttl_seconds,
    minted_key,
    model_facts,
)

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

# Three entries out of a real `GET /api/v1/models` answer of 400, 2026-08-07, each cut to the keys
# the reduction reads: the default model, a model whose output ceiling OpenRouter does not report,
# and an alias, which is in the listing like any other id.
LISTED: list[dict[str, Any]] = [
    {
        "id": "openai/gpt-5.6-luna",
        "context_length": 1_050_000,
        "top_provider": {"context_length": 1_050_000, "max_completion_tokens": 128_000},
        "supported_parameters": [
            "include_reasoning",
            "max_completion_tokens",
            "max_tokens",
            "reasoning",
            "reasoning_effort",
            "response_format",
            "seed",
            "structured_outputs",
            "tool_choice",
            "tools",
        ],
    },
    {
        "id": "meta/muse-spark-1.2",
        "context_length": 1_048_576,
        "top_provider": {"context_length": 1_048_576, "max_completion_tokens": None},
        "supported_parameters": [
            "max_tokens",
            "reasoning",
            "response_format",
            "temperature",
            "tools",
        ],
    },
    {
        "id": "~openai/gpt-mini-latest",
        "context_length": 400_000,
        "top_provider": {"context_length": 400_000, "max_completion_tokens": 128_000},
        "supported_parameters": ["max_tokens", "reasoning", "tools"],
    },
]


def test_the_request_carries_the_cap_the_expiry_and_the_name() -> None:
    # The expiry is the TTL past `now`, in the format the endpoint echoes back: ISO 8601 UTC,
    # milliseconds, `Z`.
    now = datetime(2026, 8, 7, 17, 54, 34, 500_000, tzinfo=UTC)
    assert key_request(RUN_URL, now, 3600, 2.00) == {
        "name": RUN_URL,
        "limit": 2.00,
        "expires_at": "2026-08-07T18:54:34.500Z",
    }


def test_the_key_is_capped_at_whatever_the_caller_named() -> None:
    # No constant of its own: the caller's `spend_cap_dollars` is the limit, and the endpoint takes
    # a fractional cent and echoes it back exactly.
    now = datetime(2026, 8, 7, 17, 54, 34, 500_000, tzinfo=UTC)
    assert key_request(RUN_URL, now, 3600, 0.0005)["limit"] == 0.0005


def test_the_expiry_moves_with_the_ttl_it_is_given() -> None:
    now = datetime(2026, 8, 7, 17, 54, 34, 500_000, tzinfo=UTC)
    assert key_request(RUN_URL, now, 60, 2.00)["expires_at"] == "2026-08-07T17:55:34.500Z"


def test_the_ttl_outlives_the_job_the_key_is_for() -> None:
    # The key has to still work when a review job that queued for a while finally runs.
    assert key_ttl_seconds(30) == 2 * 30 * 60


def test_the_key_comes_off_the_top_level_of_the_answer() -> None:
    assert minted_key(CREATED) == "sk-or-v1-not-a-real-key"


def test_an_answer_carrying_no_key_says_what_it_carried_instead() -> None:
    # The key is offered once. An answer without it is one nothing later in the run recovers from,
    # so it fails here rather than as a 401 in the review job half an hour later.
    with pytest.raises(RuntimeError) as raised:
        minted_key({"data": CREATED["data"]})
    assert "['data']" in str(raised.value)


def test_the_listing_gives_up_the_facts_the_profile_needs() -> None:
    assert facts_of(LISTED, "openai/gpt-5.6-luna") == ModelFacts(
        context_length=1_050_000,
        max_completion_tokens=128_000,
        parameters=frozenset(
            {
                "include_reasoning",
                "max_completion_tokens",
                "max_tokens",
                "reasoning",
                "reasoning_effort",
                "response_format",
                "seed",
                "structured_outputs",
                "tool_choice",
                "tools",
            }
        ),
    )


def test_a_model_whose_output_ceiling_is_unreported_carries_none() -> None:
    # 48 of the 400 models listed. Nothing downstream may guess a number for one.
    assert facts_of(LISTED, "meta/muse-spark-1.2").max_completion_tokens is None


def test_a_model_the_listing_does_not_carry_says_so_by_name() -> None:
    with pytest.raises(RuntimeError) as raised:
        facts_of(LISTED, "openai/gpt-5.6-nebula")
    assert "'openai/gpt-5.6-nebula'" in str(raised.value)


@pytest.mark.parametrize(
    "entry",
    [
        {**LISTED[0], "top_provider": None},
        {**LISTED[0], "top_provider": {"context_length": 1_050_000}},
        {**LISTED[0], "context_length": "large"},
        {**LISTED[0], "context_length": 0},
        # A `bool` is an `int` in Python, so an entry answering `True` would otherwise build a
        # profile with a context length of one.
        {**LISTED[0], "context_length": True},
        {**LISTED[0], "top_provider": {"max_completion_tokens": "many"}},
        {**LISTED[0], "top_provider": {"max_completion_tokens": 0}},
        {**LISTED[0], "supported_parameters": "tools"},
        {**LISTED[0], "supported_parameters": ["tools", 3]},
    ],
)
def test_a_selected_listing_entry_with_unreadable_facts_fails_clearly(
    entry: dict[str, Any],
) -> None:
    with pytest.raises(RuntimeError) as raised:
        facts_of([entry], "openai/gpt-5.6-luna")

    # Named so a broken listing is one comment on the pull request rather than a traceback.
    assert "openai/gpt-5.6-luna" in str(raised.value)
    assert "listing entry" in str(raised.value)


def test_an_unselected_malformed_listing_entry_is_not_validated() -> None:
    facts = facts_of(
        [{"id": "not-selected", "top_provider": "unreadable"}, LISTED[0]],
        "openai/gpt-5.6-luna",
    )
    assert facts.context_length == LISTED[0]["context_length"]


def test_an_alias_is_refused_before_anything_is_asked_of_it() -> None:
    # Not by its absence from the listing: aliases are in there, and the per-model route answers
    # 200 for them, so `model_facts` refuses one itself. This test makes no request, which is the
    # other half of what it checks.
    with pytest.raises(RuntimeError) as raised:
        model_facts("~openai/gpt-mini-latest")
    assert "Name the model exactly" in str(raised.value)
