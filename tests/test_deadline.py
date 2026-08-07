"""Tests of `coral.deadline`.

No clock is faked. A `Deadline` carries the reading it started from, so an expired one is built
by putting that reading far enough in the past.
"""

import time

import pytest

from coral.deadline import (
    HEADROOM_MINUTES,
    JOB_CEILING_MINUTES,
    Deadline,
    budget_seconds,
    job_timeout_minutes,
    reviewer_budget,
    start,
)

# The `time_budget_minutes` input's default, declared in `.github/workflows/coral.yml`. Every
# assertion below about an unconfigured install is against this value.
DEFAULT = "20"


def test_a_fresh_deadline_has_not_expired() -> None:
    assert not start(budget_seconds(DEFAULT)).expired()


def test_a_deadline_whose_budget_is_spent_has_expired() -> None:
    budget = budget_seconds(DEFAULT)
    assert Deadline(started=time.monotonic() - (budget + 1), budget=budget).expired()


def test_elapsed_grows_with_the_gap_to_the_starting_reading() -> None:
    deadline = Deadline(started=time.monotonic() - 30, budget=budget_seconds(DEFAULT))
    assert 30 <= deadline.elapsed() < 31


def test_the_budget_is_the_input_in_seconds() -> None:
    assert budget_seconds(DEFAULT) == 20 * 60


def test_the_job_timeout_is_the_budget_plus_the_headroom() -> None:
    assert job_timeout_minutes(DEFAULT) == 20 + HEADROOM_MINUTES


def test_the_reviewer_leaves_the_step_something_for_the_verifier() -> None:
    # The whole point of the split. A reviewer budget at or above the step's would let the first
    # run spend everything and leave the second nothing to run in.
    budget = budget_seconds(DEFAULT)
    assert reviewer_budget(budget) < budget


def test_the_reviewers_slice_of_the_default_budget_is_thirteen_minutes() -> None:
    # The number the fraction replaced, so an install naming no budget still splits the step the
    # way every measurement behind it was taken.
    assert reviewer_budget(budget_seconds(DEFAULT)) == 13 * 60


def test_a_budget_that_is_not_a_whole_number_of_minutes_says_what_it_takes() -> None:
    with pytest.raises(RuntimeError) as raised:
        budget_seconds("twenty")
    assert "between 1 and 350" in str(raised.value)


def test_a_fractional_budget_is_refused() -> None:
    with pytest.raises(RuntimeError, match="between 1 and 350"):
        budget_seconds("20.5")


def test_a_budget_of_nothing_is_refused() -> None:
    with pytest.raises(RuntimeError, match="between 1 and 350"):
        budget_seconds("0")


def test_the_smallest_budget_passes() -> None:
    assert budget_seconds("1") == 60


def test_the_largest_budget_is_the_one_whose_job_reaches_githubs_ceiling() -> None:
    largest = JOB_CEILING_MINUTES - HEADROOM_MINUTES
    assert job_timeout_minutes(str(largest)) == JOB_CEILING_MINUTES


def test_a_budget_whose_job_would_pass_githubs_ceiling_carries_the_bound() -> None:
    over = JOB_CEILING_MINUTES - HEADROOM_MINUTES + 1
    with pytest.raises(RuntimeError) as raised:
        job_timeout_minutes(str(over))
    assert "between 1 and 350" in str(raised.value)
    assert "360-minute" in str(raised.value)
