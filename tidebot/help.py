"""Build the ``/help`` reply.

The reply lists only the commands the caller's tier may run, grouped the
same way as the README's Commands section.
"""

from __future__ import annotations

from typing import Optional

from .commands import AI_COMMANDS, COMMUNITY_COMMANDS, WORKFLOW_COMMANDS, Command, TRIGGER
from .permissions import Tier, required_tier, tier_for

_GROUPS = (
    ("AI", AI_COMMANDS),
    ("Workflow", WORKFLOW_COMMANDS),
    ("Community", COMMUNITY_COMMANDS),
)


def help_text(author: str, permission: Optional[str]) -> str:
    tier = tier_for(permission)
    lines = [f"Commands you can run here ({tier.name.lower()} access). "
             f"Start a line with `{TRIGGER}`, for example `{TRIGGER} /ask where is auth handled?`.", ""]
    for title, names in _GROUPS:
        allowed = sorted(n for n in names if required_tier(Command(n), author) <= tier)
        if allowed:
            lines.append(f"**{title}:** " + ", ".join(f"`/{n}`" for n in allowed))
    if tier < Tier.MAINTAINER:
        lines += ["", "Other commands need more access to the repo."]
    return "\n".join(lines)
