"""Save ``/remind`` requests and post them when they are due.

A reminder is written as ``:tide /remind 2h check the flaky test``. The
delay is one or more ``<number><unit>`` parts with units m, h, d and w, so
``1h30m`` works too. Reminders are kept in ``state.json`` with the App
installation they came from, so they survive a restart and can be posted
with the right token later.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from typing import Callable, List, Optional, Tuple

from .github import GitHubClient, GitHubError

STATE_KEY = "reminders"
MIN_DELAY = 60
MAX_DELAY = 30 * 24 * 3600

_UNITS = {"m": 60, "h": 3600, "d": 86400, "w": 7 * 86400}
_DELAY = re.compile(r"^((?:\d+[mhdw])+)(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)
_PART = re.compile(r"(\d+)([mhdw])", re.IGNORECASE)


@dataclass(frozen=True)
class Reminder:
    repo: str
    number: int
    installation: int
    author: str
    due: float
    text: str = ""

    def message(self) -> str:
        if self.text:
            return f"@{self.author}, you asked me to remind you: {self.text}"
        return f"@{self.author}, here is the reminder you asked for."


def parse_delay(args: str) -> Optional[Tuple[int, str]]:
    """Split ``2h check CI`` into ``(7200, "check CI")``; None if it doesn't start with a delay."""
    match = _DELAY.match(args.strip())
    if not match:
        return None
    seconds = sum(int(n) * _UNITS[u.lower()] for n, u in _PART.findall(match.group(1)))
    return seconds, (match.group(2) or "").strip()


def describe(seconds: int) -> str:
    """Write a delay back out the way people type it, largest units first."""
    parts = []
    for unit, size in (("w", _UNITS["w"]), ("d", _UNITS["d"]), ("h", _UNITS["h"]),
                       ("m", _UNITS["m"])):
        count, seconds = divmod(seconds, size)
        if count:
            parts.append(f"{count}{unit}")
    return "".join(parts) or "0m"


class Reminders:
    def __init__(self, store, clock: Callable[[], float] = time.time):
        self.store = store
        self.clock = clock

    def _all(self) -> List[Reminder]:
        return [Reminder(**r) for r in self.store.get(STATE_KEY) or []]

    def _save(self, reminders: List[Reminder]) -> None:
        self.store.set(STATE_KEY, [asdict(r) for r in reminders])

    def add(self, repo: str, number: int, installation: int, author: str,
            delay: int, text: str) -> Reminder:
        reminder = Reminder(repo, number, installation, author, self.clock() + delay, text)
        self._save(self._all() + [reminder])
        return reminder

    def pending(self, repo: Optional[str] = None) -> List[Reminder]:
        return [r for r in self._all() if repo is None or r.repo == repo]

    def drop_installation(self, installation: int) -> int:
        """Forget every reminder from ``installation`` and return how many there were.

        Run when the App is uninstalled: its token is gone, so they could
        never be posted.
        """
        reminders = self._all()
        keep = [r for r in reminders if r.installation != installation]
        if len(keep) != len(reminders):
            self._save(keep)
        return len(reminders) - len(keep)

    def deliver_due(self, github: Callable[[int], GitHubClient]) -> int:
        """Post every reminder that is due and return how many were posted.

        A reminder whose post fails with a server error or rate limit stays
        for the next round. Other failures, like a deleted issue or a removed
        installation, would fail forever, so those reminders are dropped.
        """
        now = self.clock()
        keep, sent = [], 0
        for reminder in self._all():
            if reminder.due > now:
                keep.append(reminder)
                continue
            try:
                github(reminder.installation).post_comment(
                    reminder.repo, reminder.number, reminder.message())
                sent += 1
            except GitHubError as err:
                if err.status >= 500 or err.status == 429:
                    keep.append(reminder)
        self._save(keep)
        return sent
