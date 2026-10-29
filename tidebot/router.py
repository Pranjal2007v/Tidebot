"""Turn a comment into a list of things to do.

This is the "router" step of the README's Architecture section: parse the
commands in a comment, check each against the permission tiers, then
against the rate limits. Nothing here talks to GitHub; the caller passes in
what it already knows about the author and acts on the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .commands import Command, parse_commands
from .config import TideConfig
from .permissions import check
from .ratelimit import RateLimiter


@dataclass(frozen=True)
class Action:
    command: Command
    allowed: bool
    reason: str = ""


def is_bot(login: str) -> bool:
    return login.lower().endswith("[bot]")


def route_comment(repo: str, author: str, body: Optional[str], permission: Optional[str],
                  limiter: RateLimiter, config: TideConfig = TideConfig(),
                  starred: bool = False) -> List[Action]:
    """Return one Action per command in ``body``.

    Comments from bots are skipped so Tidebot never answers itself. Only
    commands that pass the permission check count against the rate limit.
    """
    if is_bot(author):
        return []
    actions = []
    for command in parse_commands(body):
        decision = check(command, author, permission, starred=starred,
                         star_gate=config.star_gate)
        if not decision.allowed:
            actions.append(Action(command, False, decision.reason))
            continue
        verdict = limiter.hit(repo, author)
        if not verdict.allowed:
            minutes = -(-verdict.retry_after // 60)
            actions.append(Action(command, False, f"rate limited, try again in {minutes} min"))
            continue
        actions.append(Action(command, True))
    return actions
