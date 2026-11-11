import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from tidebot.github import GitHubError
from tidebot.signin import SESSION_TTL, STATE_TTL, OAuthApp, Sessions


def oauth(handler):
    calls = []

    def transport(request):
        calls.append(request)
        return handler(request)

    return calls, OAuthApp("cid", "csecret", httpx.Client(transport=httpx.MockTransport(transport)))


def test_authorize_url_asks_for_read_user_only():
    _, app = oauth(lambda r: httpx.Response(500))
    url = urlparse(app.authorize_url("st", "https://bot.test/auth/callback"))
    assert url.netloc == "github.com" and url.path == "/login/oauth/authorize"
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert q == {"client_id": "cid", "redirect_uri": "https://bot.test/auth/callback",
                 "scope": "read:user", "state": "st", "allow_signup": "false"}


def test_exchange_trades_the_code_for_a_token():
    calls, app = oauth(lambda r: httpx.Response(200, json={"access_token": "gho_x"}))
    assert app.exchange("c0de", "https://bot.test/cb") == "gho_x"
    sent = parse_qs(calls[0].content.decode())
    assert sent["code"] == ["c0de"] and sent["client_secret"] == ["csecret"]
    assert calls[0].headers["Accept"] == "application/json"


def test_a_bad_code_raises():
    _, app = oauth(lambda r: httpx.Response(200, json={"error": "bad_verification_code"}))
    with pytest.raises(GitHubError, match="bad_verification_code"):
        app.exchange("old", "https://bot.test/cb")


def test_login_and_push_access():
    def handler(r):
        assert r.headers["Authorization"] == "token gho_x"
        if r.url.path == "/user":
            return httpx.Response(200, json={"login": "alice"})
        if r.url.path == "/repos/o/r":
            return httpx.Response(200, json={"permissions": {"push": True}})
        if r.url.path == "/repos/o/read-only":
            return httpx.Response(200, json={"permissions": {"push": False}})
        return httpx.Response(404, json={})

    _, app = oauth(handler)
    assert app.login("gho_x") == "alice"
    assert app.can_push("gho_x", "o/r") is True
    assert app.can_push("gho_x", "o/read-only") is False
    assert app.can_push("gho_x", "o/secret") is False


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_state_works_once_and_expires():
    clock = Clock()
    s = Sessions(clock)
    state = s.new_state("https://dash.test/dashboard.html")
    assert s.take_state(state) == "https://dash.test/dashboard.html"
    assert s.take_state(state) is None
    late = s.new_state("x")
    clock.now += STATE_TTL + 1
    assert s.take_state(late) is None
    assert s.take_state("") is None


def test_sessions_last_a_day_and_can_end():
    clock = Clock()
    s = Sessions(clock)
    sid = s.start("alice", "gho_x")
    assert s.get(sid)["login"] == "alice"
    assert s.get("guess") is None and s.get(None) is None
    s.end(sid)
    assert s.get(sid) is None
    sid = s.start("bob", "gho_y")
    clock.now += SESSION_TTL + 1
    assert s.get(sid) is None
