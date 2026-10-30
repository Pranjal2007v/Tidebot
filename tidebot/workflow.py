"""Carry out the first workflow commands through the GitHub API.

The router has already checked permission and rate limits, so these
handlers only do the work. Each returns the text to reply with, or None
when the change on the issue speaks for itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .commands import Command
from .github import GitHubClient

_SPLIT = re.compile(r"[\s,]+")


@dataclass(frozen=True)
class Target:
    """The issue or PR a command was written on."""
    repo: str
    number: int
    is_pr: bool
    author: str


def _words(args: str) -> List[str]:
    return [w for w in _SPLIT.split(args.strip()) if w]


def _logins(args: str, author: str) -> List[str]:
    """Turn ``@alice bob me`` into logins; no args means the author."""
    names = [w.lstrip("@") for w in _words(args)] or ["me"]
    return [author if n.lower() == "me" else n for n in names]


def _label(gh: GitHubClient, t: Target, args: str) -> Optional[str]:
    words = _words(args)
    if not words:
        return "Usage: `:tide /label bug docs`, or `-bug` to remove a label."
    add = [w for w in words if not w.startswith("-")]
    remove = [w[1:] for w in words if w.startswith("-") and len(w) > 1]
    if add:
        gh.add_labels(t.repo, t.number, add)
    for name in remove:
        gh.remove_label(t.repo, t.number, name)
    return None


def _close(gh: GitHubClient, t: Target, args: str) -> Optional[str]:
    gh.set_state(t.repo, t.number, "closed")
    return None


def _reopen(gh: GitHubClient, t: Target, args: str) -> Optional[str]:
    gh.set_state(t.repo, t.number, "open")
    return None


def _assign(gh: GitHubClient, t: Target, args: str) -> Optional[str]:
    gh.add_assignees(t.repo, t.number, _logins(args, t.author))
    return None


def _cc(gh: GitHubClient, t: Target, args: str) -> Optional[str]:
    logins = [w.lstrip("@") for w in _words(args)]
    if not logins:
        return "Usage: `:tide /cc @someone`."
    if t.is_pr:
        # Asking for a review on a PR notifies them and shows up in their queue.
        gh.request_reviewers(t.repo, t.number, logins)
        return None
    return "cc " + " ".join("@" + name for name in logins)


Handler = Callable[[GitHubClient, Target, str], Optional[str]]

HANDLERS: Dict[str, Handler] = {
    "label": _label,
    "close": _close,
    "reopen": _reopen,
    "assign": _assign,
    "cc": _cc,
}


def run_command(gh: GitHubClient, target: Target, command: Command) -> Optional[str]:
    """Run ``command`` if it has a handler; return the reply text, if any."""
    handler = HANDLERS.get(command.name)
    if handler is None:
        return None
    return handler(gh, target, command.args)
