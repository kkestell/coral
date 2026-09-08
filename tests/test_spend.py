"""Tests of `coral.spend`.

The validation, the accumulation, and the check that stops a run are the whole of what this module
decides. What a response actually costs is OpenRouter's, and reading it off one is
`coral/agent.py`'s.
"""

import math

import pytest

from coral.spend import Ledger, cap_dollars, priced, stop_if_over_cap

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


def test_an_ordinary_reported_cost_is_the_amount_to_add() -> None:
    assert priced(2.015e-05) == 2.015e-05
    assert priced("0.5") == 0.5
    assert priced(0) == 0.0


def test_a_cost_that_is_not_a_number_is_not_priced() -> None:
    assert priced(None) is None
    assert priced("free") is None
    assert priced({"amount": 1}) is None


def test_a_cost_of_nan_is_not_priced() -> None:
    # `float` takes the word, and a ledger holding NaN never reaches its cap however much follows.
    assert priced("nan") is None
    assert priced(math.nan) is None


def test_an_infinite_cost_is_not_priced() -> None:
    assert priced(math.inf) is None
    assert priced(-math.inf) is None


def test_a_negative_cost_is_not_priced() -> None:
    # It would pay for later spending, which is a cap the run can talk its way back under.
    assert priced(-0.5) is None


def test_a_ledger_under_its_cap_passes_the_check() -> None:
    stop_if_over_cap(Ledger(cap=1.0, spent=0.5))


def test_the_check_stops_a_ledger_at_its_cap_and_says_what_it_spent() -> None:
    # Both numbers to six decimal places, because a cap of a fraction of a cent has to be legible
    # in the comment this message becomes.
    with pytest.raises(RuntimeError) as raised:
        stop_if_over_cap(Ledger(cap=0.0005, spent=0.000512))
    assert "$0.000512" in str(raised.value)
    assert "$0.000500" in str(raised.value)


def test_the_check_stops_a_run_coral_cannot_price_however_little_it_counted() -> None:
    with pytest.raises(RuntimeError, match="carried no cost"):
        stop_if_over_cap(Ledger(cap=1.0, spent=0.0, unpriced=1))
