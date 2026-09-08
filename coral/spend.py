"""Coral's own spend cap for a run, and the running total measured against it.

Arithmetic over the cost each OpenRouter response reports, and nothing else, including the check
that fails a run the cap should have stopped. This module imports only the standard library so the
cap stays testable without the agent framework: the callback that reads a cost off a response and
the middleware that runs the check before each model call live in `coral/agent.py`, next to the
framework they hook into.
"""

import math
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Ledger:
    """The mutable spend state shared by the reviewer's and verifier's agent runs."""

    cap: float
    spent: float = 0.0
    # Responses OpenRouter reported no cost for. Counted rather than treated as free: a review
    # whose spending Coral cannot measure is one the cap does not hold, and in pass-through mode
    # no provider-side limit holds it either.
    unpriced: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def add(self, cost: float) -> None:
        """Count what one response cost."""
        with self._lock:
            self.spent += cost

    def add_unpriced(self) -> None:
        """Count one response whose cost could not be measured."""
        with self._lock:
            self.unpriced += 1

    def exceeded(self) -> bool:
        """Whether the cap is reached."""
        with self._lock:
            return self.spent >= self.cap

    def snapshot(self) -> tuple[float, int]:
        """Read the values a limit check reports together."""
        with self._lock:
            return self.spent, self.unpriced


def priced(value: Any) -> float | None:
    """What one response cost, or `None` when that is not an amount a cap can hold it to.

    The provider reports this figure and Coral checks it rather than trusting it. A NaN added to
    the ledger never reaches the cap however many responses follow it, and a negative one pays for
    later spending. Both are counted as unpriced instead, which is what stops the run.
    """
    try:
        cost = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(cost) or cost < 0:
        return None
    return cost


def stop_if_over_cap(ledger: Ledger) -> None:
    """Fail the run when the cap is reached or the spending cannot be measured.

    Six decimal places because a cap of a fraction of a cent has to be legible: the message is the
    whole of what the failure comment says the reason was.
    """
    # A cap Coral cannot measure against is not a cap, so this stops the run too. Only the minted
    # key's own limit would have caught the spending, and a passed-through key has none.
    spent, unpriced = ledger.snapshot()
    if unpriced:
        raise RuntimeError(
            f"{unpriced} of this run's responses carried no cost, so Coral cannot hold it "
            f"to its cap of ${ledger.cap:.6f}. It had counted ${ledger.spent:.6f} of that."
        )
    if spent >= ledger.cap:
        raise RuntimeError(
            f"Coral ran out of money after ${spent:.6f}, against a cap of ${ledger.cap:.6f}."
        )


def cap_dollars(value: str) -> float:
    """Validate the settings file's per-command spend cap."""
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
