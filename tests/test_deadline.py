"""Tests of `coral.deadline`.

No clock is faked. A `Deadline` carries the reading it started from, so an expired one is built
by putting that reading far enough in the past.
"""

import time

from coral.deadline import REVIEW_BUDGET_SECONDS, Deadline, start


def test_a_fresh_deadline_has_not_expired() -> None:
    deadline = start()
    assert not deadline.expired()
    assert deadline.budget == REVIEW_BUDGET_SECONDS


def test_a_deadline_whose_budget_is_spent_has_expired() -> None:
    started = time.monotonic() - (REVIEW_BUDGET_SECONDS + 1)
    assert Deadline(started=started, budget=REVIEW_BUDGET_SECONDS).expired()


def test_elapsed_grows_with_the_gap_to_the_starting_reading() -> None:
    deadline = Deadline(started=time.monotonic() - 30, budget=REVIEW_BUDGET_SECONDS)
    assert 30 <= deadline.elapsed() < 31
