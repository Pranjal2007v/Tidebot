"""Size labels for pull requests.

A PR's size is the number of lines it adds plus the lines it removes. The
buckets follow the ones Kubernetes' Prow uses, stopping at ``size/XL`` as
the README's Automatic behavior section does.
"""

from __future__ import annotations

from typing import Iterable, List

PREFIX = "size/"
# (label, smallest line count that gets it), largest first.
_BUCKETS = (("XL", 500), ("L", 100), ("M", 30), ("S", 10), ("XS", 0))
LABELS = tuple(PREFIX + name for name, _ in _BUCKETS)


def size_label(lines: int) -> str:
    for name, smallest in _BUCKETS:
        if lines >= smallest:
            return PREFIX + name
    return PREFIX + "XS"


def changed_lines(pr: dict) -> int:
    return int(pr.get("additions", 0)) + int(pr.get("deletions", 0))


def stale_labels(current: Iterable[str], wanted: str) -> List[str]:
    """Size labels on the PR that should go now that it is ``wanted``."""
    return sorted(name for name in current if name in LABELS and name != wanted)
