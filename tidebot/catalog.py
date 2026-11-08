"""Describe every command for the website's command reference.

Each entry has a one-line summary, an example of how to run it and an
example of what Tidebot does or replies. The group and the tier come from
``commands`` and ``permissions``, so the reference can't drift from what the
bot actually accepts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .commands import AI_COMMANDS, BARE_COMMANDS, COMMUNITY_COMMANDS, TRIGGER, WORKFLOW_COMMANDS, Command
from .permissions import Tier, required_tier

GROUPS = (
    ("AI", AI_COMMANDS),
    ("Workflow", WORKFLOW_COMMANDS),
    ("Community", COMMUNITY_COMMANDS),
)


@dataclass(frozen=True)
class Entry:
    name: str
    group: str
    tier: str
    summary: str
    example: str
    result: str
    bare: bool = False


# name: (summary, arguments for the example, what happens)
_DETAILS: Dict[str, tuple] = {
    "ask": ("Answer a question using the issue or PR thread as context.",
            "where is auth handled?",
            "A short answer that points at the files or comments it used."),
    "review": ("Run the review pipeline and post the findings in one comment.",
               "",
               "A memo on what the PR does, then each verified finding by file."),
    "review-sc": ("Review the PR and post up to 12 findings as inline suggested changes.",
                  "",
                  "One PR review with suggestions you can commit from the diff view."),
    "security": ("Look only for security problems in the changed files.",
                 "",
                 "Findings such as injection, path traversal or secrets in code."),
    "perf": ("Look only for performance problems in the changed files.",
             "",
             "Findings such as repeated work in loops or quadratic searches."),
    "docs": ("Suggest missing or outdated doc comments in the PR.",
             "",
             "Suggested docstrings, and a note when code changed but no docs did."),
    "test": ("List the test cases the PR's code changes still need.",
             "edge cases for the parser",
             "Up to eight test cases, each with a file, a name and what it checks."),
    "summarize": ("Summarize a long issue or PR thread.",
                  "",
                  "A few lines on where the discussion stands and what is still open."),
    "explain": ("Explain a PR's change from its diff, or an issue in plain words.",
                "",
                "A plain-language walk through what changes and why."),
    "changelog": ("Write a release-note line for the PR.",
                  "",
                  "- Reminders can now be cancelled with `/remind cancel` (#42)"),
    "estimate": ("Give a rough size and effort for an issue or PR.",
                 "assuming no API changes",
                 "**M**, about a day, with up to three reasons."),
    "checklist": ("Make a review checklist for a PR or a definition of done for an issue.",
                  "",
                  "A GitHub task list of up to ten unticked items."),
    "roast": ("A light-hearted take on the PR's code, never on the people behind it.",
              "",
              "Three to five friendly lines, ending with something the PR does well."),
    "chat": ("Talk with the model in the thread, with earlier `/chat` turns as context.",
             "would a cache help here?",
             "A reply that follows on from the earlier turns."),
    "assign": ("Assign yourself, or (as a maintainer) anyone else.",
               "@me",
               "The issue is assigned; no reply."),
    "label": ("Add labels, or remove one with a leading minus.",
              "bug -question",
              "Labels are updated; no reply."),
    "close": ("Close the issue or PR.",
              "",
              "It is closed; no reply."),
    "reopen": ("Reopen a closed issue or PR.",
               "",
               "It is reopened; no reply."),
    "retitle": ("Change the title.",
                "Fix crash when the config file is empty",
                "The title is changed; no reply."),
    "duplicate": ("Mark the issue as a duplicate of another and close it.",
                  "#123",
                  "Duplicate of #123"),
    "milestone": ("Set the milestone, or `clear` it.",
                  "v1.0",
                  "The milestone is set; no reply."),
    "lock": ("Lock the conversation, with an optional reason, or `cancel` to unlock.",
             "resolved",
             "The conversation is locked; no reply."),
    "cc": ("Ask someone to look: a review request on a PR, a mention on an issue.",
           "@alice",
           "cc @alice"),
    "lgtm": ("Add the `lgtm` label to a PR, or `cancel` to remove it.",
             "",
             "The `lgtm` label is added; no reply."),
    "hold": ("Block a merge with `do-not-merge/hold`, or `cancel` to lift it.",
             "",
             "The hold label is added; no reply."),
    "wip": ("Mark a PR as work in progress, or `cancel` when it's ready.",
            "",
            "The `do-not-merge/wip` label is added; no reply."),
    "approve": ("Approve the PR as a GitHub review.",
                "",
                "An approving review is posted."),
    "merge": ("Merge the PR once CI is green and it has an approval.",
              "squash",
              "Not merging: it has no approval; CI is still running."),
    "ship": ("Approve and merge in one step, if nothing else blocks the merge.",
             "",
             "The PR is approved and merged."),
    "vote": ("Open a yes/no vote, cast a ballot, show the count or `close` it.",
             "Should we drop Python 3.8?",
             "Vote opened: **Should we drop Python 3.8?**"),
    "kudos": ("Thank someone, with a count of how often they've been thanked here.",
              "@alice for the quick fix",
              "Kudos to @alice from @bob for the quick fix"),
    "stats": ("Show how Tidebot is used in this repo.",
              "",
              "**Tidebot in owner/repo:** 128 commands run. Most used: `/lgtm` 40, ..."),
    "remind": ("Set a reminder in this thread, from 1 minute to 30 days ahead.",
               "2h check the flaky test",
               "OK @bob, I'll remind you here in 2h."),
    "size": ("Label the PR by how many lines it changes.",
             "",
             "This PR changes 84 lines: `size/M`."),
    "ping": ("Check that Tidebot is listening.",
             "",
             "pong"),
    "joke": ("Tell a programming joke.",
             "",
             "It works on my machine. Then we'll ship your machine."),
    "help": ("List the commands you can run here.",
             "",
             "The commands your access level allows, by group."),
}


def _tier_label(name: str) -> str:
    if name == "assign":
        return "Collaborator (self), Maintainer (others)"
    return required_tier(Command(name), "").name.capitalize()


def entries() -> List[Entry]:
    """Every command, grouped like the README and sorted by name in each group."""
    result = []
    for group, names in GROUPS:
        for name in sorted(names):
            summary, args, outcome = _DETAILS[name]
            example = f"{TRIGGER} /{name}" + (f" {args}" if args else "")
            result.append(Entry(name, group, _tier_label(name), summary, example, outcome,
                                bare=name in BARE_COMMANDS))
    return result


def tiers() -> List[str]:
    """The tier names, lowest first."""
    return [t.name.capitalize() for t in Tier]
