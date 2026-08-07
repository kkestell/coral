"""Coral's own time budget for a review.

Arithmetic over one `time.monotonic()` reading, and nothing else. This module imports only the
standard library so the budget stays testable without a fake clock and without paying for the
agent framework's import: the middleware that turns a deadline into a hook lives in
`coral/agent.py`, next to the framework it hooks into.
"""

import time
from dataclasses import dataclass
from typing import Final

# Twenty minutes from the start of the review step, against the job's `timeout-minutes: 30`. The
# gap is headroom: the review step has to still be running when its deadline fires, because it is
# the step that posts the failure. Chosen rather than measured; item 9 on the roadmap settles it.
STEP_BUDGET_SECONDS: Final = 20 * 60

# The reviewer's slice of the step. The verifier runs under the step's own budget, so whatever the
# reviewer leaves is what the verifier gets, and this number is what guarantees there is any. A
# reviewer that would have used minute fourteen fails here instead — a review whose findings cannot
# be verified posts nothing anyway. Chosen rather than measured; item 9 settles it.
REVIEWER_BUDGET_SECONDS: Final = 13 * 60


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


def start(budget: float = STEP_BUDGET_SECONDS) -> Deadline:
    """Begin a budget, now. The default is the step's own, begun before any other work."""
    return Deadline(started=time.monotonic(), budget=budget)
