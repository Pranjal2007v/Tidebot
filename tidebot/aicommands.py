"""Carry out the AI commands from the README's AI commands section.

Each command is a prompt around some context from the issue or PR. The
router has checked permission and rate limits; the app then queues the job
built by ``make_job``, which asks the model and posts the reply itself. A
command that posts its own answer, as ``/review-sc`` posts a PR review,
returns None so no comment follows.
Commands the model can't help with yet are left out of ``AI_HANDLERS``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple, Union

from .ai import AIClient, AIError
from .aiqueue import Job
from .commands import Command
from .github import GitHubClient, GitHubError
from .review import (FOCUS, MAX_FINDINGS, ChangedFile, FileReview, Focus, Suggestion,
                     format_review, is_docs_path, is_test_path, numbered,
                     format_review_body, inline_comment, pick_files, review_files, verify,
                     write_memo)
from .router import is_bot
from .workflow import Target

# Characters of issue or PR text sent to the model; small models have
# small context windows.
MAX_CONTEXT = 8000
# Of that, the most the opening post of a long thread may take.
MAX_OPENING = 3000
# GitHub refuses comments over 65536 characters.
MAX_REPLY = 60000

Runner = Callable[[GitHubClient, AIClient, Target, str], Optional[str]]


@dataclass(frozen=True)
class AICommand:
    run: Runner
    # Shown, without asking the model, when the command needs arguments
    # and has none.
    usage: Optional[str] = None


def clip(text: Optional[str], limit: int = MAX_CONTEXT) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "\n[...cut for length]"


def _system(repo: str, task: str) -> str:
    return (f"You are Tidebot, a maintainer's assistant for the GitHub repository {repo}. "
            f"{task} Reply in GitHub Markdown and keep it short. If the context doesn't "
            "say, answer that you don't know rather than guessing file names or APIs.")


def _opening_post(gh: GitHubClient, t: Target) -> str:
    issue = gh.issue(t.repo, t.number)
    kind = "Pull request" if t.is_pr else "Issue"
    return f"{kind} #{t.number}: {issue.get('title') or ''}\n\n{clip(issue.get('body'))}"


def thread_text(issue: dict, comments: List[dict], is_pr: bool, number: int,
                limit: int = MAX_CONTEXT) -> str:
    """The opening post and the latest human comments that fit in ``limit``.

    Bot comments, Tidebot's own included, are left out. When the thread is
    too long the oldest comments go first, since the latest say where it
    stands.
    """
    kind = "Pull request" if is_pr else "Issue"
    author = (issue.get("user") or {}).get("login", "someone")
    head = (f"{kind} #{number} by @{author}: {issue.get('title') or ''}\n\n"
            f"{clip(issue.get('body'), MAX_OPENING)}")
    # Leave room for the "[N earlier comments left out]" note.
    budget = limit - len(head) - 40
    kept: List[str] = []
    people = [c for c in comments if not is_bot((c.get("user") or {}).get("login", ""))]
    for c in reversed(people):
        entry = f"@{(c.get('user') or {}).get('login', '')}: {(c.get('body') or '').strip()}"
        if len(entry) > budget:
            break
        kept.append(entry)
        budget -= len(entry) + 2
    left_out = len(people) - len(kept)
    parts = [head]
    if left_out:
        parts.append(f"[{left_out} earlier comments left out]")
    parts += reversed(kept)
    return "\n\n".join(parts)


def _ask(gh: GitHubClient, ai: AIClient, t: Target, args: str) -> str:
    return ai.ask(_system(t.repo, "Answer the question using the issue or pull request "
                                  "below as context."),
                  f"{_opening_post(gh, t)}\n\nQuestion: {args}")


def _summarize(gh: GitHubClient, ai: AIClient, t: Target, args: str) -> str:
    thread = thread_text(gh.issue(t.repo, t.number), gh.issue_comments(t.repo, t.number),
                         t.is_pr, t.number)
    return ai.ask(_system(t.repo, "Summarize the thread below in a few bullets: what it is "
                                  "about, what has been decided and what is still open."),
                  thread)


def _explain(gh: GitHubClient, ai: AIClient, t: Target, args: str) -> str:
    """Explain a PR's change from its diff, or an issue in plain words.

    Text after the command narrows the explanation, as in ``/explain the retry loop``.
    """
    if t.is_pr:
        task = ("Explain what the pull request below changes and why, for a reviewer "
                "who doesn't know this code yet.")
        diff = gh.pull_diff(t.repo, t.number)
        context = _opening_post(gh, t) + (f"\n\nDiff:\n{clip(diff)}" if diff else
                                          "\n\n(The diff is too large to include.)")
    else:
        task = ("Explain the issue below in plain words: the problem, where it likely "
                "comes from and what would fix it.")
        context = _opening_post(gh, t)
    if args.strip():
        context += f"\n\nFocus on: {args.strip()}"
    return ai.ask(_system(t.repo, task), context)


@dataclass(frozen=True)
class ReviewResult:
    """What the review pipeline found at the PR's head commit ``sha``."""
    sha: str
    memo: str
    kept: List[Suggestion]
    reviews: List[FileReview]
    skipped: List[Tuple[str, str]]
    dropped: int
    focus: Focus
    # Every file the PR changes, reviewed or not.
    paths: List[str]

    def comment(self) -> str:
        return format_review(self.memo, self.kept, self.reviews, self.skipped, self.dropped,
                             self.focus.label)


def _pipeline(gh: GitHubClient, ai: AIClient, t: Target, name: str,
              focus: Focus = FOCUS["review"]) -> Union[str, ReviewResult]:
    """Run the review pipeline from the README's "How code review works".

    Returns a reply instead when there is nothing to review.
    """
    if not t.is_pr:
        return f"`/{name}` works on pull requests only."
    sha = gh.pull(t.repo, t.number)["head"]["sha"]
    files = [ChangedFile.from_api(f) for f in gh.pull_changes(t.repo, t.number)]
    to_review, skipped = pick_files(files)
    if not to_review:
        return "Nothing to review: every changed file is a lockfile, generated, removed or binary."
    thread = thread_text(gh.issue(t.repo, t.number), gh.issue_comments(t.repo, t.number),
                         True, t.number)
    memo = write_memo(ai, t.repo, thread)
    reviews = review_files(ai, t.repo, memo, to_review, focus=focus)
    found = [s for r in reviews for s in r.suggestions]
    kept, dropped = verify(gh, t.repo, sha, to_review, found)
    return ReviewResult(sha, memo, kept, reviews, skipped, dropped, focus,
                        [f.path for f in files])


def _focused_review(name: str) -> Runner:
    """``/review``, ``/security`` or ``/perf``: the pipeline with that command's focus,
    answered in one comment."""
    def run(gh: GitHubClient, ai: AIClient, t: Target, args: str) -> str:
        result = _pipeline(gh, ai, t, name, FOCUS[name])
        return result if isinstance(result, str) else result.comment()

    return run


def _docs(gh: GitHubClient, ai: AIClient, t: Target, args: str) -> str:
    """Suggest missing doc comments, and say when code changed but no docs did."""
    result = _pipeline(gh, ai, t, "docs", FOCUS["docs"])
    if isinstance(result, str):
        return result
    text = result.comment()
    if not any(is_docs_path(p) for p in result.paths):
        text += ("\n\nThis PR changes no docs files (README, `*.md`, `docs/`). If it changes "
                 "how something is used, the docs may need an update too.")
    return text


def _test(gh: GitHubClient, ai: AIClient, t: Target, args: str) -> str:
    """List the test cases a PR's code changes still need.

    The model sees the code diffs and the names of the test files the PR
    already touches, so it can say where each case belongs and skip what
    those tests cover. Text after the command narrows the focus.
    """
    if not t.is_pr:
        return "`/test` works on pull requests only."
    files = [ChangedFile.from_api(f) for f in gh.pull_changes(t.repo, t.number)]
    to_review, _ = pick_files(files)
    tests = [f.path for f in files if is_test_path(f.path) and f.status != "removed"]
    code = [f for f in to_review if not is_test_path(f.path) and not is_docs_path(f.path)]
    if not code:
        return "Nothing to test: this PR changes no code, only tests, docs or generated files."
    diffs = "\n\n".join(f"File: {f.path}\n{numbered(f.patch)}" for f in code)
    context = _opening_post(gh, t)
    context += ("\n\nTest files this PR changes: " + ", ".join(tests) if tests else
                "\n\nThis PR changes no test files.")
    context += f"\n\nCode changes:\n{clip(diffs)}"
    if args.strip():
        context += f"\n\nFocus on: {args.strip()}"
    return ai.ask(_system(t.repo, "List the test cases the code changes below still need, "
                                  "at most eight, as Markdown bullets. For each give the test "
                                  "file it belongs in (one the PR already changes when it "
                                  "fits), a test name and what it checks: edge cases, error "
                                  "paths and the behavior the PR adds. Leave out cases the "
                                  "changed test files clearly cover already."),
                  context)


def _review_sc(gh: GitHubClient, ai: AIClient, t: Target, args: str) -> Optional[str]:
    """Post the verified findings as inline suggested changes in one PR review.

    Up to ``MAX_FINDINGS`` go inline and the rest are listed in the review
    body. With no findings there is no review, only the usual comment.
    """
    r = _pipeline(gh, ai, t, "review-sc")
    if isinstance(r, str):
        return r
    if not r.kept:
        return r.comment()
    body = (f"`/review-sc` for @{t.author}:\n\n"
            + format_review_body(r.memo, r.kept[MAX_FINDINGS:], r.reviews, r.skipped, r.dropped))
    # Placed at the commit the suggestions were checked against, even if
    # the PR has moved on since.
    gh.post_review(t.repo, t.number, r.sha, body,
                   [inline_comment(s) for s in r.kept[:MAX_FINDINGS]])
    return None


def changelog_line(answer: str, number: int) -> str:
    """The model's first line as one release-note bullet ending in ``(#number)``."""
    line = next((l.strip() for l in answer.splitlines() if l.strip()), "")
    line = line.lstrip("-*• ").strip().strip("`")
    if f"#{number}" not in line:
        line = f"{line} (#{number})"
    return f"- {line}"


def _changelog(gh: GitHubClient, ai: AIClient, t: Target, args: str) -> str:
    """One release-note line for a PR, from its title, description, files and diff."""
    if not t.is_pr:
        return "`/changelog` works on pull requests only."
    paths = [f.get("filename", "") for f in gh.pull_changes(t.repo, t.number)]
    diff = gh.pull_diff(t.repo, t.number)
    context = _opening_post(gh, t)
    context += "\n\nChanged files: " + (", ".join(paths) if paths else "none")
    context += f"\n\nDiff:\n{clip(diff, MAX_CONTEXT // 2)}" if diff else ""
    answer = ai.ask(_system(t.repo, "Write one release-note line for the pull request "
                                    "below, for people who use the project, not its "
                                    "developers. Start with a conventional type such as "
                                    "feat, fix, docs or perf and a colon, then say what "
                                    "changed for the user in under 15 words. Reply with "
                                    "the line only."),
                    context)
    return changelog_line(answer, t.number)


def _estimate(gh: GitHubClient, ai: AIClient, t: Target, args: str) -> str:
    """A rough size and effort for an issue, or for a PR's change."""
    thread = thread_text(gh.issue(t.repo, t.number), gh.issue_comments(t.repo, t.number),
                         t.is_pr, t.number, MAX_CONTEXT // 2)
    if t.is_pr:
        pr = gh.pull(t.repo, t.number)
        thread += (f"\n\nLines changed: +{pr.get('additions', 0)} -{pr.get('deletions', 0)} "
                   f"across {pr.get('changed_files', 0)} files.")
        task = ("Estimate how long the pull request below takes to review well and how "
                "risky it is.")
    else:
        task = "Estimate how much work the issue below takes to fix or build."
    if args.strip():
        thread += f"\n\nAssume: {args.strip()}"
    return ai.ask(_system(t.repo, task + " Start with a size from XS, S, M, L or XL and "
                                         "a rough time such as \"half a day\", then give "
                                         "up to three short reasons and the main unknown. "
                                         "It is a guess; say so when the context is thin."),
                  thread)


# Most items a checklist keeps; a long list stops being checked.
MAX_CHECKLIST = 10
_LIST_ITEM = re.compile(r"^\s*(?:[-*•+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.+)$")


def checklist_items(answer: str, limit: int = MAX_CHECKLIST) -> List[str]:
    """The list items in the model's answer as unticked GitHub task-list lines."""
    items = []
    for line in answer.splitlines():
        match = _LIST_ITEM.match(line)
        if match and len(items) < limit:
            items.append(f"- [ ] {match.group(1).strip()}")
    return items


def _checklist(gh: GitHubClient, ai: AIClient, t: Target, args: str) -> str:
    """A review checklist for a PR, or a definition-of-done checklist for an issue."""
    thread = thread_text(gh.issue(t.repo, t.number), gh.issue_comments(t.repo, t.number),
                         t.is_pr, t.number, MAX_CONTEXT // 2)
    if t.is_pr:
        diff = gh.pull_diff(t.repo, t.number)
        thread += (f"\n\nDiff:\n{clip(diff, MAX_CONTEXT // 2)}" if diff else
                   "\n\n(The diff is too large to include.)")
        task = ("Write a checklist a reviewer works through before approving the pull "
                "request below: what to run, read and try, specific to this change.")
    else:
        task = ("Write a checklist of what must be true before the issue below can be "
                "closed as done: the behavior, tests and docs it needs.")
    if args.strip():
        thread += f"\n\nFocus on: {args.strip()}"
    answer = ai.ask(_system(t.repo, task + f" Give at most {MAX_CHECKLIST} items, one "
                                           "per line, each starting with \"- \" and under "
                                           "15 words. Reply with the list only."),
                    thread)
    items = checklist_items(answer)
    return "\n".join(items) if items else answer


ROAST_FOOTER = "\n\n_All in good fun. Run `/review` for the serious version._"


def _roast(gh: GitHubClient, ai: AIClient, t: Target, args: str) -> str:
    """A light-hearted take on a PR's code, never on the people behind it."""
    if not t.is_pr:
        return "`/roast` works on pull requests only."
    diff = gh.pull_diff(t.repo, t.number)
    context = _opening_post(gh, t)
    context += (f"\n\nDiff:\n{clip(diff, MAX_CONTEXT // 2)}" if diff else
                "\n\n(The diff is too large to include, so roast its size.)")
    answer = ai.ask(_system(t.repo, "Give the pull request below a friendly roast in "
                                    "three to five short lines, like a teammate teasing "
                                    "over coffee. Joke about the code, naming, size or "
                                    "commit habits, never about the author as a person, "
                                    "their skill, or anything outside the PR. No slurs "
                                    "or swearing. End with one thing the PR does well."),
                    context, temperature=0.8)
    return answer + ROAST_FOOTER


AI_HANDLERS: Dict[str, AICommand] = {
    "ask": AICommand(_ask, "Usage: `:tide /ask where is auth handled?`"),
    "summarize": AICommand(_summarize),
    "explain": AICommand(_explain),
    "review": AICommand(_focused_review("review")),
    "review-sc": AICommand(_review_sc),
    "security": AICommand(_focused_review("security")),
    "perf": AICommand(_focused_review("perf")),
    "docs": AICommand(_docs),
    "test": AICommand(_test),
    "changelog": AICommand(_changelog),
    "estimate": AICommand(_estimate),
    "checklist": AICommand(_checklist),
    "roast": AICommand(_roast),
}


def usage_error(command: Command) -> Optional[str]:
    """The usage reply when ``command`` needs arguments it doesn't have."""
    handler = AI_HANDLERS.get(command.name)
    if handler and handler.usage and not command.args.strip():
        return handler.usage
    return None


def make_job(gh: GitHubClient, target: Target, command: Command) -> Job:
    """A queue job that runs ``command`` and posts the answer on the issue."""
    handler = AI_HANDLERS[command.name]

    def job(ai: AIClient) -> None:
        try:
            answer = handler.run(gh, ai, target, command.args)
            if answer is None:
                return
            reply = f"`/{command.name}` for @{target.author}:\n\n{clip(answer, MAX_REPLY)}"
        except AIError as err:
            reply = f"`/{command.name}` failed: {err}"
        except GitHubError as err:
            reply = f"`/{command.name}` failed: GitHub answered {err.status}"
        gh.post_comment(target.repo, target.number, reply)

    return job
