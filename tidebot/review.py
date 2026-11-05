"""The code review pipeline from the README's "How code review works".

Step one lives here so far: ``write_memo`` reads the PR thread into a short
memo on what the PR is trying to do, and ``pick_files`` lists the changed
files worth reviewing, leaving out lockfiles and generated code.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .ai import AIClient

# Most files one review looks at; each one costs a model call.
MAX_FILES = 30
MEMO_TOKENS = 300

# Files that tools rewrite; nobody reviews them by hand.
LOCKFILES = {
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "poetry.lock", "Pipfile.lock", "uv.lock", "pdm.lock", "Cargo.lock", "Gemfile.lock",
    "composer.lock", "go.sum", "flake.lock", "mix.lock", "pubspec.lock", "Podfile.lock",
    "packages.lock.json", "gradle.lockfile",
}
GENERATED_SUFFIXES = (
    ".min.js", ".min.css", ".map", ".pb.go", "_pb2.py", "_pb2_grpc.py", ".pb.h", ".pb.cc",
    ".g.dart", ".freezed.dart", ".snap",
)
GENERATED_DIRS = {"dist", "vendor", "node_modules", "third_party", "generated", "__generated__"}
# Markers code generators write near the top of a file.
_GENERATED_MARK = re.compile(r"@generated|code generated .*do not edit|auto-?generated",
                             re.IGNORECASE)
_FIRST_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+1(?:,\d+)? @@")


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    # The unified diff of this file; GitHub leaves it out for binary files
    # and very large changes.
    patch: str

    @classmethod
    def from_api(cls, entry: dict) -> "ChangedFile":
        return cls(entry["filename"], entry.get("status", "modified"), entry.get("patch") or "")


def _looks_generated(patch: str) -> bool:
    """True when a hunk at the top of the file carries a generator's marker."""
    lines = patch.splitlines()
    if not lines or not _FIRST_HUNK.match(lines[0]):
        return False
    return any(_GENERATED_MARK.search(line) for line in lines[1:6])


def skip_reason(f: ChangedFile) -> Optional[str]:
    """Why ``f`` isn't reviewed, or None when it should be."""
    name = posixpath.basename(f.path)
    if f.status == "removed":
        return "removed"
    if name in LOCKFILES:
        return "lockfile"
    if (name.endswith(GENERATED_SUFFIXES) or GENERATED_DIRS & set(f.path.split("/")[:-1])
            or _looks_generated(f.patch)):
        return "generated"
    if not f.patch:
        return "binary or too large to diff"
    return None


def pick_files(files: List[ChangedFile], limit: int = MAX_FILES
               ) -> Tuple[List[ChangedFile], List[Tuple[str, str]]]:
    """Split ``files`` into those to review and ``(path, reason)`` for the rest."""
    review: List[ChangedFile] = []
    skipped: List[Tuple[str, str]] = []
    for f in files:
        reason = skip_reason(f)
        if reason is None and len(review) >= limit:
            reason = f"over the {limit}-file limit"
        if reason:
            skipped.append((f.path, reason))
        else:
            review.append(f)
    return review, skipped


def write_memo(ai: AIClient, repo: str, thread: str) -> str:
    """A few sentences on what the PR is trying to do, from its whole thread."""
    return ai.ask(
        f"You are Tidebot, a maintainer's assistant for the GitHub repository {repo}. "
        "Before the code is reviewed, write a memo of three to five sentences for the "
        "reviewer: what the pull request below is trying to do, and anything the thread "
        "says about how it should be done or what to avoid. Don't review the code and "
        "don't guess beyond what the thread says.",
        thread, max_tokens=MEMO_TOKENS)
