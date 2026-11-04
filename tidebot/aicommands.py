"""Carry out the AI commands from the README's AI commands section.

Each command is a prompt around some context from the issue or PR. The
router has checked permission and rate limits; the app then queues the job
built by ``make_job``, which asks the model and posts the reply itself.
Commands the model can't help with yet are left out of ``AI_HANDLERS``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .ai import AIClient, AIError
from .aiqueue import Job
from .commands import Command
from .github import GitHubClient, GitHubError
from .router import is_bot
from .workflow import Target

# Characters of issue or PR text sent to the model; small models have
# small context windows.
MAX_CONTEXT = 8000
# Of that, the most the opening post of a long thread may take.
MAX_OPENING = 3000
# GitHub refuses comments over 65536 characters.
MAX_REPLY = 60000

Runner = Callable[[GitHubClient, AIClient, Target, str], str]


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


AI_HANDLERS: Dict[str, AICommand] = {
    "ask": AICommand(_ask, "Usage: `:tide /ask where is auth handled?`"),
    "summarize": AICommand(_summarize),
    "explain": AICommand(_explain),
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
            text = clip(handler.run(gh, ai, target, command.args), MAX_REPLY)
            reply = f"`/{command.name}` for @{target.author}:\n\n{text}"
        except AIError as err:
            reply = f"`/{command.name}` failed: {err}"
        except GitHubError as err:
            reply = f"`/{command.name}` failed: GitHub answered {err.status}"
        gh.post_comment(target.repo, target.number, reply)

    return job
