"""Per-repo numbers for the dashboard.

The README's Website section plans a dashboard with commands run, queue wait
times, reviews posted and duplicates caught for each repo. ``Metrics`` keeps
the numbers the bot measures itself in the state file, and ``report`` puts
them together with the command counts ``/stats`` already keeps.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict

from .community import STATS_KEY
from .state import StateStore

METRICS_KEY = "metrics"
# Only the most recent waits are kept, so the state file stays small.
MAX_WAITS = 200
# Commands whose reply is a code review of a PR, for the "reviews posted" count.
REVIEW_COMMANDS = ("review", "review-sc", "security", "perf", "docs")


class Metrics:
    def __init__(self, store: StateStore):
        self.store = store

    def _update(self, repo: str, change) -> None:
        data = dict(self.store.get(METRICS_KEY) or {})
        entry = dict(data.get(repo, {}))
        change(entry)
        data[repo] = entry
        self.store.set(METRICS_KEY, data)

    def record_wait(self, repo: str, seconds: float) -> None:
        """Note how long one AI job in ``repo`` waited in the queue."""
        if not repo:
            return

        def change(entry):
            waits = list(entry.get("queue_waits", []))
            waits.append(round(max(seconds, 0.0), 1))
            entry["queue_waits"] = waits[-MAX_WAITS:]

        self._update(repo, change)

    def record_reply(self, repo: str, command: str) -> None:
        """Note that an AI command's answer went out; only reviews are counted."""
        if not repo or command not in REVIEW_COMMANDS:
            return

        def change(entry):
            reviews = dict(entry.get("reviews", {}))
            reviews[command] = reviews.get(command, 0) + 1
            entry["reviews"] = reviews

        self._update(repo, change)

    def record_duplicates(self, repo: str, number: int) -> None:
        """Note that issue ``number`` got a duplicates comment."""
        if not repo:
            return

        def change(entry):
            entry["duplicates"] = entry.get("duplicates", 0) + 1

        self._update(repo, change)

    def report(self, repo: str) -> Dict[str, Any]:
        counts = (self.store.get(STATS_KEY) or {}).get(repo, {})
        entry = (self.store.get(METRICS_KEY) or {}).get(repo, {})
        waits = entry.get("queue_waits", [])
        reviews = entry.get("reviews", {})
        return {
            "repo": repo,
            "commands": {
                "total": sum(counts.values()),
                "by_command": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
            },
            "queue": {
                "jobs": len(waits),
                "median_wait": statistics.median(waits) if waits else None,
                "max_wait": max(waits) if waits else None,
            },
            "reviews": {
                "total": sum(reviews.values()),
                "by_command": {name: reviews[name] for name in REVIEW_COMMANDS
                               if reviews.get(name)},
            },
            "duplicates_caught": entry.get("duplicates", 0),
        }
