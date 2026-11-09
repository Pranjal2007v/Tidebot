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


class Metrics:
    def __init__(self, store: StateStore):
        self.store = store

    def record_wait(self, repo: str, seconds: float) -> None:
        """Note how long one AI job in ``repo`` waited in the queue."""
        if not repo:
            return
        data = dict(self.store.get(METRICS_KEY) or {})
        entry = dict(data.get(repo, {}))
        waits = list(entry.get("queue_waits", []))
        waits.append(round(max(seconds, 0.0), 1))
        entry["queue_waits"] = waits[-MAX_WAITS:]
        data[repo] = entry
        self.store.set(METRICS_KEY, data)

    def report(self, repo: str) -> Dict[str, Any]:
        counts = (self.store.get(STATS_KEY) or {}).get(repo, {})
        waits = (self.store.get(METRICS_KEY) or {}).get(repo, {}).get("queue_waits", [])
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
        }
