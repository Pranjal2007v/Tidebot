"""Find open issues that a new issue may duplicate.

This is the first step of the duplicate check in the README's Automatic
behavior section: TF-IDF vectors over the titles and bodies of the open
issues, compared by cosine similarity. Titles count twice, since they say
the most in the fewest words. Matches at or above ``THRESHOLD`` are reported.
Scores between ``BORDERLINE`` and ``THRESHOLD`` go to the AI check when a
model is configured: the model reads both issues and only the pairs it
calls the same report are added.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Dict, Iterable, List, Optional, Tuple

from .ai import AIClient, AIError

THRESHOLD = 0.5
BORDERLINE = 0.3
# Most matches to list in one reply.
MAX_MATCHES = 3
# Characters of each issue the AI check reads.
_AI_CONTEXT = 2000

_WORD = re.compile(r"[a-z0-9][a-z0-9_.-]*[a-z0-9]|[a-z0-9]")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_STOPWORDS = frozenset("""
a about after all also am an and any are as at be because been but by can could did do
does doing for from get got had has have how i if in into is it its just like me more my
no not of on or our out please so some than that the their them then there these they
this to too up us use using was we were what when where which while who why will with
would you your
""".split())


@dataclass(frozen=True)
class Match:
    number: int
    title: str
    score: float
    # True when the AI check confirmed a borderline score.
    checked: bool = False


def tokens(title: Optional[str], body: Optional[str]) -> List[str]:
    text = f"{title or ''}\n{title or ''}\n{_HTML_COMMENT.sub('', body or '')}".lower()
    return [w for w in _WORD.findall(text) if w not in _STOPWORDS and len(w) > 1]


def _vectors(docs: List[List[str]]) -> List[Dict[str, float]]:
    df: Counter = Counter()
    for doc in docs:
        df.update(set(doc))
    n = len(docs)
    vectors = []
    for doc in docs:
        tf = Counter(doc)
        vec = {w: c * (math.log((1 + n) / (1 + df[w])) + 1) for w, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vectors.append({w: v / norm for w, v in vec.items()})
    return vectors


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(w, 0.0) for w, v in a.items())


def find_duplicates(issue: dict, open_issues: Iterable[dict],
                    threshold: float = THRESHOLD) -> List[Match]:
    """Open issues that score at least ``threshold`` against ``issue``, best first."""
    return _scored(issue, open_issues, threshold)[:MAX_MATCHES]


def split_matches(issue: dict, open_issues: Iterable[dict]) -> Tuple[List[Match], List[Match]]:
    """Clear matches and borderline ones for the AI check, best first."""
    matches = _scored(issue, open_issues, BORDERLINE)
    strong = [m for m in matches if m.score >= THRESHOLD][:MAX_MATCHES]
    borderline = [m for m in matches if m.score < THRESHOLD][:MAX_MATCHES]
    return strong, borderline


def _scored(issue: dict, open_issues: Iterable[dict], threshold: float) -> List[Match]:
    new = tokens(issue.get("title"), issue.get("body"))
    if not new:
        return []
    others = [o for o in open_issues
              if o.get("number") != issue.get("number") and "pull_request" not in o]
    docs = [new] + [tokens(o.get("title"), o.get("body")) for o in others]
    vectors = _vectors(docs)
    matches = [Match(o["number"], o.get("title") or "", _cosine(vectors[0], vec))
               for o, vec in zip(others, vectors[1:])]
    matches = [m for m in matches if m.score >= threshold]
    matches.sort(key=lambda m: (-m.score, m.number))
    return matches


def _describe(label: str, issue: dict) -> str:
    body = (_HTML_COMMENT.sub("", issue.get("body") or "")).strip()[:_AI_CONTEXT]
    return f"Issue {label}: {issue.get('title') or ''}\n{body}"


def same_report(ai: AIClient, issue: dict, other: dict) -> bool:
    """Ask the model whether two issues report the same thing; errors count as no."""
    try:
        answer = ai.ask("You compare GitHub issues. Answer with only yes or no.",
                        "Do these two issues report the same problem or ask for the same "
                        f"change?\n\n{_describe('A', issue)}\n\n{_describe('B', other)}",
                        max_tokens=5, temperature=0)
    except AIError as err:
        print(f"tidebot: AI duplicate check failed: {err}")
        return False
    return answer.strip().lower().startswith("yes")


def confirm_borderline(ai: AIClient, issue: dict, open_issues: Iterable[dict],
                       strong: List[Match], borderline: List[Match]) -> List[Match]:
    """``strong`` plus the borderline matches the model confirms, best first."""
    by_number = {o.get("number"): o for o in open_issues}
    confirmed = [replace(m, checked=True) for m in borderline
                 if m.number in by_number and same_report(ai, issue, by_number[m.number])]
    matches = sorted(strong + confirmed, key=lambda m: (-m.score, m.number))
    return matches[:MAX_MATCHES]


def duplicates_comment(matches: List[Match]) -> Optional[str]:
    if not matches:
        return None
    lines = ["This issue looks similar to:", ""]
    lines += [f"- #{m.number} {m.title} ({round(m.score * 100)}% similar"
              f"{', confirmed by the AI check' if m.checked else ''})" for m in matches]
    lines += ["", "If one of these is the same problem, a maintainer can close this one "
                  "with `:tide /duplicate #N`."]
    return "\n".join(lines)
