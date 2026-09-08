"""Coral's time budget for one CLI review.

Arithmetic over one `time.monotonic()` reading, and nothing else, including the check that fails a
run the budget should have stopped. This module imports only the standard library so the budget
stays testable without a fake clock and without paying for the agent framework's import: the
middleware that runs the check before each model call lives in `coral/agent.py`, next to the
framework it hooks into.
"""

import time
from dataclasses import dataclass
from typing import Final

MAX_BUDGET_MINUTES: Final = 350

# The reviewer's slice of the step. The verifier runs under the step's own budget, so whatever the
# reviewer leaves is what the verifier gets, and this number is what guarantees there is any. A
# reviewer that would have used the whole step fails here instead — a review whose findings cannot
# be verified posts nothing anyway.
#
# Observed reviews finished in 21 to 60 seconds, so the split holds as chosen at every budget.
REVIEWER_FRACTION: Final = 0.65


@dataclass(frozen=True)
class Deadline:
    """When the review began and how long it gets."""

    # A `time.monotonic()` reading, which is unaffected by the clock being set.
    started: float
    budget: float

    def elapsed(self) -> float:
        """How long the review has been running."""
        return time.monotonic() - self.started

    def expired(self) -> bool:
        """Whether the budget is spent."""
        return self.elapsed() >= self.budget


def start(budget: float) -> Deadline:
    """Begin a budget, now."""
    return Deadline(started=time.monotonic(), budget=budget)


def stop_if_expired(deadline: Deadline) -> None:
    """Fail the run when the budget is spent.

    Raised rather than ended gracefully so the CLI reports the real limit instead of a missing
    structured response.
    """
    if deadline.expired():
        raise RuntimeError(
            f"Coral ran out of time after {deadline.elapsed():.0f} seconds, against a budget of "
            f"{deadline.budget:.0f}."
        )


def budget_minutes(value: str) -> int:
    """Validate the settings file's whole-command time budget."""
    try:
        minutes = int(value)
    except ValueError:
        raise RuntimeError(
            f"Coral's `time_budget_minutes` input has to be a whole number of minutes between 1 "
            f"and {MAX_BUDGET_MINUTES}, and this run passed {value!r}."
        ) from None
    if not 1 <= minutes <= MAX_BUDGET_MINUTES:
        raise RuntimeError(
            "Coral's `time_budget_minutes` input has to be between 1 and "
            f"{MAX_BUDGET_MINUTES} minutes, and this run passed {minutes}."
        )
    return minutes


def budget_seconds(value: str) -> float:
    """The step's budget out of the input, in the unit a `Deadline` carries."""
    return budget_minutes(value) * 60.0


def reviewer_budget(step_budget: float) -> float:
    """The reviewer's slice of the step's budget."""
    return step_budget * REVIEWER_FRACTION
