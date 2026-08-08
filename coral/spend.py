"""Coral's own spend cap for a run, and the running total measured against it.

Arithmetic over the cost each OpenRouter response reports, and nothing else. This module imports
only the standard library so the cap stays testable without the agent framework: the callback that
reads a cost off a response and the middleware that stops the run live in `coral/agent.py`, next to
the framework they hook into.
"""

import math
from dataclasses import dataclass


@dataclass
class Ledger:
    """The cap the run gets and what it has spent against it.

    The one mutable object Coral passes between modules, and deliberately. The reviewer and the
    verifier are two `invoke` calls with separate states, and one ledger crossing between them is
    what makes the cap cover the run rather than each run alone.
    """

    cap: float
    spent: float = 0.0
    # Responses OpenRouter reported no cost for. Counted rather than treated as free: a review
    # whose spending Coral cannot measure is one the cap does not hold, and in pass-through mode
    # no provider-side limit holds it either.
    unpriced: int = 0

    def add(self, cost: float) -> None:
        """Count what one response cost."""
        self.spent += cost

    def exceeded(self) -> bool:
        """Whether the cap is reached."""
        return self.spent >= self.cap


def cap_dollars(value: str) -> float:
    """The run's cap out of the `spend_cap_dollars` input, validated.

    The message carries the bound, because a caller who set the input wrong reads it on the pull
    request. No upper bound, unlike the time budget: GitHub's ceiling on a job is what bounds that
    one, and nothing outside Coral bounds a dollar figure. The only default is the input's own,
    declared in the reusable workflow.
    """
    problem = (
        "Coral's `spend_cap_dollars` input has to be a number of dollars above zero, and this run "
        f"passed {value!r}."
    )
    try:
        cap = float(value)
    except ValueError:
        raise RuntimeError(problem) from None
    if not math.isfinite(cap) or cap <= 0:
        raise RuntimeError(problem)
    return cap
