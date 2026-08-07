"""OpenRouter's management API: minting the one API key this run gets.

The only place Coral speaks to OpenRouter about keys. Completions go through `ChatOpenRouter` in
`coral/agent.py` and never through here, and a management key cannot make one anyway.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import httpx

BASE_URL: Final = "https://openrouter.ai/api/v1"
TIMEOUT: Final = 30.0

# What a minted key may spend. Two orders of magnitude above the most expensive review measured:
# the account's `Coral` key spent $0.063 across every live check up to 2026-08-07, so no single
# review has yet cost a cent. Low enough that a leaked key is not worth extracting. Re-measure
# before raising it.
KEY_LIMIT_DOLLARS: Final = 2.00

# How long a minted key lives. Twice the review job's `timeout-minutes: 30`, which is the only
# long pole after minting; the slack covers the runner queue time between the two jobs, which
# GitHub does not bound. A review job that starts later than that finds the provider answering
# 401, and the failure comment carries it.
KEY_TTL_SECONDS: Final = 3600

log = logging.getLogger(__name__)


def key_request(name: str, now: datetime) -> dict[str, Any]:
    """The create-key body: the name, the spend cap, and the expiry that revokes the key.

    The expiry is what makes revocation independent of anything the rest of the run does. No
    cleanup call can be skipped by a cancelled run, because there is no cleanup call.
    """
    expiry = now + timedelta(seconds=KEY_TTL_SECONDS)
    return {
        "name": name,
        "limit": KEY_LIMIT_DOLLARS,
        # ISO 8601 UTC, milliseconds, `Z`. The endpoint echoes back exactly what it was sent.
        "expires_at": expiry.astimezone(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
    }


def minted_key(answer: dict[str, Any]) -> str:
    """The key string out of the create-key answer, which carries it once and never again.

    It sits at the top level, beside a `data` object holding the hash and the limits. An answer
    without it is one nothing later in the run can recover from.
    """
    if "key" not in answer:
        raise RuntimeError(
            "OpenRouter created a key and answered without one. The answer's keys were "
            f"{sorted(answer)}."
        )
    return str(answer["key"])


def mint(management_key: str, name: str) -> str:
    """Create this run's own API key, capped and expiring, and return it.

    No retry: one mint per run, and a management key that cannot mint now will not mint on a
    second attempt either. The status and the body go into the failure comment, because
    OpenRouter's own words are what a broken secret has to say.
    """
    log.info("Minting an OpenRouter key named %s, capped at $%.2f.", name, KEY_LIMIT_DOLLARS)
    response = httpx.post(
        f"{BASE_URL}/keys",
        json=key_request(name, datetime.now(UTC)),
        timeout=TIMEOUT,
        headers={"Authorization": f"Bearer {management_key}"},
    )
    if not response.is_success:
        raise RuntimeError(f"POST /api/v1/keys returned {response.status_code}: {response.text}")
    return minted_key(response.json())
