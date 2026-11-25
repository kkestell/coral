"""The review step: render what the agent is asked, run it, and leave its review on disk.

This step posts nothing. The finished create-review bodies or issue bodies cross to the publishing
job as an artifact, and so does a failure.
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from coral import container, runner
from coral.deadline import budget_seconds, start, stop_if_expired
from coral.diff import added_lines, diff_text, merge_base
from coral.github.conversation import Comment, Conversation, Thread, read_conversation
from coral.github.post import count, issue_payloads, payloads, write_issue_payloads, write_payloads
from coral.handoff import review_key
from coral.openrouter import model_facts
from coral.publish import described
from coral.spend import Ledger, cap_dollars, stop_if_over_cap

log = logging.getLogger(__name__)

# The agent's container and its copy of the checkout. A fixed name rather than a generated one: a
# job gets a runner VM to itself, so there is nothing for it to collide with.
REVIEWER: Final = "coral-reviewer"


@dataclass(frozen=True)
class PullRequestSubject:
    """A pinned pull request reduced to what the agent's request needs."""

    head: str
    common: str
    title: str
    body: str | None
    conversation: Conversation


@dataclass(frozen=True)
class PushSubject:
    """A pinned main-push range reduced to what the agent's request needs."""

    head: str
    common: str


Subject = PullRequestSubject | PushSubject


def attribution(comment: Comment) -> str:
    """Who wrote a comment, as the agent is told.

    The association is the cheapest basis the model gets for weighing a comment, and Coral's own
    comments have to be identifiable so a finding that already stands is not made twice. Which
    comments are Coral's is settled where the conversation is read, and never here.
    """
    if comment.mine:
        return "Coral"
    return f"{comment.author or 'a deleted account'} ({comment.association})"


def rendered_comment(depth: int, comment: Comment) -> str:
    """One piece of prose under a heading naming its author and its timestamp."""
    return f"{'#' * depth} {attribution(comment)} wrote at {comment.written_at}\n\n{comment.body}"


def rendered_thread(thread: Thread) -> str:
    """One review thread: where it is, its two flags, and the comments in it."""
    # A thread whose line is null is one whose code is gone, which is what an outdated thread
    # against a deleted line looks like.
    if thread.line is None:
        location = "a line that is gone"
    elif thread.start_line is None:
        location = f"line {thread.line}"
    else:
        location = f"lines {thread.start_line} to {thread.line}"
    state = "resolved" if thread.resolved else "unresolved"
    staleness = "outdated" if thread.outdated else "current"
    held = f"It holds {count(thread.total_comments, 'comment')}."
    unread = thread.total_comments - len(thread.comments)
    if unread:
        held = held.removesuffix(".") + f", of which the bound left {unread} unread."
    return "\n\n".join(
        [
            f"### `{thread.path}`, {location}",
            f"This thread is {state} and {staleness}. {held}",
            *(rendered_comment(4, comment) for comment in thread.comments),
        ]
    )


def section(heading: str, entries: list[str]) -> str:
    """A heading and what is under it, saying so when there is nothing."""
    return "\n\n".join([f"## {heading}", *(entries or ["None."])])


def render_conversation(conversation: Conversation) -> str:
    """The conversation as text, with the labels and flags the prompt's rules read against.

    Rendered rather than handed over as JSON: the association on each comment and the resolution
    and staleness flags on each thread are what decide whether a finding still stands, and putting
    them in prose is Coral's deterministic job rather than the model's parsing exercise.
    """
    if conversation.reviewed_commits:
        reviewed = ", ".join(f"`{commit}`" for commit in conversation.reviewed_commits)
        memory = f"Coral has already reviewed these commits: {reviewed}."
    else:
        memory = "Coral has not reviewed this pull request before."

    return "\n\n".join(
        [
            f"Coral read {count(conversation.bound.read, 'comment')} on this pull request and "
            f"left {count(conversation.bound.unread, 'comment')} unread.",
            memory,
            section(
                "Comments on the pull request",
                [rendered_comment(3, comment) for comment in conversation.comments],
            ),
            section(
                "Submitted reviews",
                [
                    rendered_comment(3, past)
                    + f"\n\nThat review's state was {past.state}, on commit "
                    + f"{past.commit or 'not recorded'}."
                    for past in conversation.reviews
                ],
            ),
            section(
                "Review threads",
                [rendered_thread(thread) for thread in conversation.threads],
            ),
        ]
    )


def heading(subject: Subject) -> str:
    """The request's first heading."""
    match subject:
        case PullRequestSubject(title=title):
            return title
        case PushSubject(head=head, common=common):
            return f"Main range {common}..{head}"


def description(subject: Subject) -> str:
    """The prose immediately under a request's heading."""
    match subject:
        case PullRequestSubject(body=body):
            return body.strip() if body and body.strip() else "The author left no description."
        case PushSubject():
            return (
                "This range was pushed directly to main. There is no pull-request description or "
                "conversation."
            )


def change_description(subject: Subject) -> str:
    """What the diff is and what the checkout contains."""
    match subject:
        case PullRequestSubject():
            comparison = "the merge base and the head commit"
            checkout = "the head commit"
        case PushSubject(head=head, common=common):
            comparison = f"the prior main tip `{common}` and the pushed head `{head}`"
            checkout = f"the pushed head `{head}`"
    return (
        f"The diff between {comparison} follows, whole. It is the subject of the review; the "
        f"checkout holds every file at {checkout}."
    )


def render_review_request(subject: Subject, diff: str) -> str:
    """Everything the reviewer receives for either review mode."""
    match subject:
        case PullRequestSubject(conversation=conversation):
            context = [
                "# The conversation on this pull request",
                render_conversation(conversation),
            ]
        case PushSubject():
            context = []
    return "\n\n".join(
        [
            f"# {heading(subject)}",
            description(subject),
            *context,
            "# The change under review",
            change_description(subject),
            diff,
        ]
    )


def read_subject(workspace: Path) -> Subject:
    """Read the staged review subject and finish its pinned comparison range."""
    if runner.push_path().exists():
        push: dict[str, str] = json.loads(runner.push_path().read_text())
        return PushSubject(head=push["head"], common=push["base"])

    pull_request = json.loads(runner.pull_request_path().read_text())
    head = str(pull_request["head"]["sha"])
    base = str(pull_request["base"]["sha"])
    return PullRequestSubject(
        head=head,
        common=merge_base(workspace, base, head),
        title=str(pull_request["title"]),
        body=pull_request["body"],
        conversation=read_conversation(runner.conversation_path()),
    )


def copy_checkout(workspace: Path, destination: Path) -> None:
    """Copy the checkout to where one agent run will own it.

    `cp -a` rather than `shutil.copytree`: `.git` and the whole history come along, which the
    `git log` the reviewer's prompt offers needs, and the file modes come with them.
    """
    result = subprocess.run(
        ["cp", "-a", str(workspace), str(destination)], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Copying the checkout failed: {result.stderr.strip() or 'no output'}")


def provision(name: str, workspace: Path) -> None:
    """A copy of the checkout and a container over it, for the agent run.

    The workspace itself is never written by the agent, so the diff the agent saw and the diff the
    anchors are checked against are the same diff by construction.

    The copy's path on the runner stays here. Every tool the agent holds addresses the container's
    own `/checkout`, so the agent's side of the run needs the container's name and nothing else.
    """
    checkout = runner.checkout_copy_path(name)
    copy_checkout(workspace, checkout)
    container.start(name, checkout)


def review() -> None:
    """Review the checked-out change and leave the result for publishing."""
    # The whole step is inside the failure path: it posts nothing, so the reason file is the only
    # way a failure here reaches the pull request, and there is no failure the file cannot carry.
    try:
        # Popped rather than read, before any other work, so no later code that assembles a child
        # environment out of `os.environ` can pick them up by accident. The review job has no
        # GitHub token, and its API key is either the caller's secret or a decrypted handoff.
        plain_key = os.environ.pop("OPENROUTER_API_KEY")
        encrypted_key = os.environ.pop("ENCRYPTED_OPENROUTER_API_KEY")
        encryption = os.environ.pop("CORAL_KEY_ENCRYPTION_KEY")
        api_key = review_key(plain_key, encrypted_key, encryption)
        if not plain_key:
            runner.mask(api_key)

        # The five the caller configured, each already defaulted by the reusable workflow. The
        # budget runs from the top of the step, so everything below is spent out of it; the resolve
        # step validated the same value and derived this job's own timeout from it.
        name = os.environ["CORAL_MODEL"]
        effort = os.environ["CORAL_REASONING_EFFORT"]
        instructions = os.environ["CORAL_INSTRUCTIONS"]
        deadline = start(budget_seconds(os.environ["CORAL_TIME_BUDGET_MINUTES"]))
        ledger = Ledger(cap=cap_dollars(os.environ["CORAL_SPEND_CAP_DOLLARS"]))

        workspace = runner.workspace()
        subject = read_subject(workspace)
        diff = diff_text(workspace, subject.common, subject.head)
        added = set(added_lines(workspace, subject.common, subject.head))
        request = render_review_request(subject, diff)
        log.info("Asking the agent to review %s in %d characters.", subject.head, len(request))
        facts = model_facts(name)

        # Deferred: importing the agent framework costs about two seconds, and `coral/cli.py`
        # imports this module to reach `review`, so `coral resolve` would pay for it on every
        # delivery.
        from coral.agent import produce_review

        provision(REVIEWER, workspace)
        review = produce_review(
            api_key, name, effort, instructions, facts, REVIEWER, request, deadline, ledger
        )

        log.info("The review spent $%.6f of its $%.6f cap.", ledger.spent, ledger.cap)
        # Nothing is published that a limit should have stopped. The agent run checks its limits
        # as it ends, and this is the same check made where a payload is about to be written.
        stop_if_expired(deadline)
        stop_if_over_cap(ledger)
        # The ledger is final here: the agent run is over, and nothing the publishing job does
        # costs anything. What the body reports and what the line above logs are the same number.
        match subject:
            case PushSubject(common=common, head=head):
                write_issue_payloads(
                    runner.issues_path(), issue_payloads(common, head, review, ledger.spent)
                )
            case PullRequestSubject(head=head):
                write_payloads(runner.payloads_path(), payloads(head, review, added, ledger.spent))
    except Exception as error:
        log.exception("The review failed; the publishing job will report it.")
        runner.reason_path().write_text(described(error))
        # Re-raised: a run that could not review is red.
        raise
