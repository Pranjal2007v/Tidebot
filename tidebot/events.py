"""Automatic behavior when a pull request or issue opens.

These handlers run on the ``pull_request`` and ``issues`` webhooks, not on
commands, so they follow the repo's ``.tide.yml`` instead of permission
tiers. See the README's Automatic behavior section for what each one does.
"""

from __future__ import annotations

from typing import List

from .config import TideConfig
from .github import GitHubClient
from .help import welcome_text
from .lint import lint_comment, lint_pull_request
from .router import is_bot
from .size import changed_lines, size_label, stale_labels


def pull_request_opened(gh: GitHubClient, repo: str, pr: dict, config: TideConfig) -> None:
    """Welcome the author of a new PR, label its size and lint it, per the config."""
    if config.size_labels:
        label_size(gh, repo, pr)
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
