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
