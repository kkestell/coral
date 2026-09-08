"""Run a code review from the command line and render it as Markdown."""

import logging
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import replace
from functools import partial
from pathlib import Path
from uuid import uuid4

from coral import container
from coral.agent import produce_review, verify_findings
from coral.deadline import Deadline, reviewer_budget, start, stop_if_expired
from coral.openrouter import ModelFacts, model_facts
from coral.progress import Table
from coral.schema import Finding, Review, apply_dispositions, finding_dispositions, where
from coral.settings import AgentSettings, Settings
from coral.spend import Ledger, stop_if_over_cap

log = logging.getLogger(__name__)


def git(workspace: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run Git without turning an ordinary non-repository into a traceback."""
    return subprocess.run(["git", *arguments], cwd=workspace, capture_output=True, text=True)


def default_scope(workspace: Path) -> str:
    """Choose the user's requested fallback scope from the current checkout."""
    inside = git(workspace, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0:
        return "Review the whole codebase."
    status = git(workspace, "status", "--porcelain", "--untracked-files=all")
    if status.returncode != 0:
        raise RuntimeError(f"`git status` failed: {status.stderr.strip() or 'no output'}")
    if status.stdout:
        return "Review all uncommitted changes, including staged, unstaged, and untracked files."
    head = git(workspace, "rev-parse", "--verify", "HEAD")
    if head.returncode == 0:
        return "Review the most recent commit."
    return "Review the whole codebase."


def copy_checkout(workspace: Path, destination: Path) -> None:
    """Copy a repository for an agent without copying Git-ignored local secrets."""
    inside = git(workspace, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0:
        shutil.copytree(workspace, destination)
        return

    cloned = subprocess.run(
        ["git", "clone", "--no-hardlinks", "--quiet", str(workspace), str(destination)],
        capture_output=True,
        text=True,
    )
    if cloned.returncode != 0:
        raise RuntimeError(f"Copying the repository failed: {cloned.stderr.strip() or 'no output'}")

    head = git(workspace, "rev-parse", "--verify", "HEAD")
    if head.returncode == 0:
        checked_out = git(destination, "checkout", "--detach", "--quiet", head.stdout.strip())
        if checked_out.returncode != 0:
            detail = checked_out.stderr.strip() or "no output"
            raise RuntimeError(f"Checking out the review commit failed: {detail}")

    listed = git(workspace, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    if listed.returncode != 0:
        raise RuntimeError(f"`git ls-files` failed: {listed.stderr.strip() or 'no output'}")
    for name in listed.stdout.split("\0"):
        if not name:
            continue
        source = workspace / name
        target = destination / name
        if not source.exists() and not source.is_symlink():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, target, symlinks=True)
        elif source.is_symlink():
            target.symlink_to(source.readlink())
        else:
            shutil.copy2(source, target)


def remove_work(work: Path) -> None:
    """Remove a temporary tree, including files an agent wrote as root."""
    if not work.exists():
        return
    try:
        shutil.rmtree(work)
    except PermissionError:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--volume",
                f"{work}:/junk",
                container.IMAGE,
                "chown",
                "--recursive",
                f"{os.getuid()}:{os.getgid()}",
                "/junk",
            ],
            capture_output=True,
        )
        shutil.rmtree(work)


def model_profiles(settings: Settings) -> dict[str, ModelFacts]:
    """Fetch each configured model profile once."""
    names = {
        *(agent.model for agent in settings.review_agents),
        settings.verification_agent.model,
    }
    return {name: model_facts(name) for name in names}


def verification_request(scope: str, reviews: list[Review]) -> str:
    """Give the verifier the scope, reviewer summaries, and one numbered finding list."""
    findings = Review(
        summary="",
        findings=[finding for review in reviews for finding in review.findings],
    )
    summaries = "\n\n".join(
        f"## Reviewer {index}\n\n{review.summary}" for index, review in enumerate(reviews, 1)
    )
    return "\n\n".join(
        [
            "# Review scope",
            scope,
            "# Reviewer summaries",
            summaries,
            "# Findings to verify",
            *(rendered_findings(findings) or ["None."]),
        ]
    )


def combined_review(reviews: list[Review]) -> Review:
    """Flatten concurrent reviewer results in configured order."""
    return Review(
        summary="\n\n".join(review.summary for review in reviews),
        findings=[finding for review in reviews for finding in review.findings],
    )


def rendered_finding_for_verifier(index: int, finding: Finding) -> str:
    """One proposed finding with the evidence the verifier must check."""
    if finding.regression_test is None:
        evidence = "The reviewer could not reproduce this with a test; it is speculative."
    else:
        test = finding.regression_test
        evidence = "\n\n".join(
            [
                f"The reviewer's test is `{test.path}`, run with `{test.command}`:",
                f"```\n{test.content}\n```",
            ]
        )
    return "\n\n".join(
        [
            f"## Finding {index}",
            f"Severity: {finding.severity}. Concerns {where(finding.anchor)}.",
            finding.body,
            evidence,
        ]
    )


def rendered_findings(review: Review) -> list[str]:
    """Number all proposed findings in verifier order."""
    return [
        rendered_finding_for_verifier(index, finding)
        for index, finding in enumerate(review.findings)
    ]


def rendered_finding(finding: Finding) -> str:
    """One verified finding as Markdown."""
    parts = [
        f"### {finding.severity.capitalize()} severity — {where(finding.anchor)}",
        finding.body,
    ]
    if finding.regression_test is None:
        parts.append("*Speculative — not reproduced by a test.*")
    else:
        test = finding.regression_test
        parts.append(
            "<details>\n"
            f"<summary>Regression test — <code>{test.path}</code></summary>\n\n"
            f"Run with `{test.command}`:\n\n"
            f"```\n{test.content}\n```\n"
            "</details>"
        )
    return "\n\n".join(parts)


def render(review: Review, spent: float) -> str:
    """Render the final verified review for stdout."""
    parts = ["# Coral code review", review.summary]
    if review.findings:
        parts.append("## Findings")
        parts.extend(rendered_finding(finding) for finding in review.findings)
    else:
        parts.append("Coral found nothing to report.")
    parts.append(f"*This review cost ${spent:.4f}.*")
    return "\n\n".join(parts)


def run_reviewer(
    work: Path,
    workspace: Path,
    run_id: str,
    scope: str,
    api_key: str,
    profiles: dict[str, ModelFacts],
    budget: float,
    ledger: Ledger,
    toolcache: Path,
    table: Table,
    index: int,
    configured: AgentSettings,
) -> Review:
    """Provision and run one independently configured reviewer.

    The row is added here rather than when the reviewer is queued, so the table names the agents
    that started: a model the configured list never reached gets no row.
    """
    name = f"coral-{run_id}-reviewer-{index}"
    try:
        checkout = work / f"reviewer-{index}"
        copy_checkout(workspace, checkout)
        container.start(name, checkout, toolcache)
        return produce_review(
            api_key,
            configured.model,
            configured.effort,
            profiles[configured.model],
            name,
            scope,
            start(budget),
            ledger,
            table.agent(configured.model),
        )
    finally:
        container.remove(name)


def gather_reviews(
    agents: list[AgentSettings],
    wanted: int,
    concurrency: int,
    deadline: Deadline,
    ledger: Ledger,
    run: Callable[[int, AgentSettings], Review],
) -> list[Review]:
    """Run reviewers concurrently until `wanted` of them produced a review, in configured order.

    A model whose reviewer fails is not tried again: the next unused model in the configured order
    takes its place, until the requested number of reviews exists or the list runs out. Running
    out is not a failure while at least one review came back, because the verifier rules on the
    findings it is given.

    A reached time budget or spend cap fails the whole run instead of falling back. Both are
    shared by every agent, so no remaining model could finish under a limit already spent.
    """
    queued = list(enumerate(agents))
    running: dict[Future[Review], int] = {}
    produced: dict[int, Review] = {}
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        while len(produced) < wanted:
            # An in-flight reviewer counts against the number still wanted, so a list longer than
            # the request is drawn on only as reviewers fail.
            while queued and len(running) < concurrency and len(running) + len(produced) < wanted:
                index, configured = queued.pop(0)
                running[pool.submit(run, index, configured)] = index
            if not running:
                break
            for future in wait(list(running), return_when=FIRST_COMPLETED).done:
                index = running.pop(future)
                try:
                    produced[index] = future.result()
                except Exception as error:
                    log.warning(
                        "The reviewer on %s failed, so Coral falls back to the next model: %s",
                        agents[index].model,
                        error,
                    )
                    stop_if_expired(deadline)
                    stop_if_over_cap(ledger)
    if not produced:
        raise RuntimeError(f"None of the {len(agents)} configured review agents produced a review.")
    if len(produced) < wanted:
        log.warning(
            "Coral ran out of configured review agents with %d of the %d reviews asked for.",
            len(produced),
            wanted,
        )
    return [produced[index] for index in sorted(produced)]


def review(workspace: Path, scope: str, settings: Settings, table: Table) -> str:
    """Run the requested reviewers concurrently, verify their findings, and return Markdown."""
    work = Path(tempfile.mkdtemp(prefix="coral-"))
    run_id = uuid4().hex[:12]
    toolcache = work / "toolcache"
    toolcache.mkdir()
    deadline = start(settings.time_budget_minutes * 60.0)
    ledger = Ledger(cap=settings.spend_cap_dollars)
    try:
        profiles = model_profiles(settings)
        reviews = gather_reviews(
            settings.review_agents,
            settings.num_reviews,
            settings.max_concurrent_reviews,
            deadline,
            ledger,
            partial(
                run_reviewer,
                work,
                workspace,
                run_id,
                scope,
                settings.openrouter_api_key,
                profiles,
                reviewer_budget(deadline.budget),
                ledger,
                toolcache,
                table,
            ),
        )

        proposed = combined_review(reviews)
        verifier = settings.verification_agent
        verifier_name = f"coral-{run_id}-verifier"
        try:
            checkout = work / "verifier"
            copy_checkout(workspace, checkout)
            container.start(verifier_name, checkout, toolcache)
            verification = verify_findings(
                settings.openrouter_api_key,
                verifier.model,
                verifier.effort,
                profiles[verifier.model],
                verifier_name,
                verification_request(scope, reviews),
                deadline,
                ledger,
                table.agent(verifier.model),
            )
        finally:
            container.remove(verifier_name)

        dispositions = finding_dispositions(proposed, verification)
        for disposition in dispositions:
            outcome = "confirmed" if disposition.kept else "dropped"
            reasons = "; ".join(verdict.reason for verdict in disposition.verdicts)
            log.info(
                "Finding %d %s: %s", disposition.finding, outcome, reasons or disposition.reason
            )
        final = apply_dispositions(proposed, dispositions)
        if verification.summary:
            final = replace(final, summary=verification.summary)
        stop_if_expired(deadline)
        stop_if_over_cap(ledger)
        return render(final, ledger.spent)
    finally:
        remove_work(work)
