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
from .router import is_bot


def pull_request_opened(gh: GitHubClient, repo: str, pr: dict, config: TideConfig) -> None:
    """Welcome the author of a new PR with the command list."""
    author = (pr.get("user") or {}).get("login", "")
    if is_bot(author):
        return
    parts: List[str] = [welcome_text(author)]
    gh.post_comment(repo, pr["number"], "\n\n".join(parts))
