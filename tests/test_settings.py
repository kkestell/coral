"""Tests of the CLI settings boundary."""

import json
from pathlib import Path

import pytest

from coral.settings import AgentSettings, Settings, load_settings, parse_settings


def configured() -> dict[str, object]:
    return {
        "openrouter_api_key": "sk-test",
        "review_agents": [
            {"model": "anthropic/claude-sonnet-4", "effort": "high"},
            {"model": "openai/gpt-5", "effort": ""},
        ],
        "num_reviews": 2,
        "max_concurrent_reviews": 1,
        "verification_agent": {"model": "google/gemini-2.5-pro", "effort": "medium"},
        "time_budget_minutes": 20,
        "spend_cap_dollars": 2.0,
    }


def test_every_setting_is_read_from_one_object() -> None:
    assert parse_settings(configured()) == Settings(
        openrouter_api_key="sk-test",
        review_agents=[
            AgentSettings(model="anthropic/claude-sonnet-4", effort="high"),
            AgentSettings(model="openai/gpt-5", effort=""),
        ],
        num_reviews=2,
        max_concurrent_reviews=1,
        verification_agent=AgentSettings(model="google/gemini-2.5-pro", effort="medium"),
        time_budget_minutes=20,
        spend_cap_dollars=2.0,
    )


def test_at_least_one_reviewer_is_required() -> None:
    value = configured() | {"review_agents": [], "num_reviews": 1}
    with pytest.raises(RuntimeError, match="non-empty JSON array"):
        parse_settings(value)


def test_more_reviews_than_review_agents_is_refused() -> None:
    value = configured() | {"num_reviews": 3}
    with pytest.raises(RuntimeError, match="asks for 3 reviews, and only 2 review agents"):
        parse_settings(value)


def test_fewer_reviews_than_review_agents_leaves_the_rest_as_fallbacks() -> None:
    assert parse_settings(configured() | {"num_reviews": 1}).num_reviews == 1


@pytest.mark.parametrize("key", ["num_reviews", "max_concurrent_reviews"])
@pytest.mark.parametrize("value", [0, -1, 1.5, True, "2", None])
def test_a_count_has_to_be_a_whole_number_of_at_least_one(key: str, value: object) -> None:
    with pytest.raises(RuntimeError, match=f"settings.{key} must be a whole number"):
        parse_settings(configured() | {key: value})


def test_agent_model_and_effort_are_both_explicit() -> None:
    value = configured() | {"review_agents": [{"model": "openai/gpt-5"}], "num_reviews": 1}
    with pytest.raises(RuntimeError, match=r"review_agents\[0\]\.effort"):
        parse_settings(value)


def test_unknown_settings_are_refused() -> None:
    with pytest.raises(RuntimeError, match="unknown settings: model"):
        parse_settings(configured() | {"model": "old-format"})


def test_a_missing_file_names_the_required_path(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    with pytest.raises(RuntimeError, match=str(path)):
        load_settings(path)


def test_invalid_json_reports_its_location(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"openrouter_api_key": }')
    with pytest.raises(RuntimeError, match=r"line 1, column"):
        load_settings(path)


def test_load_settings_reads_json(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(configured()))
    assert load_settings(path) == parse_settings(configured())
