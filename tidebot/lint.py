"""Lint a pull request's title and description.

Runs when a PR opens and ``pr_lint`` is on in ``.tide.yml``. The findings
are short notes for the author, added to the welcome comment; nothing here
blocks a merge.
"""

from __future__ import annotations

import re
from typing import List, Optional

TITLE_MIN = 10
TITLE_MAX = 72
DESCRIPTION_MIN = 20

# Titles GitHub fills in from the branch or file name, which say nothing
# about the change: "Update README.md", "Patch 1", "Add files via upload".
_GENERIC_TITLE = re.compile(
    r"^(update|create|delete)\s+\S+$|^patch[\s-]*\d*$|^add files via upload$", re.I)
_WIP_TITLE = re.compile(r"^\[?wip\b", re.I)
# PR templates leave HTML comments behind; they don't count as a description.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def lint_title(title: Optional[str]) -> List[str]:
    title = (title or "").strip()
    if not title:
        return ["Add a title that says what the PR changes."]
    if _WIP_TITLE.match(title):
        return ["Mark the PR as a draft or run `:tide /wip` instead of putting WIP in the title."]
    if _GENERIC_TITLE.match(title):
        return [f"\"{title}\" is the title GitHub suggested; say what the change does instead."]
    if len(title) < TITLE_MIN:
        return [f"The title is short ({len(title)} characters); say what the PR changes."]
    if len(title) > TITLE_MAX:
        return [f"Keep the title under {TITLE_MAX} characters (it has {len(title)})."]
    return []


def lint_description(body: Optional[str]) -> List[str]:
    text = _HTML_COMMENT.sub("", body or "").strip()
    if len(text) < DESCRIPTION_MIN:
        return ["Add a description: what changed, why, and how you tested it."]
    return []


def lint_pull_request(pr: dict) -> List[str]:
    return lint_title(pr.get("title")) + lint_description(pr.get("body"))


def lint_comment(findings: List[str]) -> Optional[str]:
    """The section added to the welcome comment, or None when nothing was found."""
    if not findings:
        return None
    return "\n".join(["A few things that would help reviewers:", ""]
                     + [f"- {note}" for note in findings])
