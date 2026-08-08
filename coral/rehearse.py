"""`coral rehearse`: the review step over one commit of a local clone, with no GitHub.

Everything `coral review` reads is staged here instead of by the resolve job: a clone of the
repository checked out at the head commit stands in for the workspace, a stub pull request
carries the two SHAs, and the conversation is empty. What prints is the create-review body the
publishing job would have posted, which is how a change to `coral/prompts/review.md` is judged
without opening a pull request.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

from coral.container import IMAGE
from coral.github.conversation import Bound, Conversation, write_conversation
from coral.github.post import read_payloads
from coral.review import REVIEWER, VERIFIER, review

# Each rehearsal gets a directory here holding the clone the agents review and the files that
# would have crossed between jobs. Gitignored, and read by nothing but this module.
RUNS: Final = Path(".rehearsals")


def line(*command: str) -> str:
    """One git invocation, its output stripped to the line it is."""
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def openrouter_key(repo: Path) -> str:
    """The key out of the repository's `.env`, the file no packaged code reads."""
    for entry in (repo / ".env").read_text().splitlines():
        name, _, value = entry.partition("=")
        if name.strip() == "OPENROUTER_API_KEY":
            return value.strip().strip("'\"")
    raise RuntimeError(f"No OPENROUTER_API_KEY in {repo / '.env'}.")


def stage(repo: Path, head: str, base: str, work: Path) -> None:
    """Leave everything the review step reads where the resolve job would have left it."""
    workspace = work / "checkout"
    coral = work / "temp" / "coral"
    coral.mkdir(parents=True)

    # A full clone rather than a worktree: each agent's copy is mounted into a container, where a
    # worktree's `.git` file would point at a path that does not exist.
    line("git", "clone", "--no-hardlinks", "--quiet", str(repo), str(workspace))
    line("git", "-C", str(workspace), "checkout", "--quiet", head)

    (coral / "pull-request.json").write_text(
        json.dumps(
            {
                "number": 0,
                "title": line("git", "-C", str(repo), "log", "-1", "--format=%s", head),
                "body": line("git", "-C", str(repo), "log", "-1", "--format=%b", head) or None,
                "head": {"sha": head},
                "base": {"sha": base},
            }
        )
    )
    write_conversation(
        coral / "conversation.json",
        Conversation(
            comments=[],
            reviews=[],
            threads=[],
            bound=Bound(read=0, unread=0, oldest_read=None),
            reviewed_commits=[],
        ),
    )


def obliterate(work: Path) -> None:
    """Remove one rehearsal's directory, root-owned files included.

    The agents run as root in their containers and leave root-owned files in their copies of the
    checkout — `__pycache__` from a test run, whatever an install wrote — which `shutil.rmtree`
    running as the developer cannot remove. The same image that wrote them hands them back first.
    """
    if not work.exists():
        return
    try:
        shutil.rmtree(work)
    except PermissionError:
        subprocess.run(
            ["docker", "run", "--rm", "--volume", f"{work}:/junk", IMAGE]
            + ["chown", "--recursive", f"{os.getuid()}:{os.getgid()}", "/junk"],
            capture_output=True,
        )
        shutil.rmtree(work)


def rehearse(arguments: argparse.Namespace) -> None:
    """Stage one commit, run the real review step over it, and print what it produced."""
    repo = arguments.repo.resolve()
    head = line("git", "-C", str(repo), "rev-parse", arguments.head)
    base = line("git", "-C", str(repo), "rev-parse", arguments.base or f"{arguments.head}^")

    work = repo / RUNS / head[:8]
    obliterate(work)
    stage(repo, head, base, work)

    # The containers carry fixed names because a job gets a runner VM to itself. This machine
    # keeps its containers between rehearsals, so the last run's have to go first.
    for name in (REVIEWER, VERIFIER):
        subprocess.run(["docker", "rm", "--force", name], capture_output=True)

    # An empty toolcache. The agent installs any interpreter it wants with `apt-get`, which the
    # prompt already tells it; a minute of installing per rehearsal costs less than keeping a
    # local replica of the hosted image's cache current.
    (work / "toolcache").mkdir()

    # The environment the workflow would have built, assembled in this process: `review` reads
    # everything it needs from these and nothing else.
    os.environ.update(
        OPENROUTER_API_KEY=openrouter_key(repo),
        ENCRYPTED_OPENROUTER_API_KEY="",
        CORAL_KEY_ENCRYPTION_KEY="",
        CORAL_TOOLCACHE=str(work / "toolcache"),
        CORAL_MODEL=arguments.model,
        CORAL_REASONING_EFFORT=arguments.effort,
        CORAL_TIME_BUDGET_MINUTES=arguments.budget,
        CORAL_SPEND_CAP_DOLLARS=arguments.cap,
        RUNNER_TEMP=str(work / "temp"),
        GITHUB_WORKSPACE=str(work / "checkout"),
    )

    print(f"Rehearsing a review of {head[:8]} against {base[:8]}.", file=sys.stderr)
    try:
        review()
    except Exception:
        # `review` already wrote the reason and logged the failure; the reason file is what the
        # publishing job would have posted, so it is what a rehearsal prints.
        print(f"\nThe failure comment would carry:\n{(work / 'temp/coral/reason.txt').read_text()}")
        raise SystemExit(1) from None

    payloads = read_payloads(work / "temp" / "coral" / "review-payloads.json")
    print(f"\n{payloads.anchored['body']}")
    for comment in payloads.anchored["comments"]:
        place = f"{comment['path']}:{comment.get('start_line', comment['line'])}-{comment['line']}"
        print(f"\n--- {place}\n{comment['body']}")

    if not arguments.keep:
        obliterate(work / "checkout")


def add_rehearse_arguments(parser: argparse.ArgumentParser) -> None:
    """The rehearse subcommand's arguments, declared next to the code that reads them."""
    parser.add_argument("head", help="the commit to review")
    parser.add_argument("--base", help="what to review it against; its parent by default")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="the repository to clone")
    parser.add_argument("--model", default="openai/gpt-5.6-luna")
    parser.add_argument("--effort", default="")
    parser.add_argument("--budget", default="20", help="the time budget in minutes")
    parser.add_argument("--cap", default="2.00", help="the spend cap in dollars")
    parser.add_argument("--keep", action="store_true", help="leave the clone behind")
