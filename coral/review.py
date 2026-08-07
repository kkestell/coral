"""The review step: render what each agent run is asked, run both, post what survives."""

import json
import logging
import os

from coral import runner
from coral.deadline import REVIEWER_BUDGET_SECONDS, start
from coral.diff import added_lines, diff_text, merge_base, reset
from coral.github.client import GitHub
from coral.github.conversation import Comment, Conversation, Thread, read_conversation
from coral.github.post import count, is_open, post_comment, post_review
from coral.report import described, failure_comment
from coral.schema import Review, confirmed, where

log = logging.getLogger(__name__)


def attribution(comment: Comment) -> str:
    """Who wrote a comment, as the agent is told.

    The association is the cheapest basis the model gets for weighing a comment, and Coral's own
    comments have to be identifiable so a finding that already stands is not made twice. Coral
    recognizes its own by the marker, never by the author login.
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


def render_request(title: str, body: str | None, diff: str, conversation: Conversation) -> str:
    """Everything the agent is given: the pull request, its conversation, and the change."""
    return "\n\n".join(
        [
            f"# {title}",
            body.strip() if body and body.strip() else "The author left no description.",
            "# The conversation on this pull request",
            render_conversation(conversation),
            "# The change under review",
            "The diff between the merge base and the head commit follows, whole. It is the "
            "subject of the review; the checkout holds every file at the head commit.",
            diff,
        ]
    )


def render_verification_request(title: str, body: str | None, diff: str, review: Review) -> str:
    """Everything the verifier is given: the pull request, the change, and the findings to rule on.

    The conversation is deliberately absent. The verifier judges each claim against the code, and
    a finding a comment talked into existence should face somebody who never read that comment.
    """
    findings = []
    for index, finding in enumerate(review.findings):
        test = finding.regression_test
        if test is None:
            evidence = "The reviewer could not reproduce this with a test; it is speculative."
        else:
            evidence = "\n\n".join(
                [
                    f"The reviewer's test is `{test.path}`, run with `{test.command}`:",
                    f"```\n{test.content}\n```",
                ]
            )
        findings.append(
            "\n\n".join(
                [
                    f"## Finding {index}",
                    f"Severity: {finding.severity}. Concerns {where(finding.anchor)}.",
                    finding.body,
                    evidence,
                ]
            )
        )

    return "\n\n".join(
        [
            f"# {title}",
            body.strip() if body and body.strip() else "The author left no description.",
            "# The change under review",
            "The diff between the merge base and the head commit follows, whole. The checkout "
            "holds every file at the head commit, with nothing the reviewer wrote still in it.",
            diff,
            "# The findings to rule on",
            *(findings or ["None."]),
        ]
    )


def review() -> None:
    """Review the checked-out change, verify what it found, and post what survives."""
    # The budget runs from the top of the step, so everything below is spent out of it.
    deadline = start()

    # Popped rather than read, and both before any other work, so no later code that assembles a
    # child environment out of `os.environ` can pick either up by accident.
    github = GitHub(token=os.environ.pop("GITHUB_TOKEN"))
    api_key = os.environ.pop("OPENROUTER_API_KEY")

    pull_request = json.loads(runner.pull_request_path().read_text())
    owner = pull_request["base"]["repo"]["owner"]["login"]
    repo = pull_request["base"]["repo"]["name"]
    number = pull_request["number"]
    head = pull_request["head"]["sha"]
    base = pull_request["base"]["sha"]

    # Everything from here down is inside the failure path. Above it are the two credentials and
    # the pull request off disk, and a failure there leaves this step without the client or the
    # commit it would post with — which is the report step's to cover, and it does.
    try:
        conversation = read_conversation(runner.conversation_path())
        workspace = runner.workspace()
        # The merge base is hoisted out of the diff call so the lines an anchor is checked against
        # come from the same diff the agent read.
        common = merge_base(workspace, base, head)
        diff = diff_text(workspace, common, head)
        added = set(added_lines(workspace, common, head))
        request = render_request(pull_request["title"], pull_request["body"], diff, conversation)
        log.info("Asking the agent to review %s in %d characters.", head, len(request))

        # Deferred: importing the agent framework costs about two seconds, and `coral/cli.py`
        # imports this module to reach `review`, so `coral resolve` would pay for it on every
        # delivery.
        from coral.agent import produce_review, verify_findings

        # The reviewer gets a slice of the step rather than the whole of it, so that whatever it
        # leaves behind is time the verifier is guaranteed.
        review = produce_review(api_key, workspace, request, start(REVIEWER_BUDGET_SECONDS))

        if review.findings:
            reset(workspace)
            log.info("Asking a second agent to verify %s.", count(len(review.findings), "finding"))
            verification = verify_findings(
                api_key,
                workspace,
                render_verification_request(
                    pull_request["title"], pull_request["body"], diff, review
                ),
                deadline,
            )
            # Every verdict is logged with its reason, because the log is the only record of one: a
            # reason is never posted, and a rejected finding is never posted either.
            for index in range(len(review.findings)):
                rulings = [verdict for verdict in verification.verdicts if verdict.finding == index]
                if not rulings:
                    log.info("Finding %d dropped: no verdict named it.", index)
                for ruling in rulings:
                    outcome = "confirmed" if ruling.confirmed else "dropped"
                    log.info("Finding %d %s: %s", index, outcome, ruling.reason)
            review = confirmed(review, verification)

        # Resolve's check was minutes and two agent runs ago, and a review landing after the merge
        # is advice nobody can act on.
        if not is_open(github, owner, repo, number):
            log.info("Pull request %d is no longer open; posting nothing.", number)
            return

        post_review(github, owner, repo, number, head, review, added)
    except Exception as error:
        log.exception("The review failed; reporting it on the pull request.")
        post_comment(
            github, owner, repo, number, head, failure_comment(described(error), runner.run_url())
        )
        # Written after the post, so a post that fails leaves the comment still owed and the report
        # step still covering it. The file exists only when a comment landed.
        runner.reported_path().write_text("")
        # Re-raised: a run that could not review is red.
        raise
