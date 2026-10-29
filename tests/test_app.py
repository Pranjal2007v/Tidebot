import json

from fastapi.testclient import TestClient

from tidebot.app import create_app
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
