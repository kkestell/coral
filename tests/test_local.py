"""Tests of local scope selection, checkout copies, aggregation, and rendering."""

import subprocess
import threading
import time
from pathlib import Path

import pytest

from coral.deadline import Deadline, start
from coral.local import (
    combined_review,
    copy_checkout,
    default_scope,
    gather_reviews,
    render,
    verification_request,
)
from coral.schema import FileAnchor, Finding, Review
from coral.settings import AgentSettings
from coral.spend import Ledger


def command(workspace: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=workspace, capture_output=True, text=True, check=True
    ).stdout.strip()


def repository(path: Path, *, commit: bool = True) -> Path:
    path.mkdir()
    command(path, "init", "-b", "main")
    command(path, "config", "user.email", "test@example.com")
    command(path, "config", "user.name", "Test")
    if commit:
        (path / "code.py").write_text("before\n")
        command(path, "add", "code.py")
        command(path, "commit", "--message", "first")
    return path


def finding(body: str = "The parser returns the wrong value.") -> Finding:
    return Finding(
        body=body,
        anchor=FileAnchor(kind="file", path="code.py"),
        severity="high",
        regression_test=None,
    )


def result(summary: str, *findings: Finding) -> Review:
    return Review(summary=summary, findings=list(findings))


def agents(*models: str) -> list[AgentSettings]:
    return [AgentSettings(model=model, effort="high") for model in models]


def gathered(
    models: list[str],
    wanted: int,
    concurrency: int,
    failing: set[str],
    *,
    deadline: Deadline | None = None,
    ledger: Ledger | None = None,
) -> tuple[list[Review], list[str]]:
    """Schedule over models whose named entries raise, and report what ran."""
    attempted: list[str] = []
    lock = threading.Lock()

    def run(index: int, configured: AgentSettings) -> Review:
        with lock:
            attempted.append(configured.model)
        if configured.model in failing:
            raise RuntimeError(f"{configured.model} timed out")
        return result(configured.model)

    reviews = gather_reviews(
        agents(*models),
        wanted,
        concurrency,
        deadline if deadline is not None else start(600.0),
        ledger if ledger is not None else Ledger(cap=10.0),
        run,
    )
    return reviews, attempted


def test_only_as_many_reviewers_as_reviews_asked_for_run() -> None:
    reviews, attempted = gathered(["a", "b", "c"], wanted=2, concurrency=2, failing=set())
    assert [review.summary for review in reviews] == ["a", "b"]
    assert sorted(attempted) == ["a", "b"]


def test_a_failed_reviewer_falls_back_to_the_next_configured_model() -> None:
    reviews, attempted = gathered(["a", "b", "c"], wanted=2, concurrency=2, failing={"b"})
    assert [review.summary for review in reviews] == ["a", "c"]
    assert sorted(attempted) == ["a", "b", "c"]


def test_reviews_stay_in_configured_order_whatever_fell_back() -> None:
    reviews, attempted = gathered(["a", "b", "c", "d"], wanted=2, concurrency=1, failing={"a", "c"})
    assert [review.summary for review in reviews] == ["b", "d"]
    assert attempted == ["a", "b", "c", "d"]


def test_running_out_of_models_returns_the_reviews_that_came_back() -> None:
    reviews, attempted = gathered(["a", "b", "c"], wanted=3, concurrency=3, failing={"a", "b"})
    assert [review.summary for review in reviews] == ["c"]
    assert sorted(attempted) == ["a", "b", "c"]


def test_no_model_producing_a_review_fails_the_run() -> None:
    with pytest.raises(RuntimeError, match="None of the 2 configured review agents"):
        gathered(["a", "b"], wanted=1, concurrency=1, failing={"a", "b"})


def test_concurrency_bounds_how_many_reviewers_run_at_once() -> None:
    live = 0
    peak = 0
    lock = threading.Lock()

    def run(index: int, configured: AgentSettings) -> Review:
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.05)
        with lock:
            live -= 1
        return result(configured.model)

    reviews = gather_reviews(agents("a", "b", "c", "d"), 4, 2, start(600.0), Ledger(cap=10.0), run)
    assert len(reviews) == 4
    assert peak == 2


def test_a_spent_time_budget_stops_the_fallback_instead_of_trying_another_model() -> None:
    with pytest.raises(RuntimeError, match="ran out of time"):
        gathered(["a", "b"], wanted=1, concurrency=1, failing={"a"}, deadline=start(0.0))


def test_a_reached_spend_cap_stops_the_fallback_instead_of_trying_another_model() -> None:
    ledger = Ledger(cap=1.0)
    ledger.add(2.0)
    with pytest.raises(RuntimeError, match="ran out of money"):
        gathered(["a", "b"], wanted=1, concurrency=1, failing={"a"}, ledger=ledger)


def test_uncommitted_changes_are_the_first_default(tmp_path: Path) -> None:
    repo = repository(tmp_path / "repo")
    (repo / "code.py").write_text("after\n")
    assert default_scope(repo) == (
        "Review all uncommitted changes, including staged, unstaged, and untracked files."
    )


def test_an_untracked_file_is_an_uncommitted_change(tmp_path: Path) -> None:
    repo = repository(tmp_path / "repo")
    (repo / "new.py").write_text("new\n")
    assert default_scope(repo).startswith("Review all uncommitted changes")


def test_a_clean_repository_defaults_to_the_latest_commit(tmp_path: Path) -> None:
    assert default_scope(repository(tmp_path / "repo")) == "Review the most recent commit."


def test_a_repository_without_a_commit_defaults_to_the_codebase(tmp_path: Path) -> None:
    assert default_scope(repository(tmp_path / "repo", commit=False)) == (
        "Review the whole codebase."
    )


def test_a_plain_directory_defaults_to_the_codebase(tmp_path: Path) -> None:
    assert default_scope(tmp_path) == "Review the whole codebase."


def test_a_checkout_copy_has_local_changes_but_not_ignored_files(tmp_path: Path) -> None:
    repo = repository(tmp_path / "repo")
    (repo / ".gitignore").write_text(".env\n")
    (repo / "code.py").write_text("after\n")
    (repo / "new.py").write_text("new\n")
    (repo / ".env").write_text("OPENROUTER_API_KEY=secret\n")

    checkout = tmp_path / "checkout"
    copy_checkout(repo, checkout)

    assert (checkout / "code.py").read_text() == "after\n"
    assert (checkout / "new.py").read_text() == "new\n"
    assert not (checkout / ".env").exists()
    assert command(checkout, "rev-parse", "HEAD") == command(repo, "rev-parse", "HEAD")


def test_reviewer_outputs_flatten_in_configured_order() -> None:
    first = finding("First.")
    second = finding("Second.")
    combined = combined_review([result("One.", first), result("Two.", second)])
    assert combined.summary == "One.\n\nTwo."
    assert combined.findings == [first, second]


def test_the_verifier_receives_the_scope_unchanged_and_all_reviewer_output() -> None:
    request = verification_request("focus on the parser", [result("Looked at it.", finding())])
    assert "# Review scope\n\nfocus on the parser" in request
    assert "Looked at it." in request
    assert "## Finding 0" in request
    assert "The parser returns the wrong value." in request


def test_the_final_markdown_contains_only_verified_review_content() -> None:
    output = render(result("The final summary.", finding()), 0.00125)
    assert output.startswith("# Coral code review\n\nThe final summary.")
    assert "### High severity — `code.py`, the whole file" in output
    assert "The parser returns the wrong value." in output
    assert "*This review cost $0.0013.*" in output
