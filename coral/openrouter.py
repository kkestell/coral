"""The OpenRouter model listing used to build an agent's model profile."""

import logging
from dataclasses import dataclass
from typing import Any, Final, TypeIs

import httpx

BASE_URL: Final = "https://openrouter.ai/api/v1"
TIMEOUT: Final = 30.0

# The prefix OpenRouter's alias ids carry. An alias resolves to whichever model is current, so a
# review's model would not be knowable from the caller's file, and the request would succeed
# rather than fail: aliases are in the listing and the per-model route answers 200 for them, so
# refusing one has to be Coral's own check.
ALIAS_PREFIX: Final = "~"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelFacts:
    """What OpenRouter's listing says about one model, reduced to what its profile is built from."""

    context_length: int
    # Null in the listing for the models whose output ceiling OpenRouter does not report.
    max_completion_tokens: int | None
    parameters: frozenset[str]


def counted(value: Any) -> TypeIs[int]:
    """Whether a listing field holds a positive count. `True` is an `int` and is not one."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def facts_of(models: list[dict[str, Any]], name: str) -> ModelFacts:
    """Find the named model in the listing and reduce it to the facts its profile is built from.

    Only the selected entry is read. The listing carries hundreds of models this run will never
    ask anything of, and one of those being malformed is not this run's problem.
    """
    entry = next(
        (model for model in models if isinstance(model, dict) and model.get("id") == name), None
    )
    if entry is None:
        raise RuntimeError(
            f"OpenRouter does not list a model named {name!r}. Name a model from "
            "https://openrouter.ai/models exactly as it appears there."
        )

    # The listing is an external input, so an entry Coral cannot read owes one clear message
    # naming what it could not read, rather than a `KeyError` out of the middle of a profile.
    def unreadable(what: str) -> RuntimeError:
        return RuntimeError(
            f"OpenRouter's listing entry for model {name!r} is unreadable: {what}. The entry's "
            f"keys were {sorted(entry)}."
        )

    top_provider = entry.get("top_provider")
    if not isinstance(top_provider, dict) or "max_completion_tokens" not in top_provider:
        raise unreadable("it carries no `top_provider` reporting a completion ceiling")

    context_length = entry.get("context_length")
    if not counted(context_length):
        raise unreadable(f"its context length is {context_length!r}")

    # Null for the models whose output ceiling OpenRouter does not report, which is a fact about
    # the model rather than a malformed entry.
    ceiling = top_provider["max_completion_tokens"]
    if ceiling is not None and not counted(ceiling):
        raise unreadable(f"its completion ceiling is {ceiling!r}")

    parameters = entry.get("supported_parameters")
    if not isinstance(parameters, list) or any(not isinstance(one, str) for one in parameters):
        raise unreadable(f"its supported parameters are {parameters!r}")

    return ModelFacts(
        context_length=context_length,
        max_completion_tokens=ceiling,
        parameters=frozenset(parameters),
    )


def model_facts(name: str) -> ModelFacts:
    """Fetch the listing and reduce the named model to the facts its profile is built from.

    Unauthenticated, about 650 KB, once per run. The whole listing rather than the per-model route
    because a name Coral will not review has to be refused before anything is asked of it.
    """
    if ALIAS_PREFIX in name:
        raise RuntimeError(
            f"Coral will not review with {name!r}. OpenRouter resolves a `{ALIAS_PREFIX}` alias to "
            "whichever model is current, so the model a review ran on would not be knowable from "
            "the settings file. Name the model exactly."
        )
    log.info("Fetching OpenRouter's model listing to build the profile for %s.", name)
    response = httpx.get(f"{BASE_URL}/models", timeout=TIMEOUT)
    if not response.is_success:
        raise RuntimeError(f"GET /api/v1/models returned {response.status_code}: {response.text}")
    return facts_of(response.json()["data"], name)
