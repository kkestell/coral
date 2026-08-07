"""Tests of `coral.deadline`.

No clock is faked. A `Deadline` carries the reading it started from, so an expired one is built
by putting that reading far enough in the past.
"""

import time

from coral.deadline import REVIEWER_BUDGET_SECONDS, STEP_BUDGET_SECONDS, Deadline, start


def test_a_fresh_deadline_has_not_expired() -> None:
    deadline = start()
    assert not deadline.expired()
    assert deadline.budget == STEP_BUDGET_SECONDS


def test_a_deadline_whose_budget_is_spent_has_expired() -> None:
    started = time.monotonic() - (STEP_BUDGET_SECONDS + 1)
    assert Deadline(started=started, budget=STEP_BUDGET_SECONDS).expired()


def test_elapsed_grows_with_the_gap_to_the_starting_reading() -> None:
    deadline = Deadline(started=time.monotonic() - 30, budget=STEP_BUDGET_SECONDS)
    assert 30 <= deadline.elapsed() < 31


def test_a_budget_can_be_asked_for() -> None:
    assert start(60).budget == 60


def test_the_reviewer_leaves_the_step_something_for_the_verifier() -> None:
    # The whole point of the split. A reviewer budget at or above the step's would let the first
    # run spend everything and leave the second nothing to run in.
    assert REVIEWER_BUDGET_SECONDS < STEP_BUDGET_SECONDS
