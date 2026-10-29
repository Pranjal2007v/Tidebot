import json

from tidebot.ratelimit import RateLimiter
from tidebot.state import StateStore


class FakeClock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def make(per_user=10, per_repo=50, path=None, clock=None):
    return RateLimiter(StateStore(path), per_user=per_user, per_repo=per_repo,
                       clock=clock or FakeClock())


def test_user_limit():
    limiter = make(per_user=3)
    assert all(limiter.hit("o/r", "alice").allowed for _ in range(3))
    verdict = limiter.hit("o/r", "alice")
    assert not verdict.allowed
    assert verdict.retry_after == 3600


def test_user_limit_is_case_insensitive_and_per_repo():
    limiter = make(per_user=1)
    assert limiter.hit("o/r", "Alice").allowed
    assert not limiter.hit("o/r", "alice").allowed
    assert limiter.hit("o/other", "alice").allowed


def test_repo_limit_across_users():
    limiter = make(per_user=10, per_repo=2)
    assert limiter.hit("o/r", "a").allowed
    assert limiter.hit("o/r", "b").allowed
    assert not limiter.hit("o/r", "c").allowed


def test_window_slides():
    clock = FakeClock()
    limiter = make(per_user=2, clock=clock)
    limiter.hit("o/r", "a")
    clock.now += 1800
    limiter.hit("o/r", "a")
    assert not limiter.hit("o/r", "a").allowed
    clock.now += 1800  # the first command is now an hour old
    assert limiter.hit("o/r", "a").allowed
    verdict = limiter.hit("o/r", "a")
    assert not verdict.allowed
    assert verdict.retry_after == 1800


def test_denied_hits_are_not_counted():
    clock = FakeClock()
    limiter = make(per_user=1, clock=clock)
    limiter.hit("o/r", "a")
    for _ in range(5):
        limiter.hit("o/r", "a")
    clock.now += 3600
    assert limiter.hit("o/r", "a").allowed


def test_counts_survive_restart(tmp_path):
    path = tmp_path / "state.json"
    clock = FakeClock()
    make(per_user=1, path=path, clock=clock).hit("o/r", "a")
    assert not make(per_user=1, path=path, clock=clock).hit("o/r", "a").allowed


def test_state_store_round_trip_and_bad_file(tmp_path):
    path = tmp_path / "state.json"
    StateStore(path).set("k", {"v": 1})
    assert json.loads(path.read_text()) == {"k": {"v": 1}}
    assert StateStore(path).get("k") == {"v": 1}
    path.write_text("{not json")
    assert StateStore(path).get("k") is None
    assert list(tmp_path.iterdir()) == [path]  # no temp files left behind
