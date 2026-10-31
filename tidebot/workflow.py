"""Carry out workflow commands through the GitHub API.

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
_ISSUE_REF = re.compile(r"^#?(\d+)$")
# Reasons GitHub accepts when locking a conversation.
_LOCK_REASONS = {"off-topic", "too heated", "resolved", "spam"}


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


def _retitle(gh: GitHubClient, t: Target, args: str) -> Optional[str]:
    title = args.strip()
    if not title:
        return "Usage: `:tide /retitle New title`."
    gh.set_title(t.repo, t.number, title)
    return None


def _lock(gh: GitHubClient, t: Target, args: str) -> Optional[str]:
    reason = " ".join(_words(args)).lower()
    if reason == "cancel":
        gh.unlock(t.repo, t.number)
        return None
    if reason and reason not in _LOCK_REASONS:
        return "Lock reasons are " + ", ".join(f"`{r}`" for r in sorted(_LOCK_REASONS)) + "."
    gh.lock(t.repo, t.number, reason or None)
    return None


def _milestone(gh: GitHubClient, t: Target, args: str) -> Optional[str]:
    title = args.strip()
    if not title:
        return "Usage: `:tide /milestone v1.0`, or `/milestone clear`."
    if title.lower() == "clear":
        gh.set_milestone(t.repo, t.number, None)
        return None
    number = gh.find_milestone(t.repo, title)
    if number is None:
        return f"There is no open milestone called `{title}`."
    gh.set_milestone(t.repo, t.number, number)
    return None


def _duplicate(gh: GitHubClient, t: Target, args: str) -> Optional[str]:
    words = _words(args)
    match = _ISSUE_REF.match(words[0]) if words else None
    if not match:
        return "Usage: `:tide /duplicate #123`."
    original = int(match.group(1))
    if original == t.number:
        return "An issue can't be a duplicate of itself."
    gh.add_labels(t.repo, t.number, ["duplicate"])
    gh.set_state(t.repo, t.number, "closed")
    # GitHub links the two when a comment says "Duplicate of #N".
    return f"Duplicate of #{original}"


Handler = Callable[[GitHubClient, Target, str], Optional[str]]

# Labels that stand for a reviewer's verdict or a merge blocker.
LGTM_LABEL = "lgtm"
HOLD_LABEL = "do-not-merge/hold"
WIP_LABEL = "do-not-merge/wip"


def _cancelled(args: str) -> bool:
    return [w.lower() for w in _words(args)][:1] == ["cancel"]


def _toggle_label(label: str) -> Handler:
    """Add ``label``, or remove it when the args start with ``cancel``."""
    def handler(gh: GitHubClient, t: Target, args: str) -> Optional[str]:
        if _cancelled(args):
            gh.remove_label(t.repo, t.number, label)
        else:
            gh.add_labels(t.repo, t.number, [label])
        return None
    return handler


def _lgtm(gh: GitHubClient, t: Target, args: str) -> Optional[str]:
    if not t.is_pr:
        return "`/lgtm` only works on pull requests."
    return _toggle_label(LGTM_LABEL)(gh, t, args)


def _approve(gh: GitHubClient, t: Target, args: str) -> Optional[str]:
    if not t.is_pr:
        return "`/approve` only works on pull requests."
    gh.approve(t.repo, t.number, f"Approved by @{t.author} with `/approve`.")
    return None


_MERGE_METHODS = {"merge", "squash", "rebase"}


def merge_blockers(gh: GitHubClient, t: Target, pr: dict) -> List[str]:
    """List what stops ``pr`` from merging; empty means it can go in."""
    blockers = []
    if pr.get("state") != "open":
        blockers.append("it is not open")
    if pr.get("draft"):
        blockers.append("it is a draft")
    labels = {label.get("name") for label in pr.get("labels", [])}
    for label in sorted(labels & {HOLD_LABEL, WIP_LABEL}):
        blockers.append(f"it has the `{label}` label")
    if pr.get("mergeable") is False:
        blockers.append("it has merge conflicts")
    reviews = gh.review_states(t.repo, t.number).values()
    if "CHANGES_REQUESTED" in reviews:
        blockers.append("a reviewer requested changes")
    elif "APPROVED" not in reviews:
        blockers.append("it has no approval")
    ci = gh.ci_state(t.repo, pr["head"]["sha"])
    if ci != "success":
        blockers.append({"none": "no CI has reported on it",
                         "pending": "CI is still running",
                         "failure": "CI is failing"}[ci])
    return blockers


def _merge(gh: GitHubClient, t: Target, args: str) -> Optional[str]:
    if not t.is_pr:
        return "`/merge` only works on pull requests."
    words = [w.lower() for w in _words(args)]
    method = words[0] if words else "merge"
    if method not in _MERGE_METHODS:
        return "Usage: `:tide /merge`, `/merge squash` or `/merge rebase`."
    pr = gh.pull(t.repo, t.number)
    blockers = merge_blockers(gh, t, pr)
    if blockers:
        return "Not merging: " + "; ".join(blockers) + "."
    gh.merge(t.repo, t.number, pr["head"]["sha"], method)
    return None


HANDLERS: Dict[str, Handler] = {
    "label": _label,
    "close": _close,
    "reopen": _reopen,
    "assign": _assign,
    "cc": _cc,
    "retitle": _retitle,
    "lock": _lock,
    "milestone": _milestone,
    "duplicate": _duplicate,
    "lgtm": _lgtm,
    "hold": _toggle_label(HOLD_LABEL),
    "wip": _toggle_label(WIP_LABEL),
    "approve": _approve,
    "merge": _merge,
}


def run_command(gh: GitHubClient, target: Target, command: Command) -> Optional[str]:
    """Run ``command`` if it has a handler; return the reply text, if any."""
    handler = HANDLERS.get(command.name)
    if handler is None:
        return None
    return handler(gh, target, command.args)
