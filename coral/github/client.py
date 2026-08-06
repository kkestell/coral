"""The one authenticated transport. Every REST call Coral makes goes through here."""

from dataclasses import dataclass
from typing import Any, Final

import httpx

BASE_URL: Final = "https://api.github.com"
API_VERSION: Final = "2022-11-28"
TIMEOUT: Final = 30.0


@dataclass(frozen=True)
class GitHub:
    """The GitHub REST API, holding the job's token."""

    token: str

    def get(self, path: str) -> Any:
        return self._request("GET", path, None)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self._request("POST", path, body)

    def _request(self, method: str, path: str, body: dict[str, Any] | None) -> Any:
        response = httpx.request(
            method,
            f"{BASE_URL}{path}",
            json=body,
            timeout=TIMEOUT,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "Authorization": f"Bearer {self.token}",
            },
        )
        # Not `raise_for_status()`, which drops the body. The body is the whole of what a 422 from
        # the create-review endpoint has to say, and it is what a failure comment reports.
        if response.is_success:
            return response.json()
        raise RuntimeError(f"{method} {path} returned {response.status_code}: {response.text}")
