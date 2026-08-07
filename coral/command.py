"""What counts as a request: the command, who may make one, and Coral's own comments.

A request is read off a comment body and an author association and nothing else, so one rule
answers both for the comment on the triggering payload and for every comment in the fetched
conversation.
"""

import re
from typing import Final

from coral.github.marker import reviewed_commit

# Spelled in lower case and matched exactly. The workflow's job-level condition uses `contains`,
# which is not case sensitive, so `/CORAL` reaches a runner and then stops here with the command
# inert. One spelling is one thing to document and one thing to test, and folding case in Python
# while the requirements, `README.md`, and every example say `/coral` would buy a spelling
# nobody was told about.
COMMAND: Final = "/coral"

# The associations the workflow's job-level condition names. Testing them again here is not a
# duplicate of that condition: the condition tested one comment, and this tests every comment in
# the conversation. Doing it for the triggering comment too costs one set membership and leaves
# one definition in the codebase of who may ask.
WRITE_ACCESS: Final = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})

# A fenced code block opens on a line of three or more backticks or tildes indented no more than
# three spaces, and everything after the run of characters on that line is the info string.
FENCE: Final = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def closes(opened: str, fence: str, after: str) -> bool:
    """Whether a fence line ends the block another fence line opened.

    A closing fence is the same character, at least as long, with nothing after it. A fence left
    unclosed therefore runs to the end of the comment, which is what GitHub renders too.
    """
    return fence[0] == opened[0] and len(fence) >= len(opened) and not after.strip()


def asks_for_review(body: str) -> bool:
    """Whether any line of a comment body is the command.

    A line counts when it is exactly the command, with nothing before it and nothing after it
    but whitespace. That one rule is what makes the inert forms inert, and most of them need no
    branch of their own: `/coral` in a sentence is not the whole line, `` `/coral` `` is
    backticks around the command rather than the command, `> /coral` begins with the blockquote
    marker GitHub's quote-reply button writes, `- /coral` begins with a list marker, and an
    indented `/coral` has whitespace before the command on its line. A code fence is the one
    form the rule cannot see, because the line inside it really is exactly the command, and it
    is why this walk tracks fence state at all.

    Trailing whitespace is allowed. It is invisible in a rendered comment and a person who left
    it cannot tell that they did, and two trailing spaces are a Markdown hard line break, which
    is just as invisible.
    """
    opened: str | None = None
    for line in body.splitlines():
        found = FENCE.match(line)
        if opened is not None:
            if found and closes(opened, found[1], found[2]):
                opened = None
        elif found:
            opened = found[1]
        elif line.rstrip() == COMMAND:
            return True
    return False


def is_request(body: str, association: str) -> bool:
    """Whether this comment asks for a review and its author may ask for one."""
    # Coral cannot trigger itself today, because an event created with the job's own token
    # starts no workflow run at all. This is here because that property expires the moment Coral
    # is given an identity of its own.
    if reviewed_commit(body) is not None:
        return False
    return association in WRITE_ACCESS and asks_for_review(body)
