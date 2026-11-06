"""The code review pipeline from the README's "How code review works".

``write_memo`` reads the PR thread into a short memo on what the PR is
trying to do, and ``pick_files`` lists the changed files worth reviewing,
leaving out lockfiles and generated code. ``review_files`` then reviews each
file on its own, four at a time, with the ``Focus`` of the command that asked
(``/review`` looks for any real problem, ``/security``, ``/perf`` and
``/docs`` for one kind), and collects the model's findings as
``Suggestion`` objects: a path, a line range on the new side of the diff, the
lines as the model read them and their replacement. ``verify`` checks each
suggestion against the real lines of the file at the PR's head commit and
drops any that don't apply cleanly. ``format_review`` writes what is left
into the one comment ``/review`` posts; ``inline_comment`` and
``format_review_body`` turn it into the PR review ``/review-sc`` posts.
"""

from __future__ import annotations

import json
import posixpath
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .ai import AIClient, AIError
from .github import GitHubClient, GitHubError

# Most files one review looks at; each one costs a model call.
MAX_FILES = 30
MEMO_TOKENS = 300
# Files reviewed at once, as the README says. This is within one queued
# review job; the AI queue still runs one job at a time.
WORKERS = 4
# Characters of numbered diff sent for one file.
MAX_FILE_CONTEXT = 6000
FILE_TOKENS = 1200
# Findings shown in the review comment; the rest are only counted.
MAX_FINDINGS = 12

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
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


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


@dataclass(frozen=True)
class Hunk:
    # First and last line of the hunk on the new side of the diff.
    start: int
    end: int


@dataclass(frozen=True)
class Suggestion:
    path: str
    start: int
    end: int
    # The lines as the model read them, and what should replace them.
    original: str
    replacement: str
    note: str


@dataclass(frozen=True)
class FileReview:
    path: str
    suggestions: List[Suggestion]
    error: Optional[str] = None


def hunks(patch: str) -> List[Hunk]:
    """The new-side line range of every hunk in ``patch``."""
    found: List[Hunk] = []
    for line in patch.splitlines():
        m = _HUNK.match(line)
        if m:
            start, count = int(m.group(1)), int(m.group(2) or 1)
            if count:
                found.append(Hunk(start, start + count - 1))
    return found


def numbered(patch: str) -> str:
    """``patch`` with each new-side line prefixed by its line number.

    Removed lines get no number, since a suggestion can't change them.
    """
    out: List[str] = []
    line_no = 0
    for line in patch.splitlines():
        m = _HUNK.match(line)
        if m:
            line_no = int(m.group(1))
            out.append(line)
        elif line.startswith("-"):
            out.append(f"{'':>6} {line}")
        elif line.startswith("\\"):
            continue
        else:
            out.append(f"{line_no:>6} {line}")
            line_no += 1
    return "\n".join(out)


def _text(value: object) -> Optional[str]:
    return value.rstrip("\n") if isinstance(value, str) else None


def parse_findings(path: str, answer: str) -> List[Suggestion]:
    """The suggestions in a model answer that should be a JSON array.

    Code fences and text around the array are ignored, and items missing a
    field or with nonsense line numbers are dropped.
    """
    first, last = answer.find("["), answer.rfind("]")
    if first < 0 or last < first:
        return []
    try:
        items = json.loads(answer[first:last + 1])
    except ValueError:
        return []
    found: List[Suggestion] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        start, end = item.get("start"), item.get("end", item.get("start"))
        original, replacement = _text(item.get("original")), _text(item.get("replacement"))
        note = _text(item.get("note")) or ""
        if (any(not isinstance(n, int) or isinstance(n, bool) for n in (start, end))
                or start < 1 or end < start or original is None or replacement is None):
            continue
        found.append(Suggestion(path, start, end, original, replacement, note.strip()))
    return found


@dataclass(frozen=True)
class Focus:
    # What the model is told to look for, and what the reply calls it.
    task: str
    label: str


FOCUS: Dict[str, Focus] = {
    "review": Focus("Look for real problems only: bugs, security holes, wrong error handling, "
                    "clear mistakes. Skip style nits.", "problems"),
    "security": Focus("Look only for security problems: injection into SQL, shell commands or "
                      "templates, path traversal, unsafe deserialization, missing "
                      "authentication or permission checks, secrets in code, weak crypto or "
                      "randomness, and untrusted input reaching a dangerous call. Ignore "
                      "everything else.", "security problems"),
    "perf": Focus("Look only for performance problems: work repeated inside loops, a query or "
                  "API call per item where one batch would do, quadratic searches where a set "
                  "or dict would do, whole files or responses read into memory without need, "
                  "blocking calls on hot paths and costly results computed again and again. "
                  "Ignore everything else and skip micro-optimizations.",
                  "performance problems"),
    "docs": Focus("Look only for missing or wrong documentation: new or changed public "
                  "functions, classes, methods, options and endpoints without a docstring or "
                  "doc comment, and existing doc comments or docs text the change made wrong. "
                  "Write docs in the style the file already uses. For a missing docstring, "
                  "the replacement is the original lines with the docstring added. Ignore "
                  "private helpers whose name says what they do, and everything that isn't "
                  "documentation.", "missing docs"),
}

# Where projects keep their docs, besides doc comments in the code.
DOC_SUFFIXES = (".md", ".rst", ".adoc", ".txt")
DOC_DIRS = {"docs", "doc", "documentation"}


def is_docs_path(path: str) -> bool:
    """True for a file that is documentation rather than code."""
    parts = path.lower().split("/")
    return parts[-1].endswith(DOC_SUFFIXES) or bool(DOC_DIRS & set(parts[:-1]))


TEST_DIRS = {"test", "tests", "__tests__", "spec", "testing"}
# test_x.py, x_test.go, x.test.ts, x.spec.js, XTest.java, x_spec.rb and so on.
_TEST_NAME = re.compile(r"^test_|_test\.|\.test\.|\.spec\.|_spec\.|Tests?\.(java|kt|cs|swift)$")


def is_test_path(path: str) -> bool:
    """True for a file that holds tests."""
    parts = path.split("/")
    return bool(_TEST_NAME.search(parts[-1])) or bool(TEST_DIRS & {p.lower() for p in parts[:-1]})

_FILE_TASK = (
    "You are Tidebot, reviewing one file of a pull request to the GitHub repository {repo}. "
    "{focus} Each line of the diff starts with its line number in the "
    "new file; removed lines have none and can't be changed. Reply with only a JSON array, "
    "one object per problem: {{\"start\": first line, \"end\": last line, \"original\": "
    "the exact current text of those lines, \"replacement\": the text that should replace "
    "them, \"note\": one sentence on why}}. Reply [] when nothing needs to change."
)


def review_file(ai: AIClient, repo: str, memo: str, f: ChangedFile,
                focus: Focus = FOCUS["review"]) -> FileReview:
    """Ask the model about one file and collect its suggestions."""
    diff = numbered(f.patch)
    if len(diff) > MAX_FILE_CONTEXT:
        diff = diff[:MAX_FILE_CONTEXT] + "\n[...cut for length]"
    try:
        answer = ai.ask(_FILE_TASK.format(repo=repo, focus=focus.task),
                        f"What the PR is for: {memo}\n\nFile: {f.path}\n\n{diff}",
                        max_tokens=FILE_TOKENS)
    except AIError as err:
        return FileReview(f.path, [], str(err))
    return FileReview(f.path, parse_findings(f.path, answer))


def review_files(ai: AIClient, repo: str, memo: str, files: List[ChangedFile],
                 workers: int = WORKERS, focus: Focus = FOCUS["review"]) -> List[FileReview]:
    """Review every file in ``files``, ``workers`` at a time, in the same order."""
    if not files:
        return []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda f: review_file(ai, repo, memo, f, focus), files))


def _lines(text: str) -> List[str]:
    return [line.rstrip() for line in text.splitlines()]


def check(s: Suggestion, file_lines: List[str], file_hunks: List[Hunk]) -> Optional[str]:
    """Why ``s`` doesn't apply cleanly to the file, or None when it does.

    GitHub only takes suggestions on lines inside one hunk of the diff, and
    the lines the model quoted must be the file's real lines; trailing
    spaces are ignored.
    """
    if not any(h.start <= s.start and s.end <= h.end for h in file_hunks):
        return "outside the diff"
    if s.end > len(file_lines):
        return "past the end of the file"
    if _lines(s.original) != [line.rstrip() for line in file_lines[s.start - 1:s.end]]:
        return "doesn't match the file"
    if _lines(s.replacement) == _lines(s.original):
        return "changes nothing"
    if "```" in s.replacement:
        return "can't be shown as a suggestion"
    return None


def verify(gh: GitHubClient, repo: str, sha: str, files: List[ChangedFile],
           suggestions: List[Suggestion]) -> Tuple[List[Suggestion], int]:
    """The suggestions that apply cleanly at ``sha``, and how many were dropped.

    Each file is read once. A file GitHub can't return drops every
    suggestion on it.
    """
    patches = {f.path: f.patch for f in files}
    texts: Dict[str, Optional[str]] = {}
    kept: List[Suggestion] = []
    for s in suggestions:
        if s.path not in texts:
            try:
                texts[s.path] = gh.fetch_file(repo, s.path, ref=sha)
            except GitHubError:
                texts[s.path] = None
        text = texts[s.path]
        if text is not None and check(s, text.splitlines(), hunks(patches.get(s.path, ""))) is None:
            kept.append(s)
    return kept, len(suggestions) - len(kept)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _finding(n: int, s: Suggestion) -> str:
    where = f"line {s.start}" if s.start == s.end else f"lines {s.start}-{s.end}"
    diff = [f"-{line}" for line in s.original.split("\n")]
    diff += [f"+{line}" for line in s.replacement.split("\n")] if s.replacement else []
    head = f"{n}. `{s.path}` {where}" + (f": {s.note}" if s.note else "")
    return head + "\n\n````diff\n" + "\n".join(diff) + "\n````"


def _tally(reviews: List[FileReview], skipped: List[Tuple[str, str]], dropped: int) -> str:
    tally = [f"Reviewed {_plural(len(reviews), 'file')}."]
    failed = [r for r in reviews if r.error]
    if failed:
        tally.append("Could not review: " + ", ".join(f"`{r.path}` ({r.error})" for r in failed)
                     + ".")
    if skipped:
        tally.append("Skipped: " + ", ".join(f"`{p}` ({why})" for p, why in skipped) + ".")
    if dropped:
        tally.append(f"Dropped {_plural(dropped, 'suggestion')} that didn't match the file.")
    return " ".join(tally)


def format_review(memo: str, kept: List[Suggestion], reviews: List[FileReview],
                  skipped: List[Tuple[str, str]], dropped: int, label: str = "problems") -> str:
    """The ``/review`` comment: the memo, up to ``MAX_FINDINGS`` findings and a tally."""
    parts = [f"**What this PR does:** {memo.strip()}"]
    if kept:
        parts.append("**Findings**")
        parts += [_finding(n, s) for n, s in enumerate(kept[:MAX_FINDINGS], 1)]
        if len(kept) > MAX_FINDINGS:
            more = len(kept) - MAX_FINDINGS
            parts.append(f"{_plural(more, 'more finding')} not shown.")
    else:
        parts.append(f"No {label} found in the reviewed files.")
    parts.append(_tally(reviews, skipped, dropped))
    return "\n\n".join(parts)


def inline_comment(s: Suggestion) -> dict:
    """``s`` as an inline review comment holding a GitHub suggested change.

    An empty replacement suggests deleting the lines.
    """
    body = (f"{s.note}\n\n" if s.note else "") + "```suggestion\n"
    body += (s.replacement + "\n" if s.replacement else "") + "```"
    comment = {"path": s.path, "line": s.end, "side": "RIGHT", "body": body}
    if s.start != s.end:
        comment.update(start_line=s.start, start_side="RIGHT")
    return comment


def format_review_body(memo: str, rest: List[Suggestion], reviews: List[FileReview],
                       skipped: List[Tuple[str, str]], dropped: int) -> str:
    """The body of the ``/review-sc`` review: the memo, the findings that
    didn't fit inline as one line each, and the tally."""
    parts = [f"**What this PR does:** {memo.strip()}"]
    if rest:
        lines = []
        for s in rest:
            where = f"line {s.start}" if s.start == s.end else f"lines {s.start}-{s.end}"
            lines.append(f"- `{s.path}` {where}" + (f": {s.note}" if s.note else ""))
        parts.append(f"**{_plural(len(rest), 'more finding')}** past the "
                     f"{MAX_FINDINGS} shown inline:\n" + "\n".join(lines))
    parts.append(_tally(reviews, skipped, dropped))
    return "\n\n".join(parts)
