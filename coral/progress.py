"""The live table Coral draws on stderr while a review runs.

The table is redrawn in place by moving the cursor back to its first line, never on the alternate
screen: whatever was on the terminal before the run stays there, and the last table Coral paints
is left in the scrollback. A log record is printed above the table, which is repainted under it.
"""

import logging
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, TextIO

CSI: Final = "\x1b["
COLUMN_GAP: Final = 2
# The clock in the footer advances on its own, so the table is repainted on a timer as well as on
# an agent's turn.
REPAINT_SECONDS: Final = 1.0


def short_name(model: str) -> str:
    """One agent's model without the OpenRouter vendor prefix."""
    return model.rpartition("/")[2] or model


def home_relative(path: Path) -> str:
    """The reviewed directory as the user would write it."""
    try:
        return f"~/{path.relative_to(Path.home())}"
    except ValueError:
        return str(path)


def money(dollars: float) -> str:
    """One cost cell."""
    return f"${dollars:.2f}"


def clock(seconds: float) -> str:
    """Elapsed time as hours, minutes, and seconds."""
    whole = int(seconds)
    return f"{whole // 3600:02d}:{whole // 60 % 60:02d}:{whole % 60:02d}"


@dataclass
class Row:
    """One agent's line in the table, which its own run updates as it goes."""

    table: "Table"
    label: str
    turns: int = 0
    cost: float = 0.0

    def responded(self, cost: float) -> None:
        """Count one model response and what it cost."""
        with self.table.lock:
            self.turns += 1
            self.cost += cost
        self.table.repaint()


@dataclass
class Table:
    """Every agent's progress, painted over the previous copy of itself."""

    workspace: Path
    stream: TextIO
    rows: list[Row] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    started: float = field(default_factory=time.monotonic)
    # How many lines the last paint left above the cursor, which is how far back up to go.
    drawn: int = 0

    @property
    def live(self) -> bool:
        """Whether the stream is a terminal whose cursor Coral can move."""
        return self.stream.isatty()

    def agent(self, model: str) -> Row:
        """Add a row for an agent that is starting."""
        with self.lock:
            row = Row(table=self, label=short_name(model))
            self.rows.append(row)
        self.repaint()
        return row

    def lines(self) -> list[str]:
        """The whole table as the lines to paint."""
        labels = ["Model", *(row.label for row in self.rows)]
        turns = ["Turns", *(str(row.turns) for row in self.rows)]
        costs = ["Cost", *(money(row.cost) for row in self.rows)]
        total = money(sum(row.cost for row in self.rows))
        label_width = max(len(cell) for cell in labels) + COLUMN_GAP
        turn_width = max(len(cell) for cell in turns) + COLUMN_GAP
        rule = "-" * (label_width + turn_width + max(len(cell) for cell in [*costs, total]))
        cells = [
            f"{label:<{label_width}}{turn:<{turn_width}}{cost}"
            for label, turn, cost in zip(labels, turns, costs, strict=True)
        ]
        elapsed = f"Elapsed {clock(time.monotonic() - self.started)}"
        return [
            f"Reviewing {home_relative(self.workspace)}...",
            "",
            cells[0],
            rule,
            *cells[1:],
            rule,
            f"{elapsed:<{label_width + turn_width}}{total}",
        ]

    def repaint(self) -> None:
        """Draw the table over the copy the last paint left."""
        with self.lock:
            self._paint()

    def _paint(self) -> None:
        """Draw the table. The lock is held."""
        if not self.live:
            return
        block = self.lines()
        moved = f"{CSI}{self.drawn}A" if self.drawn else ""
        # `2K` clears each line the cursor lands on, so a cell that shrank leaves nothing behind.
        painted = "".join(f"\r{CSI}2K{line}\n" for line in block)
        self.drawn = len(block)
        self.stream.write(moved + painted)
        self.stream.flush()

    def write(self, line: str) -> None:
        """Print one line above the table, which moves down to stay below it."""
        with self.lock:
            if self.live and self.drawn:
                # `J` clears from the table's first line to the end of the screen, so the line
                # printed in its place cannot be read against the table it replaced.
                self.stream.write(f"{CSI}{self.drawn}A\r{CSI}J")
                self.drawn = 0
            self.stream.write(line + "\n")
            self._paint()
            self.stream.flush()

    def close(self) -> None:
        """Leave the final table in the scrollback with the cursor below it."""
        with self.lock:
            if self.live:
                self._paint()
            else:
                self.stream.write("\n".join(self.lines()) + "\n")
                self.stream.flush()


class TableHandler(logging.Handler):
    """Sends Coral's log records through the table so they print above it."""

    def __init__(self, table: Table) -> None:
        super().__init__()
        self.table = table

    def emit(self, record: logging.LogRecord) -> None:
        self.table.write(self.format(record))


def _tick(table: Table, stop: threading.Event) -> None:
    """Repaint the footer's clock until the review ends."""
    while not stop.wait(REPAINT_SECONDS):
        table.repaint()


@contextmanager
def live_table(workspace: Path, stream: TextIO = sys.stderr) -> Iterator[Table]:
    """Paint a table for one review, with Coral's log records printed above it."""
    table = Table(workspace=workspace, stream=stream)
    handler = TableHandler(table)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    installed = root.handlers
    root.handlers = [handler]
    stop = threading.Event()
    clockwork = threading.Thread(target=_tick, args=(table, stop), daemon=True)
    clockwork.start()
    try:
        yield table
    finally:
        stop.set()
        clockwork.join()
        table.close()
        root.handlers = installed
