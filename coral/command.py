"""What counts as a request: the command, who may make one, and Coral's own comments.

A request is read off a comment body and its author's permission on the repository, so one rule
answers both for the comment on the triggering payload and for every comment in the fetched
conversation.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Final

from coral.github.client import ApiError, GitHub
from coral.github.marker import has_marker

log = logging.getLogger(__name__)

# Spelled in lower case and matched exactly. The workflow's job-level condition uses `contains`,
# which is not case sensitive, so `/CORAL` reaches a runner and then stops here with the command
# inert. One spelling is one thing to document and one thing to test, and folding case in Python
# while the requirements, `README.md`, and every example say `/coral` would buy a spelling
# nobody was told about.
COMMAND: Final = "/coral"

# The permissions the collaborator endpoint reports, and the three that can push. An
# `author_association` cannot stand in for one: GitHub gives `MEMBER` to every member of the
# owning organization and `COLLABORATOR` to anybody invited to the repository, read-only and
# triage-only people included. The workflow's job-level condition still names the associations,
# where it keeps runners from being allocated for a delivery that is certainly not a trigger.
WRITE_PERMISSIONS: Final = frozenset({"admin", "maintain", "write"})

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


@dataclass
class Access:
    """Who may ask for a review, one lookup per login and no more.

    A run reads several comments by the same author — the one on the payload and whatever the
    conversation offered — and the answer is the same for all of them.
    """

    github: GitHub
    owner: str
    repo: str
    known: dict[str, bool] = field(default_factory=dict)

    def writes(self, login: str | None) -> bool:
        """Whether this login can push to the repository being reviewed."""
        # `None` is an account that has been deleted. There is nobody left to ask about.
        if login is None:
            return False
        if login not in self.known:
            self.known[login] = self.fetch(login)
        return self.known[login]

    def fetch(self, login: str) -> bool:
        """Ask GitHub what this login may do here, answering no when it will not say.

        A permission Coral could not read is not one it may act on. Logged rather than raised: a
        run that declines costs a review, and a run that fails costs a comment saying the review
        broke, which is the louder of the two for a request that may not have been one.
        """
        try:
            answer = self.github.get(
                f"/repos/{self.owner}/{self.repo}/collaborators/{login}/permission"
            )
        except ApiError as error:
            log.warning("Could not read what %s may do in this repository: %s", login, error)
            return False
        return str(answer["permission"]) in WRITE_PERMISSIONS


def is_request(body: str, author: str | None, access: Access) -> bool:
    """Whether this comment asks for a review and its author may ask for one.

    The body decides first, so the call behind `access` is made only for a comment that really is
    the command.
    """
    # Coral cannot trigger itself today, because an event created with the job's own token
    # starts no workflow run at all. This is here because that property expires the moment Coral
    # is given an identity of its own. The marker is taken at face value here, unlike everywhere
    # else, because the comment on a payload carries no `viewerDidAuthor` to check it against;
    # forging one costs the forger the command in their own comment and nothing else.
    if has_marker(body) or not asks_for_review(body):
        return False
    return access.writes(author)
