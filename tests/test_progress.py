"""Tests of the live progress table."""

import io
import logging
from pathlib import Path

import pytest

from coral.progress import CSI, Table, home_relative, live_table, short_name


class Terminal(io.StringIO):
    """A stream Coral will move the cursor on."""

    def isatty(self) -> bool:
        return True


def table(stream: io.StringIO, *models: str) -> Table:
    board = Table(workspace=Path.home() / "src" / "coral", stream=stream)
    board.started -= 143.0
    for model in models:
        board.agent(model)
    return board


def test_the_table_names_every_agent_its_turns_and_its_costs() -> None:
    board = table(io.StringIO(), "z-ai/glm-5.3-flash", "deepseek/deepseek-v4-flash-0731")
    board.rows[0].responded(0.09)
    for _ in range(2):
        board.rows[1].responded(0.005)

    assert board.lines() == [
        "Reviewing ~/src/coral...",
        "",
        "Model                   Turns  Cost",
        "-" * 36,
        "glm-5.3-flash           1      $0.09",
        "deepseek-v4-flash-0731  2      $0.01",
        "-" * 36,
        "Elapsed 00:02:23               $0.10",
    ]


def test_a_repaint_returns_to_the_tables_first_line_rather_than_another_screen() -> None:
    stream = Terminal()
    board = table(stream, "z-ai/glm-5.3-flash")
    lines = len(board.lines())
    stream.truncate(0)
    stream.seek(0)

    board.repaint()

    painted = stream.getvalue()
    assert painted.startswith(f"{CSI}{lines}A")
    # Nothing here switches screens or hides what the terminal already held.
    assert "?1049" not in painted and painted.count("\n") == lines


def test_a_log_line_prints_above_the_table() -> None:
    stream = Terminal()
    board = table(stream, "z-ai/glm-5.3-flash")
    stream.truncate(0)
    stream.seek(0)

    board.write("Finding 1 confirmed.")

    painted = stream.getvalue()
    assert f"{CSI}J" in painted
    assert painted.index("Finding 1 confirmed.") < painted.index("Reviewing ~/src/coral...")


def test_a_stream_that_is_not_a_terminal_gets_the_table_once_at_the_end() -> None:
    stream = io.StringIO()
    board = table(stream, "z-ai/glm-5.3-flash")
    assert stream.getvalue() == ""

    board.close()

    assert stream.getvalue() == "\n".join(board.lines()) + "\n"


def test_a_live_table_takes_over_logging_for_the_run_and_hands_it_back() -> None:
    root = logging.getLogger()
    stream = Terminal()
    existing = list(root.handlers)

    with live_table(Path.cwd(), stream) as board:
        board.agent("z-ai/glm-5.3-flash")
        logging.getLogger("coral.local").warning("a response carried no cost")

    assert "a response carried no cost" in stream.getvalue()
    assert root.handlers == existing


@pytest.mark.parametrize(
    ("model", "label"),
    [("z-ai/glm-5.3-flash", "glm-5.3-flash"), ("glm-5.3-flash", "glm-5.3-flash")],
)
def test_a_row_is_labelled_without_the_vendor_prefix(model: str, label: str) -> None:
    assert short_name(model) == label


def test_a_directory_outside_the_home_directory_is_written_in_full() -> None:
    assert home_relative(Path("/opt/checkout")) == "/opt/checkout"
