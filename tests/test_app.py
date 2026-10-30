import json

from fastapi.testclient import TestClient

from tidebot.app import create_app
from tidebot.github import GitHubError
from tidebot.state import StateStore
from tidebot.webhook import sign

SECRET = "s3cret"


def client():
    return TestClient(create_app(SECRET, StateStore(None)))


def post(c, event, payload, secret=SECRET):
    body = json.dumps(payload).encode()
    return c.post("/webhook", content=body, headers={
        "X-GitHub-Event": event,
        "X-Hub-Signature-256": sign(secret, body),
        "Content-Type": "application/json",
    })


def comment_payload(body, association="NONE", login="alice", action="created"):
    return {
        "action": action,
        "repository": {"full_name": "o/r"},
        "comment": {"body": body, "author_association": association, "user": {"login": login}},
    }


def test_healthz():
    assert client().get("/healthz").json() == {"ok": True}


def test_bad_signature_is_rejected():
    res = post(client(), "issue_comment", comment_payload(":tide /help"), secret="wrong")
    assert res.status_code == 401


def test_ping():
    res = post(client(), "ping", {"zen": "hi"})
    assert res.status_code == 200
    assert res.json()["actions"] == []


def test_comment_is_routed():
    res = post(client(), "issue_comment", comment_payload(":tide /help\n:tide /merge"))
    assert res.json()["actions"] == [
        {"command": "help", "args": "", "allowed": True, "reason": ""},
        {"command": "merge", "args": "", "allowed": False,
         "reason": "/merge needs maintainer access"},
    ]


def test_owner_may_merge():
    res = post(client(), "issue_comment", comment_payload(":tide /merge", association="OWNER"))
    assert res.json()["actions"][0]["allowed"] is True


def test_other_events_and_edits_are_ignored():
    c = client()
    assert post(c, "push", {}).json()["ignored"] == "push"
    edited = post(c, "issue_comment", comment_payload(":tide /help", action="edited"))
    assert edited.json()["actions"] == []


class FakeGitHub:
    def __init__(self, permission=None, config=None, starred=False):
        self._permission = permission
        self._config = config
        self._starred = starred
        self.calls = []

    def permission(self, repo, login):
        return self._permission

    def fetch_file(self, repo, path):
        return self._config

    def has_starred(self, login, repo):
        self.calls.append(("has_starred", login, repo))
        return self._starred

    def set_state(self, repo, number, state):
        self.calls.append(("set_state", repo, number, state))

    def post_comment(self, repo, number, body):
        self.calls.append(("post_comment", repo, number, body))


def acting_client(gh):
    installs = []

    def factory(installation):
        installs.append(installation)
        return gh

    return TestClient(create_app(SECRET, StateStore(None), github=factory)), installs


def issue_payload(body, login="alice", pull_request=False):
    payload = comment_payload(body, login=login)
    payload["installation"] = {"id": 99}
    payload["issue"] = {"number": 3}
    if pull_request:
        payload["issue"]["pull_request"] = {"url": "..."}
    return payload


def test_maintainer_command_runs_and_denials_get_a_reply():
    gh = FakeGitHub(permission="write")
    c, installs = acting_client(gh)
    res = post(c, "issue_comment", issue_payload(":tide /close\n:tide /teleport"))
    assert installs == [99]
    assert res.json()["replied"] is True
    assert gh.calls == [
        ("set_state", "o/r", 3, "closed"),
        ("post_comment", "o/r", 3, "`/teleport`: unknown command /teleport"),
    ]


def test_help_reply_uses_real_permission():
    gh = FakeGitHub(permission="triage")
    c, _ = acting_client(gh)
    post(c, "issue_comment", issue_payload(":tide /help"))
    (_, _, _, body), = gh.calls
    assert "collaborator access" in body and "`/lgtm`" in body


def test_star_gate_from_repo_config():
    gh = FakeGitHub(config="star_gate: true\n", starred=False)
    c, _ = acting_client(gh)
    res = post(c, "issue_comment", issue_payload(":tide /ask why?"))
    assert res.json()["actions"][0]["reason"] == "star the repo to use Tidebot here"
    assert gh.calls[0] == ("has_starred", "alice", "o/r")


def test_silent_success_posts_nothing():
    gh = FakeGitHub(permission="admin")
    c, _ = acting_client(gh)
    res = post(c, "issue_comment", issue_payload(":tide /close"))
    assert res.json()["replied"] is False
    assert gh.calls == [("set_state", "o/r", 3, "closed")]


def test_github_errors_become_replies():
    class Failing(FakeGitHub):
        def set_state(self, repo, number, state):
            raise GitHubError(403, "forbidden")

    gh = Failing(permission="admin")
    c, _ = acting_client(gh)
    post(c, "issue_comment", issue_payload(":tide /close"))
    assert gh.calls == [("post_comment", "o/r", 3, "`/close` failed: GitHub answered 403")]
