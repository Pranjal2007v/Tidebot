from tidebot.github import GitHubError
from tidebot.reminders import STATE_KEY, Reminder, Reminders, describe, parse_delay
from tidebot.state import StateStore


def test_parse_delay():
    assert parse_delay("2h check CI") == (7200, "check CI")
    assert parse_delay("1h30m") == (5400, "")
    assert parse_delay("1W 2d") == (604800, "2d")
    assert parse_delay("tomorrow") is None
    assert parse_delay("") is None


def test_describe():
    assert describe(5400) == "1h30m"
    assert describe(8 * 86400) == "1w1d"
    assert describe(0) == "0m"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Poster:
    def __init__(self, fail=None):
        self.fail = fail
        self.calls = []

    def post_comment(self, repo, number, body):
        if self.fail:
            raise GitHubError(self.fail, "nope")
        self.calls.append((repo, number, body))


def test_reminders_post_once_when_due(tmp_path):
    clock = Clock()
    reminders = Reminders(StateStore(tmp_path / "state.json"), clock)
    reminders.add("o/r", 5, 99, "alice", 3600, "check CI")
    reminders.add("o/r", 6, 99, "bob", 7200, "")
    installs, poster = [], Poster()

    def factory(installation):
        installs.append(installation)
        return poster

    assert reminders.deliver_due(factory) == 0
    clock.now += 3600
    assert reminders.deliver_due(factory) == 1
    assert poster.calls == [("o/r", 5, "@alice, you asked me to remind you: check CI")]
    assert installs == [99]
    # Saved to disk, so a restart still has bob's reminder.
    again = Reminders(StateStore(tmp_path / "state.json"), clock)
    assert [r.author for r in again.pending()] == ["bob"]
    clock.now += 3600
    assert again.deliver_due(factory) == 1
    assert poster.calls[-1] == ("o/r", 6, "@bob, here is the reminder you asked for.")
    assert again.pending() == []


def test_server_errors_retry_and_client_errors_drop():
    clock = Clock()
    store = StateStore(None)
    reminders = Reminders(store, clock)
    reminders.add("o/r", 5, 99, "alice", 60, "x")
    clock.now += 60
    assert reminders.deliver_due(lambda i: Poster(fail=502)) == 0
    assert len(reminders.pending()) == 1
    assert reminders.deliver_due(lambda i: Poster(fail=404)) == 0
    assert store.get(STATE_KEY) == []


def test_pending_filters_by_repo():
    reminders = Reminders(StateStore(None), Clock())
    reminders.add("o/r", 1, 9, "a", 60, "")
    reminders.add("o/other", 1, 9, "a", 60, "")
    assert [r.repo for r in reminders.pending("o/r")] == ["o/r"]
    assert isinstance(reminders.pending()[0], Reminder)


def test_dropping_an_installation_forgets_only_its_reminders():
    store = StateStore(None)
    reminders = Reminders(store, clock=Clock())
    reminders.add("o/r", 1, 7, "alice", 3600, "one")
    reminders.add("o/r", 2, 8, "bob", 3600, "two")
    reminders.add("x/y", 3, 7, "carol", 7200, "three")
    assert reminders.drop_installation(7) == 2
    assert [r.author for r in reminders.pending()] == ["bob"]
    assert reminders.drop_installation(7) == 0
    assert len(store.get(STATE_KEY)) == 1
