"""Tests of `coral.spend`.

The validation and the accumulation are the whole of what this module decides. What a response
actually costs is OpenRouter's, and reading it off one is `coral/agent.py`'s.
"""

import pytest

from coral.spend import Ledger, cap_dollars

# The `spend_cap_dollars` input's default, declared in `.github/workflows/coral.yml`.
DEFAULT = "2.00"


def test_the_cap_is_the_input_in_dollars() -> None:
    assert cap_dollars(DEFAULT) == 2.00


def test_a_cap_of_a_fraction_of_a_cent_passes() -> None:
    # The live checks' cap, and the reason the input is a string: a review that stops has to be
    # provokable without spending anything.
    assert cap_dollars("0.0005") == 0.0005


def test_a_cap_that_is_not_a_number_says_what_it_takes() -> None:
    with pytest.raises(RuntimeError) as raised:
        cap_dollars("two dollars")
    assert "above zero" in str(raised.value)
    assert "'two dollars'" in str(raised.value)


def test_a_cap_of_nothing_is_refused() -> None:
    with pytest.raises(RuntimeError, match="above zero"):
        cap_dollars("0")


def test_a_negative_cap_is_refused() -> None:
    with pytest.raises(RuntimeError, match="above zero"):
        cap_dollars("-1")


def test_an_infinite_cap_is_refused() -> None:
    # `float` takes these words, and a cap no spending reaches is a cap that is not one.
    with pytest.raises(RuntimeError, match="above zero"):
        cap_dollars("inf")


def test_a_cap_that_is_not_a_number_at_all_is_refused() -> None:
    with pytest.raises(RuntimeError, match="above zero"):
        cap_dollars("nan")


def test_a_fresh_ledger_has_not_reached_its_cap() -> None:
    assert not Ledger(cap=cap_dollars(DEFAULT)).exceeded()


def test_spending_accumulates_across_responses() -> None:
    ledger = Ledger(cap=1.0)
    ledger.add(0.25)
    ledger.add(0.25)
    assert ledger.spent == 0.5
    assert not ledger.exceeded()


def test_a_ledger_at_exactly_its_cap_is_exceeded() -> None:
    # The boundary the middleware stops at, matching `Deadline.expired`.
    ledger = Ledger(cap=0.5)
    ledger.add(0.5)
    assert ledger.exceeded()


def test_a_ledger_one_response_short_of_its_cap_is_not() -> None:
    ledger = Ledger(cap=0.5)
    ledger.add(0.4)
    assert not ledger.exceeded()


def test_a_response_with_no_cost_is_counted_apart_from_the_total() -> None:
    # A separate count rather than a guessed amount: what stops the run is that the cap cannot be
    # measured against, and `coral/agent.py` is where that is decided.
    ledger = Ledger(cap=1.0)
    ledger.unpriced += 1
    assert ledger.spent == 0.0
    assert not ledger.exceeded()
