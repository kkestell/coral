"""Coral's own time budget for a review, and the job timeout derived from it.

Arithmetic over one `time.monotonic()` reading, and nothing else. This module imports only the
standard library so the budget stays testable without a fake clock and without paying for the
agent framework's import: the middleware that turns a deadline into a hook lives in
`coral/agent.py`, next to the framework it hooks into.
"""

import time
from dataclasses import dataclass
from typing import Final

# The gap between the review step's budget and the review job's own `timeout-minutes`. The step
# has to still be running when its deadline fires, because it is the step that writes the reason
# the failure comment carries.
HEADROOM_MINUTES: Final = 10

# What GitHub allows a hosted job. The budget plus the headroom is the job's timeout, so this is
# what bounds the budget.
JOB_CEILING_MINUTES: Final = 360

# The reviewer's slice of the step. The verifier runs under the step's own budget, so whatever the
# reviewer leaves is what the verifier gets, and this number is what guarantees there is any. A
# reviewer that would have used the whole step fails here instead — a review whose findings cannot
# be verified posts nothing anyway.
#
# Real reviews in `kkestell/coral-test`, including pull requests sized near the change-size
# backstop, finished in 21 to 60 seconds, so the split holds as chosen at every budget.
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


def budget_minutes(value: str) -> int:
    """The step's budget out of the `time_budget_minutes` input, validated.

    Both messages carry the bound, because a caller who set the input wrong reads them on the pull
    request. The only default is the input's own, declared in the reusable workflow.
    """
    ceiling = JOB_CEILING_MINUTES - HEADROOM_MINUTES
    try:
        minutes = int(value)
    except ValueError:
        raise RuntimeError(
            f"Coral's `time_budget_minutes` input has to be a whole number of minutes between 1 "
            f"and {ceiling}, and this run passed {value!r}."
        ) from None
    if not 1 <= minutes <= ceiling:
        raise RuntimeError(
            f"Coral's `time_budget_minutes` input has to be between 1 and {ceiling} minutes, and "
            f"this run passed {minutes}. The upper bound is GitHub's {JOB_CEILING_MINUTES}-minute "
            f"ceiling on a job, less the {HEADROOM_MINUTES} minutes of headroom Coral holds past "
            f"the budget."
        )
    return minutes


def budget_seconds(value: str) -> float:
    """The step's budget out of the input, in the unit a `Deadline` carries."""
    return budget_minutes(value) * 60.0


def job_timeout_minutes(value: str) -> int:
    """The review job's `timeout-minutes` for this budget."""
    return budget_minutes(value) + HEADROOM_MINUTES


def reviewer_budget(step_budget: float) -> float:
    """The reviewer's slice of the step's budget."""
    return step_budget * REVIEWER_FRACTION
