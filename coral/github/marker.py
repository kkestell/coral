"""The sentinel: writing it into a review body and reading it back out.

Every review Coral posts opens with this marker. It is invisible in rendered Markdown, and the
commit SHA inside it is how the next run knows which commits Coral has already looked at. This
is the whole of Coral's memory.
"""

import re
from typing import Final

SENTINEL: Final = "coral:reviewed"
PATTERN: Final = re.compile(rf"<!-- {SENTINEL} commit=([0-9a-f]+) -->")


def marker(commit: str) -> str:
    """The line that opens a review Coral posted."""
    return f"<!-- {SENTINEL} commit={commit} -->"


def reviewed_commit(body: str) -> str | None:
    """The commit a review body says it reviewed, or `None` when somebody else wrote it."""
    found = PATTERN.search(body)
    return found.group(1) if found else None
