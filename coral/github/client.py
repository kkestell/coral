"""The one authenticated transport. Every call Coral makes to GitHub goes through here."""

import json
from dataclasses import dataclass
from typing import Any, Final

import httpx

BASE_URL: Final = "https://api.github.com"
API_VERSION: Final = "2022-11-28"
TIMEOUT: Final = 30.0

# What one answer may weigh before Coral gives up on it, read off the stream so an answer past it
# is never held whole. GitHub takes 65,536 characters in a comment and the conversation query asks
# for thousands of comments at once, so a pull request somebody filled with enormous comments can
# answer with more than the runner has memory for. Two orders of magnitude above every answer
# measured, `cli/cli` 10513 included.
MAX_RESPONSE_BYTES: Final = 16 * 1024 * 1024


class ApiError(RuntimeError):
    """A GitHub call that did not succeed, holding what the caller may act on.

    Typed because the retry in `coral/github/post.py` recovers from a 422 and from nothing else,
    and a status matched on the message text is not a status. It subclasses `RuntimeError`, so
    every caller that does not care about the status is unaffected.
    """

    def __init__(self, method: str, path: str, status: int, body: str) -> None:
        super().__init__(f"{method} {path} returned {status}: {body}")
        self.status = status
        self.body = body


def data_of(answer: dict[str, Any]) -> Any:
    """The `data` half of a GraphQL answer, or the errors it carries instead."""
    # A GraphQL query that failed still answers with HTTP 200 and an `errors` key, so the status
    # check in `_request` sees a success. This is the only place that failure shows up, and
    # without it a broken query becomes a `KeyError` on `data` several frames later.
    if "errors" in answer:
        messages = "; ".join(str(error["message"]) for error in answer["errors"])
        raise RuntimeError(f"GraphQL query failed: {messages}")
    return answer["data"]


def body_of(response: httpx.Response, method: str, path: str) -> bytes:
    """One answer's bytes, refusing an answer larger than Coral will hold.

    The refusal has to happen while the answer is still arriving. Reading it and then measuring it
    is the memory this exists to not spend.
    """
    chunks: list[bytes] = []
    weight = 0
    for chunk in response.iter_bytes():
        weight += len(chunk)
        if weight > MAX_RESPONSE_BYTES:
            raise RuntimeError(
                f"{method} {path} answered with more than {MAX_RESPONSE_BYTES} bytes, which is "
                "more than Coral will read of one answer."
            )
        chunks.append(chunk)
    return b"".join(chunks)


@dataclass(frozen=True)
class GitHub:
    """The GitHub API, holding the job's token."""

    token: str

    def get(self, path: str) -> Any:
        return self._request("GET", path, None)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self._request("POST", path, body)

    def graphql(self, query: str, variables: dict[str, Any]) -> Any:
        return data_of(self._request("POST", "/graphql", {"query": query, "variables": variables}))

    def _request(self, method: str, path: str, body: dict[str, Any] | None) -> Any:
        with httpx.stream(
            method,
            f"{BASE_URL}{path}",
            json=body,
            timeout=TIMEOUT,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "Authorization": f"Bearer {self.token}",
            },
        ) as response:
            answer = body_of(response, method, path)
        # Not `raise_for_status()`, which drops the body. The body is the whole of what a 422 from
        # the create-review endpoint has to say, and it is what a failure comment reports.
        if response.is_success:
            return json.loads(answer)
        raise ApiError(method, path, response.status_code, answer.decode(errors="replace"))
