"""Label a new issue by what it says.

Runs when an issue opens and ``auto_label`` is on in ``.tide.yml``. Keyword
rules sort the issue into bug, enhancement, docs and question; words in the
title count double. An issue reads as a bug or a feature request, not both,
so the higher score wins and a tie picks neither. Tidebot only applies a
label the repo already has, trying the usual names for each kind in turn.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional

# Kind → label names to look for in the repo, in order of preference.
LABEL_NAMES = {
    "bug": ("bug", "kind/bug", "type/bug", "type: bug"),
    "enhancement": ("enhancement", "feature", "kind/feature", "type/feature",
                    "type: feature", "feature request"),
    "docs": ("documentation", "docs", "kind/documentation", "type/docs", "type: docs"),
    "question": ("question", "kind/question", "type/question", "type: question"),
}

_RULES = {
    "bug": re.compile(
        r"\b(?:bug|crash(?:es|ed|ing)?|error|exception|traceback|broken|regression"
        r"|fail(?:s|ed|ing|ure)?|doesn'?t work|does not work|not working|segfault)\b", re.I),
    "enhancement": re.compile(
        r"\b(?:feature request|feature|enhancement|add support|support for|proposal"
        r"|it would be (?:nice|great|useful)|would be (?:nice|great|useful)"
        r"|allow (?:users|us|me) to|new option|suggestion)\b", re.I),
    "docs": re.compile(
        r"\b(?:docs?|documentation|readme|typo|tutorial|docstring|guide)\b", re.I),
    "question": re.compile(
        r"\b(?:question|how (?:do|can|to|should)|is (?:it|there) a way|what is the best way)\b",
        re.I),
}
# Issue templates leave HTML comments behind; their wording isn't the reporter's.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def classify(title: Optional[str], body: Optional[str]) -> List[str]:
    """Return the kinds an issue reads as, in the order of ``LABEL_NAMES``."""
    title = title or ""
    body = _HTML_COMMENT.sub("", body or "")
    scores: Dict[str, int] = {}
    for kind, rule in _RULES.items():
        scores[kind] = 2 * len(rule.findall(title)) + len(rule.findall(body))
    if title.rstrip().endswith("?"):
        scores["question"] += 2
    bug, feature = scores["bug"], scores["enhancement"]
    scores["bug"] = bug if bug > feature else 0
    scores["enhancement"] = feature if feature > bug else 0
    return [kind for kind in LABEL_NAMES if scores[kind] > 0]


def pick_labels(kinds: Iterable[str], repo_labels: Iterable[str]) -> List[str]:
    """Map kinds to label names the repo has, matching names in any case."""
    existing = {name.lower(): name for name in repo_labels}
    picked = []
    for kind in kinds:
        for name in LABEL_NAMES[kind]:
            if name in existing:
                picked.append(existing[name])
                break
    return picked
