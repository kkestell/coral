"""The sentinel: writing it into a comment body and reading it back out.

Every comment Coral posts opens with this marker. It is invisible in rendered Markdown, and the
commit SHA inside it is how the next run knows which commits Coral has already looked at. This
is the whole of Coral's memory.

The commit is optional because a run can fail before it has one: the pull request was never
fetched, and a comment payload carries no head SHA.

The marker is characters anybody can type, so a body carrying one says only that it claims to be
Coral's. What settles that it is Coral's is `coral/github/conversation.py`.
"""

import re
from typing import Final

SENTINEL: Final = "coral:reviewed"
PATTERN: Final = re.compile(rf"<!-- {SENTINEL}(?: commit=([0-9a-f]+))? -->")


def marker(commit: str | None) -> str:
    """The line every comment Coral posts opens with, naming the commit when there is one."""
    if commit is None:
        return f"<!-- {SENTINEL} -->"
    return f"<!-- {SENTINEL} commit={commit} -->"


def has_marker(body: str) -> bool:
    """Whether a body carries the sentinel, which it does whether or not a commit follows it."""
    return PATTERN.search(body) is not None


def reviewed_commit(body: str) -> str | None:
    """The commit a body says it reviewed, or `None` when there is none to read."""
    found = PATTERN.search(body)
    return found.group(1) if found else None
