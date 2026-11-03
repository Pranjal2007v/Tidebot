"""Automatic behavior when a pull request or issue opens.

These handlers run on the ``pull_request`` and ``issues`` webhooks, not on
commands, so they follow the repo's ``.tide.yml`` instead of permission
tiers. See the README's Automatic behavior section for what each one does.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .config import TideConfig
from .github import GitHubClient, GitHubError
from .help import welcome_text
from .labeler import classify, pick_labels
from .lint import lint_comment, lint_pull_request
from .owners import CODEOWNERS_PATHS, Rule, owners_for, parse_codeowners, split_reviewers
from .router import is_bot
from .size import changed_lines, size_label, stale_labels

TRIAGE_LABEL = "triage"
# Ways people ask for an issue: "I'd like to work on this", "can I take
# this?", "please assign this to me".
_CLAIM = re.compile(
    r"\b(?:i'?d like to|i would like to|i want to|can i|could i|may i|i'?ll|i will|i can)"
    r"\s+(?:work on|take|pick up|handle)\s+(?:this|it)\b"
    r"|\bassign\s+(?:this|it)\s+to\s+me\b",
    re.I)


def pull_request_opened(gh: GitHubClient, repo: str, pr: dict, config: TideConfig) -> None:
    """Welcome the author of a new PR, label its size, lint it and ask for reviews."""
    if config.size_labels:
        label_size(gh, repo, pr)
    assign_reviewers(gh, repo, pr, config)
    author = (pr.get("user") or {}).get("login", "")
    if is_bot(author):
        return
    parts: List[str] = [welcome_text(author)]
    if config.pr_lint:
        notes = lint_comment(lint_pull_request(pr))
        if notes:
            parts.append(notes)
    gh.post_comment(repo, pr["number"], "\n\n".join(parts))


def pull_request_pushed(gh: GitHubClient, repo: str, pr: dict, config: TideConfig) -> None:
    """New commits change the PR's size, so relabel it."""
    if config.size_labels:
        label_size(gh, repo, pr)


def pull_request_ready(gh: GitHubClient, repo: str, pr: dict, config: TideConfig) -> None:
    """A draft marked ready for review gets the reviewers it skipped on open."""
    assign_reviewers(gh, repo, pr, config)


def reviewer_rules(gh: GitHubClient, repo: str, config: TideConfig) -> List[Rule]:
    """The ``reviewers`` map from ``.tide.yml`` if it has one, else CODEOWNERS."""
    if config.reviewers:
        return list(config.reviewers)
    for path in CODEOWNERS_PATHS:
        text = gh.fetch_file(repo, path)
        if text is not None:
            return parse_codeowners(text)
    return []


def assign_reviewers(gh: GitHubClient, repo: str, pr: dict, config: TideConfig) -> None:
    """Request reviews from the owners of the code a PR changes.

    Drafts wait until they are marked ready, as GitHub does for CODEOWNERS.
    The author and anyone already asked are left out. A refused request
    (say, an owner without access to the repo) is logged, not retried.
    """
    if pr.get("draft") or is_bot((pr.get("user") or {}).get("login", "")):
        return
    rules = reviewer_rules(gh, repo, config)
    if not any(owners for _, owners in rules):
        return
    author = (pr.get("user") or {}).get("login", "")
    users, teams = split_reviewers(owners_for(rules, gh.pull_files(repo, pr["number"])), author)
    asked = {(u.get("login") or "").lower() for u in pr.get("requested_reviewers") or []}
    asked_teams = {(t.get("slug") or "").lower() for t in pr.get("requested_teams") or []}
    users = [u for u in users if u.lower() not in asked]
    teams = [t for t in teams if t.lower() not in asked_teams]
    if not users and not teams:
        return
    try:
        gh.request_reviewers(repo, pr["number"], users, teams)
    except GitHubError as err:
        print(f"tidebot: requesting reviews on {repo}#{pr['number']} failed: {err}")


def label_size(gh: GitHubClient, repo: str, pr: dict) -> None:
    """Give the PR the size label its line count calls for, dropping any old one.

    The webhook payload already carries additions, deletions and labels, so
    this needs no extra API reads.
    """
    wanted = size_label(changed_lines(pr))
    current = [label.get("name", "") for label in pr.get("labels") or []]
    for old in stale_labels(current, wanted):
        gh.remove_label(repo, pr["number"], old)
    if wanted not in current:
        gh.add_labels(repo, pr["number"], [wanted])


def issue_opened(gh: GitHubClient, repo: str, issue: dict, config: TideConfig) -> None:
    """Label a new issue by content and mark it for triage, per the config."""
    labels: List[str] = []
    if config.triage_label:
        labels.append(TRIAGE_LABEL)
    if config.auto_label:
        labels += content_labels(gh, repo, issue)
    if labels:
        gh.add_labels(repo, issue["number"], labels)


def content_labels(gh: GitHubClient, repo: str, issue: dict) -> List[str]:
    """Labels the issue's text calls for that the repo has and the issue lacks.

    The repo's labels are only read when the text matches a rule, and an
    issue opened from a template that already set a label keeps it alone.
    """
    kinds = classify(issue.get("title"), issue.get("body"))
    if not kinds:
        return []
    current = {(label.get("name") or "").lower() for label in issue.get("labels") or []}
    return [name for name in pick_labels(kinds, gh.repo_labels(repo))
            if name.lower() not in current]


def claims_issue(body: Optional[str]) -> bool:
    """Whether a comment asks to work on the issue, ignoring quotes and code."""
    in_fence = False
    for raw in (body or "").replace("\u2019", "'").splitlines():
        line = raw.strip()
        if line.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if not in_fence and not line.startswith(">") and _CLAIM.search(line):
            return True
    return False


def claim_issue(gh: GitHubClient, repo: str, issue: dict, author: str,
                body: Optional[str]) -> Optional[str]:
    """Assign an unassigned issue to whoever asked for it; return the reply.

    Only plain issues count: a PR already has its author, and an issue with
    an assignee is taken. When GitHub refuses the assignment the comment is
    left for a maintainer to answer.
    """
    if "pull_request" in issue or issue.get("assignees") or is_bot(author):
        return None
    if not claims_issue(body):
        return None
    try:
        gh.add_assignees(repo, issue["number"], [author])
    except GitHubError as err:
        print(f"tidebot: assigning {repo}#{issue['number']} to {author} failed: {err}")
        return None
    return f"Thanks @{author}, this issue is yours now. Comment here if you get stuck."
