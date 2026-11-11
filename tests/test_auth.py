from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from tidebot.app import SESSION_COOKIE, create_app
from tidebot.github import GitHubError
from tidebot.signin import OAuthApp, Sessions
from tidebot.state import StateStore

DASH = "https://dash.test"


class FakeOAuth(OAuthApp):
    def __init__(self, push=()):
        super().__init__("cid", "csecret")
        self.push = set(push)
        self.checked = []

    def exchange(self, code, redirect_uri):
        if code != "good":
            raise GitHubError(401, "bad_verification_code")
        assert redirect_uri == "https://bot.test/auth/callback"
        return "gho_x"

    def login(self, token):
        return "alice"

    def can_push(self, token, repo):
        self.checked.append(repo)
        return repo in self.push


def app(oauth=None, store=None, **kwargs):
    sessions = Sessions()
    return sessions, TestClient(create_app(
        "s", store or StateStore(None), dashboard_origins=[DASH],
        oauth=oauth or FakeOAuth(), public_url="https://bot.test/",
        sessions=sessions, **kwargs), follow_redirects=False)


def sign_in(c):
    res = c.get("/auth/login", params={"return_to": DASH + "/dashboard.html"})
    state = parse_qs(urlparse(res.headers["location"]).query)["state"][0]
    return c.get("/auth/callback", params={"code": "good", "state": state})


def test_sign_in_is_off_without_an_oauth_app():
    c = TestClient(create_app("s", StateStore(None)))
    assert c.get("/auth/login").status_code == 404
    assert c.get("/auth/me").status_code == 404


def test_login_redirects_to_github_with_the_callback():
    _, c = app()
    res = c.get("/auth/login", params={"return_to": DASH + "/dashboard.html"})
    assert res.status_code == 302
    url = urlparse(res.headers["location"])
    assert url.netloc == "github.com"
    assert parse_qs(url.query)["redirect_uri"] == ["https://bot.test/auth/callback"]


def test_login_only_returns_to_a_dashboard_origin():
    _, c = app()
    for bad in ("https://evil.test/dashboard.html", "", "/dashboard.html"):
        assert c.get("/auth/login", params={"return_to": bad}).status_code == 400


def test_callback_sets_a_session_cookie_and_returns_to_the_dashboard():
    sessions, c = app()
    res = sign_in(c)
    assert res.status_code == 302
    assert res.headers["location"] == DASH + "/dashboard.html"
    cookie = res.headers["set-cookie"]
    assert cookie.startswith(SESSION_COOKIE + "=")
    for flag in ("HttpOnly", "Secure", "SameSite=none"):
        assert flag.lower() in cookie.lower()
    sid = cookie.split(";")[0].split("=", 1)[1]
    assert sessions.get(sid)["login"] == "alice"
    me = c.get("/auth/me", headers={"Cookie": f"{SESSION_COOKIE}={sid}"})
    assert me.json() == {"login": "alice"}


def test_callback_rejects_unknown_states_and_bad_codes():
    _, c = app()
    assert c.get("/auth/callback", params={"code": "good", "state": "made-up"}).status_code == 400
    res = c.get("/auth/login", params={"return_to": DASH})
    state = parse_qs(urlparse(res.headers["location"]).query)["state"][0]
    assert c.get("/auth/callback", params={"code": "bad", "state": state}).status_code == 502
    # The state was used up by the failed try.
    assert c.get("/auth/callback", params={"code": "good", "state": state}).status_code == 400


def test_me_without_a_session_and_logout():
    sessions, c = app()
    assert c.get("/auth/me").status_code == 401
    sid = sign_in(c).headers["set-cookie"].split(";")[0].split("=", 1)[1]
    cookie = {"Cookie": f"{SESSION_COOKIE}={sid}"}
    res = c.post("/auth/logout", headers=cookie)
    assert res.json() == {"ok": True}
    assert SESSION_COOKIE in res.headers["set-cookie"]
    assert c.get("/auth/me", headers=cookie).status_code == 401


def test_dashboard_origin_may_send_its_cookie():
    _, c = app()
    pre = c.options("/auth/me", headers={"Origin": DASH, "Access-Control-Request-Method": "GET"})
    assert pre.headers["access-control-allow-credentials"] == "true"
    assert pre.headers["access-control-allow-origin"] == DASH
