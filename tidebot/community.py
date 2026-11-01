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
from .size import changed_lines, size_label, stale_labels
from .state import StateStore
from .workflow import Target, _words

KUDOS_KEY = "kudos"
VOTES_KEY = "votes"
_BALLOTS = {"yes": "yes", "y": "yes", "+1": "yes", "no": "no", "n": "no", "-1": "no"}

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
            "size": self._size,
            "vote": self._vote,
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

    def _size(self, gh: GitHubClient, t: Target, args: str) -> Optional[str]:
        if not t.is_pr:
            return "`/size` only works on pull requests."
        pr = gh.pull(t.repo, t.number)
        lines = changed_lines(pr)
        label = size_label(lines)
        current = [item.get("name", "") for item in pr.get("labels", [])]
        for old in stale_labels(current, label):
            gh.remove_label(t.repo, t.number, old)
        if label not in current:
            gh.add_labels(t.repo, t.number, [label])
        word = "line" if lines == 1 else "lines"
        return f"This PR changes {lines} {word}: `{label}`."

    def _vote(self, gh: GitHubClient, t: Target, args: str) -> Optional[str]:
        """Run one yes/no vote per issue.

        ``/vote <question>`` opens it, ``/vote yes`` or ``/vote no`` casts or
        changes a ballot, ``/vote`` shows the count and ``/vote close`` ends it.
        """
        votes = dict(self.store.get(VOTES_KEY) or {})
        key = f"{t.repo}#{t.number}"
        current = votes.get(key)
        text = args.strip()
        word = text.lower()
        if not text:
            if current is None:
                return "Usage: `:tide /vote Should we drop Python 3.8?`."
            return _tally(current, "Vote so far")
        if word in _BALLOTS:
            if current is None:
                return "There is no open vote here. Start one with `:tide /vote <question>`."
            ballots = dict(current["ballots"])
            ballots[t.author.lower()] = _BALLOTS[word]
            votes[key] = {**current, "ballots": ballots}
            self.store.set(VOTES_KEY, votes)
            return _tally(votes[key], "Vote so far")
        if word == "close":
            if current is None:
                return "There is no open vote here."
            del votes[key]
            self.store.set(VOTES_KEY, votes)
            return _tally(current, "Vote closed")
        if current is not None:
            return "A vote is already open here. End it with `:tide /vote close` first."
        votes[key] = {"question": text, "ballots": {}, "opened_by": t.author}
        self.store.set(VOTES_KEY, votes)
        return (f"Vote opened: **{text}**\n\n"
                "Answer with `:tide /vote yes` or `:tide /vote no`. "
                "You can change your answer until someone runs `:tide /vote close`.")


def _tally(vote: dict, heading: str) -> str:
    ballots = vote["ballots"].values()
    yes = sum(1 for b in ballots if b == "yes")
    no = sum(1 for b in ballots if b == "no")
    return f"{heading} on **{vote['question']}**: {yes} yes, {no} no."
