"""The one configuration file read by the Coral CLI."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from coral.deadline import budget_minutes
from coral.spend import cap_dollars

SETTINGS_PATH: Final = Path.home() / ".config" / "coral" / "settings.json"


@dataclass(frozen=True)
class AgentSettings:
    """The OpenRouter model and reasoning effort for one agent run."""

    model: str
    effort: str


@dataclass(frozen=True)
class Settings:
    """Everything configurable about one CLI review."""

    openrouter_api_key: str
    review_agents: list[AgentSettings]
    num_reviews: int
    max_concurrent_reviews: int
    verification_agent: AgentSettings
    time_budget_minutes: int
    spend_cap_dollars: float


def _object(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise RuntimeError(f"{where} must be a JSON object.")
    return value


def _string(data: dict[str, object], key: str, where: str, *, empty: bool = False) -> str:
    value = data.get(key)
    if not isinstance(value, str) or (not empty and not value):
        allowance = "a string" if empty else "a non-empty string"
        raise RuntimeError(f"{where}.{key} must be {allowance}.")
    return value


def _count(data: dict[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RuntimeError(f"settings.{key} must be a whole number of at least one.")
    return value


def _agent(value: object, where: str) -> AgentSettings:
    data = _object(value, where)
    expected = {"model", "effort"}
    if extra := set(data) - expected:
        raise RuntimeError(f"{where} has unknown settings: {', '.join(sorted(extra))}.")
    return AgentSettings(
        model=_string(data, "model", where),
        effort=_string(data, "effort", where, empty=True),
    )


def parse_settings(value: object) -> Settings:
    """Validate the decoded contents of the settings file."""
    data = _object(value, "settings")
    expected = {
        "openrouter_api_key",
        "review_agents",
        "num_reviews",
        "max_concurrent_reviews",
        "verification_agent",
        "time_budget_minutes",
        "spend_cap_dollars",
    }
    if extra := set(data) - expected:
        raise RuntimeError(f"settings has unknown settings: {', '.join(sorted(extra))}.")

    configured_reviewers = data.get("review_agents")
    if not isinstance(configured_reviewers, list) or not configured_reviewers:
        raise RuntimeError("settings.review_agents must be a non-empty JSON array.")

    wanted = _count(data, "num_reviews")
    if wanted > len(configured_reviewers):
        raise RuntimeError(
            f"settings.num_reviews asks for {wanted} reviews, and only "
            f"{len(configured_reviewers)} review agents are configured to produce them."
        )
    concurrency = _count(data, "max_concurrent_reviews")

    budget = data.get("time_budget_minutes")
    if not isinstance(budget, int) or isinstance(budget, bool):
        raise RuntimeError("settings.time_budget_minutes must be a whole number.")
    budget_minutes(str(budget))

    cap = data.get("spend_cap_dollars")
    if not isinstance(cap, int | float) or isinstance(cap, bool):
        raise RuntimeError("settings.spend_cap_dollars must be a number.")
    validated_cap = cap_dollars(str(cap))

    return Settings(
        openrouter_api_key=_string(data, "openrouter_api_key", "settings"),
        review_agents=[
            _agent(agent, f"settings.review_agents[{index}]")
            for index, agent in enumerate(configured_reviewers)
        ],
        num_reviews=wanted,
        max_concurrent_reviews=concurrency,
        verification_agent=_agent(data.get("verification_agent"), "settings.verification_agent"),
        time_budget_minutes=budget,
        spend_cap_dollars=validated_cap,
    )


def load_settings(path: Path = SETTINGS_PATH) -> Settings:
    """Read and validate Coral's settings, with a command-line-sized failure."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"No Coral settings file exists at {path}.") from None
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Coral could not read {path}: line {error.lineno}, column {error.colno}: {error.msg}."
        ) from None
    return parse_settings(value)
