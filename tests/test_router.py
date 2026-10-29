from tidebot.commands import Command
from tidebot.config import TideConfig
from tidebot.ratelimit import RateLimiter
from tidebot.router import route_comment
from tidebot.state import StateStore


def limiter(per_user=10):
    return RateLimiter(StateStore(None), per_user=per_user, clock=lambda: 0.0)


def test_allowed_and_denied_commands():
    body = ":tide /ask what?\n:tide /merge\n:tide /teleport"
    actions = route_comment("o/r", "alice", body, "read", limiter())
    assert [(a.command.name, a.allowed) for a in actions] == [
        ("ask", True), ("merge", False), ("teleport", False),
    ]
    assert "maintainer" in actions[1].reason


def test_bare_lgtm_for_collaborator():
    actions = route_comment("o/r", "bob", "nice\n/lgtm", "triage", limiter())
    assert actions[0].command == Command("lgtm", bare=True)
    assert actions[0].allowed


def test_bots_are_ignored():
    assert route_comment("o/r", "tidebot[bot]", ":tide /help", "admin", limiter()) == []


def test_rate_limit_applies_after_permission():
    rl = limiter(per_user=1)
    body = ":tide /merge\n:tide /help\n:tide /help"
    actions = route_comment("o/r", "alice", body, "read", rl)
    assert [a.allowed for a in actions] == [False, True, False]
    assert actions[2].reason == "rate limited, try again in 60 min"


def test_star_gate_from_config():
    gated = TideConfig(star_gate=True)
    assert not route_comment("o/r", "a", ":tide /ask x", "read", limiter(), gated)[0].allowed
    assert route_comment("o/r", "a", ":tide /ask x", "read", limiter(), gated, starred=True)[0].allowed
