"""Parse Tidebot commands out of comment bodies.

A command is a line that starts with the ``:tide`` trigger followed by a
slash command, for example ``:tide /ask where is auth handled?``. A bare
``/lgtm`` on its own line also counts, like Prow. Lines inside fenced code
blocks and quoted lines (``> ...``) are ignored so that quoting someone
else's command doesn't run it again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

TRIGGER = ":tide"

AI_COMMANDS = frozenset({
    "ask", "review", "review-sc", "security", "perf", "docs", "test",
    "summarize", "explain", "changelog", "estimate", "checklist", "roast", "chat",
})
WORKFLOW_COMMANDS = frozenset({
    "assign", "label", "close", "reopen", "retitle", "duplicate", "milestone",
    "lock", "cc", "lgtm", "hold", "wip", "approve", "merge", "ship",
})
COMMUNITY_COMMANDS = frozenset({
    "vote", "kudos", "stats", "remind", "size", "ping", "joke", "help",
})
ALL_COMMANDS = AI_COMMANDS | WORKFLOW_COMMANDS | COMMUNITY_COMMANDS

# Commands that may be written without the trigger, on a line of their own.
BARE_COMMANDS = frozenset({"lgtm"})

_TRIGGERED = re.compile(r"^" + re.escape(TRIGGER) + r"\s+/([A-Za-z][\w-]*)(?:\s+(.*))?$", re.IGNORECASE)
_BARE = re.compile(r"^/([A-Za-z][\w-]*)(?:\s+(.*))?$")
_FENCE = re.compile(r"^(```|~~~)")


@dataclass(frozen=True)
class Command:
    name: str
    args: str = ""
    bare: bool = False

    @property
    def known(self) -> bool:
        return self.name in ALL_COMMANDS


def parse_commands(body: str) -> List[Command]:
    """Return every command in ``body``, in order of appearance."""
    commands: List[Command] = []
    in_fence = False
    for raw in (body or "").splitlines():
        line = raw.strip()
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or line.startswith(">"):
            continue
        match = _TRIGGERED.match(line)
        if match:
            commands.append(Command(match.group(1).lower(), (match.group(2) or "").strip()))
            continue
        match = _BARE.match(line)
        if match and match.group(1).lower() in BARE_COMMANDS:
            commands.append(Command(match.group(1).lower(), (match.group(2) or "").strip(), bare=True))
    return commands
