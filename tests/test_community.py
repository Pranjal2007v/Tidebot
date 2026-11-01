import random

from tidebot.commands import Command
from tidebot.community import JOKES, KUDOS_KEY, Community
from tidebot.state import StateStore
from tidebot.workflow import Target

ISSUE = Target("o/r", 5, is_pr=False, author="alice")


def community():
    return Community(StateStore(None), clock=lambda: 1000.0, rng=random.Random(1))


def run(c, name, args="", target=ISSUE):
    return c.run(None, target, Command(name, args))


def test_handles_only_its_commands():
    c = community()
    assert c.handles("ping") and c.handles("kudos")
    assert not c.handles("merge")


def test_ping_and_joke():
    c = community()
    assert run(c, "ping") == "pong"
    assert run(c, "joke") in JOKES


def test_kudos_counts_per_login():
    c = community()
    first = run(c, "kudos", "@Bob for the quick fix")
    assert first.startswith("Kudos to @Bob from @alice for the quick fix")
    assert "thanked 1 time here" in first
    second = run(c, "kudos", "@bob great review")
    assert "from @alice: great review" in second
    assert "thanked 2 times" in second
    assert c.store.get(KUDOS_KEY) == {"o/r": {"bob": 2}}


def test_kudos_needs_someone_else():
    c = community()
    assert "Usage" in run(c, "kudos")
    assert "Usage" in run(c, "kudos", "bob")
    assert "someone else" in run(c, "kudos", "@Alice")
    assert c.store.get(KUDOS_KEY) is None


PR = Target("o/r", 6, is_pr=True, author="alice")


class SizeGitHub:
    def __init__(self, additions, deletions, labels=()):
        self.pr = {"additions": additions, "deletions": deletions,
                   "labels": [{"name": n} for n in labels]}
        self.calls = []

    def pull(self, repo, number):
        return self.pr

    def add_labels(self, repo, number, labels):
        self.calls.append(("add_labels", repo, number, list(labels)))

    def remove_label(self, repo, number, label):
        self.calls.append(("remove_label", repo, number, label))


def test_size_relabels_pr():
    gh = SizeGitHub(40, 5, labels=["bug", "size/XS"])
    reply = community().run(gh, PR, Command("size"))
    assert gh.calls == [("remove_label", "o/r", 6, "size/XS"),
                        ("add_labels", "o/r", 6, ["size/M"])]
    assert reply == "This PR changes 45 lines: `size/M`."


def test_size_keeps_a_correct_label_and_refuses_issues():
    gh = SizeGitHub(1, 0, labels=["size/XS"])
    assert community().run(gh, PR, Command("size")) == "This PR changes 1 line: `size/XS`."
    assert gh.calls == []
    assert "pull requests" in run(community(), "size")


def as_user(login):
    return Target("o/r", 5, is_pr=False, author=login)


def test_vote_open_cast_change_and_close():
    c = community()
    assert "Usage" in run(c, "vote")
    assert "no open vote" in run(c, "vote", "yes")
    assert "Vote opened: **Drop Python 3.8?**" in run(c, "vote", "Drop Python 3.8?")
    assert "already open" in run(c, "vote", "Another question?")
    run(c, "vote", "yes", as_user("bob"))
    run(c, "vote", "+1", as_user("Carol"))
    assert run(c, "vote", "no", as_user("dave")) == (
        "Vote so far on **Drop Python 3.8?**: 2 yes, 1 no.")
    # Changing your mind replaces your ballot instead of adding one.
    run(c, "vote", "No", as_user("carol"))
    assert run(c, "vote") == "Vote so far on **Drop Python 3.8?**: 1 yes, 2 no."
    assert run(c, "vote", "close") == "Vote closed on **Drop Python 3.8?**: 1 yes, 2 no."
    assert "no open vote" in run(c, "vote", "close")


def test_votes_are_per_issue():
    c = community()
    run(c, "vote", "Ship it?")
    assert "no open vote" in c.run(None, PR, Command("vote", "yes"))
