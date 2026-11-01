"""Carry out the community commands.

These are the light-hearted and bookkeeping commands from the README's
Community section. Unlike the workflow handlers, some of them remember
things between comments, so they live on a class that holds the state
store. Each handler returns the text to reply with, or None.
"""

from __future__ import annotations

import random
import time
from typing import Callable, Dict, Optional

from .commands import Command
from .github import GitHubClient
from .state import StateStore
from .workflow import Target, _words

KUDOS_KEY = "kudos"

JOKES = (
    "There are 10 kinds of people: those who read binary and those who don't.",
    "A SQL query walks into a bar, goes up to two tables and asks: may I join you?",
    "Why do programmers mix up Halloween and Christmas? Because Oct 31 == Dec 25.",
    "It works on my machine. Then we'll ship your machine.",
    "I would tell you a UDP joke, but you might not get it.",
    "The two hardest problems in computing: cache invalidation, naming things and off-by-one errors.",
    "git commit -m 'fix' is not a changelog.",
)

CommunityHandler = Callable[[GitHubClient, Target, str], Optional[str]]


class Community:
    def __init__(self, store: StateStore, clock: Callable[[], float] = time.time,
                 rng: Optional[random.Random] = None):
        self.store = store
        self.clock = clock
        self.rng = rng or random.Random()
        self.handlers: Dict[str, CommunityHandler] = {
            "ping": self._ping,
            "joke": self._joke,
            "kudos": self._kudos,
        }

    def handles(self, name: str) -> bool:
        return name in self.handlers

    def run(self, gh: GitHubClient, target: Target, command: Command) -> Optional[str]:
        return self.handlers[command.name](gh, target, command.args)

    def _ping(self, gh: GitHubClient, t: Target, args: str) -> Optional[str]:
        return "pong"

    def _joke(self, gh: GitHubClient, t: Target, args: str) -> Optional[str]:
        return self.rng.choice(JOKES)

    def _kudos(self, gh: GitHubClient, t: Target, args: str) -> Optional[str]:
        words = _words(args)
        if not words or not words[0].startswith("@") or len(words[0]) < 2:
            return "Usage: `:tide /kudos @someone for the quick fix`."
        login = words[0][1:]
        if login.lower() == t.author.lower():
            return "Kudos have to go to someone else."
        reason = args.strip()[len(words[0]):].strip()
        # Counted per repo, by lowercased login, so /stats can show totals.
        kudos = dict(self.store.get(KUDOS_KEY) or {})
        repo = dict(kudos.get(t.repo, {}))
        repo[login.lower()] = repo.get(login.lower(), 0) + 1
        kudos[t.repo] = repo
        self.store.set(KUDOS_KEY, kudos)
        count = repo[login.lower()]
        line = f"Kudos to @{login} from @{t.author}"
        if not reason:
            line += "!"
        elif reason.lower().startswith("for "):
            line += f" {reason}"
        else:
            line += f": {reason}"
        times = "time" if count == 1 else "times"
        return f"{line}\n\n@{login} has been thanked {count} {times} here."
