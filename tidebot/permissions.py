"""Decide who may run which command.

The tiers follow the README's Permissions section. A user's tier comes from
their GitHub permission level on the repo. Commands the README doesn't place
in a tier are placed by how much harm they can do: anything that changes the
state of an issue or PR needs a maintainer, harmless fun is open to anyone.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from .commands import AI_COMMANDS, Command


class Tier(IntEnum):
    ANYONE = 0
    COLLABORATOR = 1
    MAINTAINER = 2


# GitHub's collaborator permission levels, as returned by
# GET /repos/{owner}/{repo}/collaborators/{username}/permission.
_PERMISSION_TIERS = {
    "admin": Tier.MAINTAINER,
    "maintain": Tier.MAINTAINER,
    "write": Tier.MAINTAINER,
    "triage": Tier.COLLABORATOR,
}

_COMMAND_TIERS = {
    **{name: Tier.ANYONE for name in AI_COMMANDS},
    "stats": Tier.ANYONE,
    "help": Tier.ANYONE,
    "kudos": Tier.ANYONE,
    "size": Tier.ANYONE,
    "ping": Tier.ANYONE,
    "joke": Tier.ANYONE,
    "lgtm": Tier.COLLABORATOR,
    "hold": Tier.COLLABORATOR,
    "wip": Tier.COLLABORATOR,
    "remind": Tier.COLLABORATOR,
    "vote": Tier.COLLABORATOR,
    "cc": Tier.COLLABORATOR,
    "merge": Tier.MAINTAINER,
    "approve": Tier.MAINTAINER,
    "close": Tier.MAINTAINER,
    "reopen": Tier.MAINTAINER,
    "retitle": Tier.MAINTAINER,
    "duplicate": Tier.MAINTAINER,
    "label": Tier.MAINTAINER,
    "lock": Tier.MAINTAINER,
    "milestone": Tier.MAINTAINER,
    "ship": Tier.MAINTAINER,
}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""


def tier_for(permission: Optional[str]) -> Tier:
    """Map a GitHub permission level (``admin``, ``triage``, ...) to a tier."""
    return _PERMISSION_TIERS.get((permission or "").lower(), Tier.ANYONE)


def _is_self_assign(args: str, author: str) -> bool:
    targets = [t.lstrip("@").lower() for t in args.split()]
    return all(t in ("me", author.lower()) for t in targets)


def required_tier(command: Command, author: str) -> Tier:
    """Return the lowest tier that may run ``command``.

    ``/assign`` with no target, ``@me`` or the author's own login is a
    self-assign and only needs a collaborator; assigning anyone else needs a
    maintainer.
    """
    if command.name == "assign":
        return Tier.COLLABORATOR if _is_self_assign(command.args, author) else Tier.MAINTAINER
    return _COMMAND_TIERS.get(command.name, Tier.MAINTAINER)


def check(command: Command, author: str, permission: Optional[str],
          starred: bool = False, star_gate: bool = False) -> Decision:
    """Decide whether ``author`` may run ``command``.

    With ``star_gate`` on, people below collaborator must have starred the
    repo to use the commands open to anyone.
    """
    if not command.known:
        return Decision(False, f"unknown command /{command.name}")
    tier = tier_for(permission)
    needed = required_tier(command, author)
    if tier < needed:
        return Decision(False, f"/{command.name} needs {needed.name.lower()} access")
    if star_gate and tier == Tier.ANYONE and not starred:
        return Decision(False, "star the repo to use Tidebot here")
    return Decision(True)
