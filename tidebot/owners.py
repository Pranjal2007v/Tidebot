"""Match changed files to the people who own that code area.

Rules come from a ``reviewers`` section in ``.tide.yml`` or from the repo's
CODEOWNERS file. Patterns follow CODEOWNERS (gitignore) syntax: a pattern
with no slash matches a name at any depth, a leading or inner slash anchors
it to the repo root, a trailing slash means a directory, ``*`` stays inside
one path segment and ``**`` crosses them. As in CODEOWNERS, the last rule
that matches a file wins, and a rule with no owners leaves the file unowned.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence, Tuple

# (pattern, owners) in file order; owners keep their leading "@".
Rule = Tuple[str, Tuple[str, ...]]
# Where GitHub looks for CODEOWNERS, in the order it checks them.
CODEOWNERS_PATHS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")


def parse_codeowners(text: Optional[str]) -> List[Rule]:
    """Read CODEOWNERS lines; email owners are skipped, since reviews need logins."""
    rules: List[Rule] = []
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        pattern, *owners = line.split()
        rules.append((pattern, tuple(o for o in owners if o.startswith("@"))))
    return rules


def _compile(pattern: str) -> "re.Pattern[str]":
    directory = pattern.endswith("/")
    anchored = pattern.startswith("/") or "/" in pattern.strip("/")
    body = ""
    rest = pattern.strip("/")
    while rest:
        if rest.startswith("**/"):
            body, rest = body + "(?:.*/)?", rest[3:]
        elif rest.startswith("**"):
            body, rest = body + ".*", rest[2:]
        elif rest[0] == "*":
            body, rest = body + "[^/]*", rest[1:]
        elif rest[0] == "?":
            body, rest = body + "[^/]", rest[1:]
        else:
            body, rest = body + re.escape(rest[0]), rest[1:]
    prefix = "" if anchored else "(?:.*/)?"
    # A pattern naming a directory also covers everything under it, except
    # ``dir/*``, which CODEOWNERS limits to the files directly in ``dir``.
    if directory:
        suffix = "/.*"
    elif pattern.endswith("/*") and not pattern.endswith("**/*"):
        suffix = ""
    else:
        suffix = "(?:/.*)?"
    return re.compile(f"^{prefix}{body}{suffix}$")


def owners_of(rules: Sequence[Rule], path: str) -> Tuple[str, ...]:
    for pattern, owners in reversed(rules):
        if _compile(pattern).match(path.lstrip("/")):
            return owners
    return ()


def owners_for(rules: Sequence[Rule], paths: Iterable[str]) -> List[str]:
    """Owners of any of ``paths``, each once, in the order they first come up."""
    seen: List[str] = []
    for path in paths:
        for owner in owners_of(rules, path):
            if owner.lower() not in (s.lower() for s in seen):
                seen.append(owner)
    return seen


def split_reviewers(owners: Iterable[str], author: str) -> Tuple[List[str], List[str]]:
    """Turn owners into (user logins, team slugs) to request, leaving out the author.

    ``@org/team`` names a team, which the review API takes by slug alone.
    """
    users: List[str] = []
    teams: List[str] = []
    for owner in owners:
        name = owner.lstrip("@")
        if "/" in name:
            teams.append(name.split("/", 1)[1])
        elif name and name.lower() != author.lower():
            users.append(name)
    return users, teams
