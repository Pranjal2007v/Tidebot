"""Carry out the AI commands from the README's AI commands section.

Each command is a prompt around some context from the issue or PR. The
router has checked permission and rate limits; the app then queues the job
built by ``make_job``, which asks the model and posts the reply itself.
Commands the model can't help with yet are left out of ``AI_HANDLERS``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional

from .ai import AIClient, AIError
from .aiqueue import Job
from .commands import Command
from .github import GitHubClient, GitHubError
from .workflow import Target

# Characters of issue or PR text sent to the model; small models have
# small context windows.
MAX_CONTEXT = 8000
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


def _ask(gh: GitHubClient, ai: AIClient, t: Target, args: str) -> str:
    return ai.ask(_system(t.repo, "Answer the question using the issue or pull request "
                                  "below as context."),
                  f"{_opening_post(gh, t)}\n\nQuestion: {args}")


AI_HANDLERS: Dict[str, AICommand] = {
    "ask": AICommand(_ask, "Usage: `:tide /ask where is auth handled?`"),
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
