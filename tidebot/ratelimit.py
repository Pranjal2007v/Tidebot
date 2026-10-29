"""Limit how many commands a user and a repo may run per hour.

The limits come from the README's Permissions section: 10 commands per hour
per user and 50 per repo, counted over a sliding one-hour window. A user's
count is kept per repo, so being busy in one repo doesn't block them in
another.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List

from .state import StateStore

STATE_KEY = "rate_limits"
WINDOW_SECONDS = 3600
PER_USER = 10
PER_REPO = 50


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    retry_after: int = 0  # seconds until the next command would be allowed


class RateLimiter:
    def __init__(self, store: StateStore, per_user: int = PER_USER, per_repo: int = PER_REPO,
                 window: int = WINDOW_SECONDS, clock: Callable[[], float] = time.time):
        self.store = store
        self.per_user = per_user
        self.per_repo = per_repo
        self.window = window
        self.clock = clock

    def _buckets(self) -> Dict[str, Dict[str, List[float]]]:
        data = self.store.get(STATE_KEY) or {}
        return {"users": dict(data.get("users", {})), "repos": dict(data.get("repos", {}))}

    def _recent(self, stamps: List[float], now: float) -> List[float]:
        return [t for t in stamps if now - t < self.window]

    def _wait(self, stamps: List[float], limit: int, now: float) -> int:
        if len(stamps) < limit:
            return 0
        oldest = sorted(stamps)[-limit]
        return max(1, int(oldest + self.window - now + 0.999))

    def hit(self, repo: str, user: str) -> Verdict:
        """Count one command by ``user`` in ``repo`` if both are under their limits."""
        now = self.clock()
        buckets = self._buckets()
        user_key = f"{repo}:{user.lower()}"
        users = {k: r for k, v in buckets["users"].items() if (r := self._recent(v, now))}
        repos = {k: r for k, v in buckets["repos"].items() if (r := self._recent(v, now))}
        user_stamps = users.get(user_key, [])
        repo_stamps = repos.get(repo, [])

        wait = max(self._wait(user_stamps, self.per_user, now),
                   self._wait(repo_stamps, self.per_repo, now))
        if not wait:
            users[user_key] = user_stamps + [now]
            repos[repo] = repo_stamps + [now]
        self.store.set(STATE_KEY, {"users": users, "repos": repos})
        return Verdict(not wait, wait)
