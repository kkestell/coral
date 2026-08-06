"""The gatekeeper step: fetch the pull request, acknowledge the request, decide whether to go on.

A decline is not a failure. This step writes `proceed=false`, says why, and exits zero, and the
checkout and review steps skip. A pull request Coral was never going to review is not a broken
pull request.
"""

import json
import logging
import os

from coral import runner
from coral.github.client import GitHub
from coral.github.reactions import react

log = logging.getLogger(__name__)


def resolve() -> None:
    """Pin the commits Coral will review, or stop the run."""
    event = runner.event()
    github = GitHub(token=os.environ["GITHUB_TOKEN"])
    pull_request = github.get(f"/repos/{event.owner}/{event.repo}/pulls/{event.number}")

    # The reaction is the acknowledgment, and it comes before any decision that could stop the
    # run: somebody whose request Coral is about to decline still deserves to be told it was
    # heard, and a comment-triggered run gives them no other sign.
    react(github, event)

    # Verbatim, because the review step reads the head SHA, the base SHA, the number, and the
    # repository back out of it rather than fetching the pull request a second time.
    runner.pull_request_path().write_text(json.dumps(pull_request))

    state = pull_request["state"]
    if state != "open":
        log.info("Not reviewing pull request %s: it is %s.", event.number, state)
        runner.write_output("proceed", "false")
        return

    runner.write_output("head-sha", pull_request["head"]["sha"])
    runner.write_output("proceed", "true")
