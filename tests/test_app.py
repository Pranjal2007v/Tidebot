import json

import pytest
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
    assert client().get("/healthz").json() == {"ok": True, "ai": {"on": False, "queued": 0}}


def test_healthz_reports_the_ai_queue_length():
    import threading

    from tidebot.aiqueue import AIQueue

    queue = AIQueue(client=None)
    c = TestClient(create_app(SECRET, StateStore(None), ai=queue))
    assert c.get("/healthz").json()["ai"] == {"on": True, "queued": 0}
    gate = threading.Event()
    queue.submit(lambda model: gate.wait(5))
    queue.submit(lambda model: None)
    assert c.get("/healthz").json()["ai"] == {"on": True, "queued": 2}
    gate.set()
    queue.join()
    assert c.get("/healthz").json()["ai"] == {"on": True, "queued": 0}


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


def test_community_commands_reply():
    gh = FakeGitHub()
    c, _ = acting_client(gh)
    post(c, "issue_comment", issue_payload(":tide /ping"))
    assert gh.calls == [("post_comment", "o/r", 3, "pong")]


def test_remind_is_saved_and_posted_on_startup_once_due():
    store = StateStore(None)
    gh = FakeGitHub(permission="triage")
    app = create_app(SECRET, store, github=lambda installation: gh)
    c = TestClient(app)
    post(c, "issue_comment", issue_payload(":tide /remind 1m rerun CI"))
    assert gh.calls == [("post_comment", "o/r", 3, "OK @alice, I'll remind you here in 1m.")]
    (saved,) = store.get("reminders")
    assert saved["installation"] == 99
    # Make it due, then start the app: startup posts what came due while down.
    saved["due"] = 0
    store.set("reminders", [saved])
    with TestClient(create_app(SECRET, store, github=lambda installation: gh)):
        pass
    assert gh.calls[-1] == ("post_comment", "o/r", 3,
                            "@alice, you asked me to remind you: rerun CI")
    assert store.get("reminders") == []


def test_stats_counts_only_allowed_commands():
    store = StateStore(None)
    gh = FakeGitHub(permission=None)
    c = TestClient(create_app(SECRET, store, github=lambda installation: gh))
    post(c, "issue_comment", issue_payload(":tide /ping\n:tide /merge"))
    post(c, "issue_comment", issue_payload(":tide /stats"))
    assert store.get("stats") == {"o/r": {"ping": 1, "stats": 1}}
    assert "2 commands run" in gh.calls[-1][3]


def test_new_pr_is_welcomed():
    gh = FakeGitHub(config="size_labels: false\npr_lint: false\n")
    c, installs = acting_client(gh)
    res = post(c, "pull_request", {
        "action": "opened", "repository": {"full_name": "o/r"}, "installation": {"id": 99},
        "pull_request": {"number": 8, "user": {"login": "alice"}},
    })
    assert res.json()["handled"] == "pull_request"
    assert installs == [99]
    (call,) = gh.calls
    assert call[:3] == ("post_comment", "o/r", 8) and "@alice" in call[3]


def test_pr_events_without_credentials_are_ignored():
    res = post(client(), "pull_request", {"action": "opened", "pull_request": {"number": 1}})
    assert res.json()["ignored"] == "pull_request"


def test_push_to_pr_relabels_size():
    class Labels(FakeGitHub):
        def add_labels(self, repo, number, labels):
            self.calls.append(("add_labels", repo, number, list(labels)))

    gh = Labels()
    c, _ = acting_client(gh)
    post(c, "pull_request", {
        "action": "synchronize", "repository": {"full_name": "o/r"}, "installation": {"id": 99},
        "pull_request": {"number": 8, "user": {"login": "alice"}, "additions": 12,
                         "deletions": 0, "labels": []},
    })
    assert gh.calls == [("add_labels", "o/r", 8, ["size/S"])]


def test_new_issue_gets_triage_label():
    class Labels(FakeGitHub):
        def add_labels(self, repo, number, labels):
            self.calls.append(("add_labels", repo, number, list(labels)))

    gh = Labels()
    c, _ = acting_client(gh)
    res = post(c, "issues", {
        "action": "opened", "repository": {"full_name": "o/r"}, "installation": {"id": 99},
        "issue": {"number": 5},
    })
    assert res.json()["handled"] == "issues"
    assert gh.calls == [("add_labels", "o/r", 5, ["triage"])]


def test_comment_claiming_an_issue_assigns_it():
    class Assigns(FakeGitHub):
        def add_assignees(self, repo, number, logins):
            self.calls.append(("add_assignees", repo, number, list(logins)))

    gh = Assigns()
    c, _ = acting_client(gh)
    res = post(c, "issue_comment", issue_payload("Hi, I'd like to work on this!", login="bob"))
    assert res.json()["replied"] is True
    assert gh.calls[0] == ("add_assignees", "o/r", 3, ["bob"])
    assert gh.calls[1][3].startswith("Thanks @bob")


def test_ai_command_without_a_model_says_so():
    gh = FakeGitHub()
    c, _ = acting_client(gh)
    post(c, "issue_comment", issue_payload(":tide /ask where is auth?"))
    assert gh.calls == [("post_comment", "o/r", 3,
                         "`/ask`: AI commands are off here: this Tidebot has no model configured.")]


def test_ai_command_is_queued_and_posts_its_answer():
    from tidebot.aiqueue import AIQueue

    class Model:
        def ask(self, system, user, **kwargs):
            return "It is in app.py."

    class Issues(FakeGitHub):
        def issue(self, repo, number):
            return {"title": "Where is auth?", "body": ""}

    gh = Issues()
    queue = AIQueue(Model())
    c = TestClient(create_app(SECRET, StateStore(None), github=lambda i: gh, ai=queue))
    res = post(c, "issue_comment", issue_payload(":tide /ask where is auth?\n:tide /ask"))
    queue.join()
    assert res.json()["replied"] is True
    # The usage reply goes out with the webhook; the answer comes from the
    # worker thread, so either may land first.
    assert sorted(gh.calls) == [
        ("post_comment", "o/r", 3, "Usage: `:tide /ask where is auth handled?`"),
        ("post_comment", "o/r", 3, "`/ask` for @alice:\n\nIt is in app.py."),
    ]


class NamedModel:
    def __init__(self, name):
        self.name = name

    def ask(self, system, user, **kwargs):
        return f"answered by {self.name}"


class AskGitHub(FakeGitHub):
    def issue(self, repo, number):
        return {"title": "Where is auth?", "body": ""}


def ask_as(installation, queue, ai_clients):
    gh = AskGitHub()
    c = TestClient(create_app(SECRET, StateStore(None), github=lambda i: gh, ai=queue,
                              ai_clients=ai_clients))
    payload = issue_payload(":tide /ask where is auth?")
    payload["installation"] = {"id": installation}
    post(c, "issue_comment", payload)
    queue.join()
    return gh.calls


def test_an_installation_with_its_own_model_is_answered_by_it():
    from tidebot.aiqueue import AIQueue

    clients = {7: NamedModel("theirs")}
    assert ask_as(7, AIQueue(NamedModel("the server's")), clients) == [
        ("post_comment", "o/r", 3, "`/ask` for @alice:\n\nanswered by theirs")]
    assert ask_as(99, AIQueue(NamedModel("the server's")), clients) == [
        ("post_comment", "o/r", 3, "`/ask` for @alice:\n\nanswered by the server's")]


def test_only_listed_installations_get_ai_when_the_server_has_no_model():
    from tidebot.aiqueue import AIQueue

    clients = {7: NamedModel("theirs")}
    assert ask_as(7, AIQueue(None), clients) == [
        ("post_comment", "o/r", 3, "`/ask` for @alice:\n\nanswered by theirs")]
    assert ask_as(99, AIQueue(None), clients) == [
        ("post_comment", "o/r", 3,
         "`/ask`: AI commands are off here: this Tidebot has no model configured.")]


def test_new_issue_duplicates_check_uses_the_installations_model():
    from tidebot.aiqueue import AIQueue

    asked = []

    class Says:
        def __init__(self, name):
            self.name = name

        def ask(self, system, user, **kwargs):
            asked.append(self.name)
            return "yes"

    class Issues(FakeGitHub):
        def open_issues(self, repo):
            return [{"number": 1, "title": "Webhook crashes on startup",
                     "body": "Crash when state file is missing on first run."},
                    {"number": 2, "title": "Receiver fails when the state file is missing",
                     "body": "Starting the receiver errors out."},
                    {"number": 3, "title": "Add dark mode to dashboard",
                     "body": "Please add a dark theme."}]

        def repo_labels(self, repo):
            return []

        def add_labels(self, repo, number, labels):
            pass

    gh = Issues()
    queue = AIQueue(Says("the server's"))
    c = TestClient(create_app(SECRET, StateStore(None), github=lambda i: gh, ai=queue,
                              ai_clients={7: Says("theirs")}))
    post(c, "issues", {
        "action": "opened", "repository": {"full_name": "o/r"}, "installation": {"id": 7},
        "issue": {"number": 9, "title": "Webhook crashes on startup",
                  "body": "The receiver crashes when the state file is missing."}})
    queue.join()
    assert asked == ["theirs"]


def test_queue_and_installation_models_come_from_the_environment(tmp_path):
    from tidebot.app import _ai_from_env
    from tidebot.installations import InstallationsError

    assert _ai_from_env({}) == (None, {})
    queue, clients = _ai_from_env({"TIDEBOT_AI_URL": "https://a.example/v1",
                                   "TIDEBOT_AI_MODEL": "m"})
    assert queue.client.model == "m" and clients == {}

    path = tmp_path / "installations.json"
    path.write_text('{"7": {"ai_url": "https://b.example/v1", "ai_model": "theirs"}}')
    queue, clients = _ai_from_env({"TIDEBOT_INSTALLATIONS": str(path)})
    assert queue is not None and queue.client is None
    assert clients[7].model == "theirs"

    path.write_text("{")
    with pytest.raises(InstallationsError):
        _ai_from_env({"TIDEBOT_INSTALLATIONS": str(path)})


def test_an_installation_at_its_cap_is_told_and_nothing_is_queued():
    import threading

    from tidebot.aiqueue import AIQueue

    gate = threading.Event()
    queue = AIQueue(NamedModel("the server's"), per_installation=1)
    queue.using(None, installation=7).submit(lambda ai: gate.wait(5))
    gh = AskGitHub()
    c = TestClient(create_app(SECRET, StateStore(None), github=lambda i: gh, ai=queue))
    payload = issue_payload(":tide /ask where is auth?")
    payload["installation"] = {"id": 7}
    post(c, "issue_comment", payload)
    assert gh.calls == [("post_comment", "o/r", 3,
                         "`/ask` wasn't queued: this installation already has 1 AI job "
                         "waiting. Try again once those answers are posted.")]
    assert queue.pending == 1
    gate.set()
    queue.join()
    # Another installation was never blocked, and 7 gets in once its job is done.
    assert ask_as(8, queue, {}) == [
        ("post_comment", "o/r", 3, "`/ask` for @alice:\n\nanswered by the server's")]
    assert ask_as(7, queue, {}) == [
        ("post_comment", "o/r", 3, "`/ask` for @alice:\n\nanswered by the server's")]


def test_the_cap_comes_from_the_environment():
    from tidebot.app import MAX_PER_INSTALLATION, _ai_from_env, per_installation_cap

    model = {"TIDEBOT_AI_URL": "https://a.example/v1", "TIDEBOT_AI_MODEL": "m"}
    assert _ai_from_env(model)[0].per_installation == MAX_PER_INSTALLATION == 5
    assert _ai_from_env(dict(model, TIDEBOT_AI_MAX_PER_INSTALLATION="2"))[0].per_installation == 2
    assert per_installation_cap({"TIDEBOT_AI_MAX_PER_INSTALLATION": "0"}) == 0
    for bad in ("-1", "lots", "2.5"):
        with pytest.raises(ValueError, match="whole number"):
            per_installation_cap({"TIDEBOT_AI_MAX_PER_INSTALLATION": bad})


def test_uninstalling_the_app_drops_that_installations_reminders():
    from tidebot.reminders import Reminders

    store = StateStore(None)
    Reminders(store).add("o/r", 3, 7, "alice", 3600, "check CI")
    Reminders(store).add("p/q", 4, 8, "bob", 3600, "")
    c = TestClient(create_app(SECRET, store))
    res = post(c, "installation", {"action": "deleted", "installation": {"id": 7}})
    assert res.json() == {"ok": True, "handled": "installation", "dropped_reminders": 1,
                          "actions": []}
    assert [r.author for r in Reminders(store).pending()] == ["bob"]


def test_other_installation_events_change_nothing():
    from tidebot.reminders import Reminders

    store = StateStore(None)
    Reminders(store).add("o/r", 3, 7, "alice", 3600, "")
    c = TestClient(create_app(SECRET, store))
    for payload in ({"action": "created", "installation": {"id": 7}},
                    {"action": "suspend", "installation": {"id": 7}},
                    {"action": "deleted", "installation": {}}):
        res = post(c, "installation", payload)
        assert res.json()["ignored"] == "installation"
    assert len(Reminders(store).pending()) == 1
