from fastapi.testclient import TestClient

from tidebot.aiqueue import AIQueue
from tidebot.app import create_app
from tidebot.metrics import MAX_WAITS, Metrics
from tidebot.state import StateStore


def test_report_combines_command_counts_and_queue_waits():
    store = StateStore(None)
    store.set("stats", {"o/r": {"ping": 1, "review": 3, "ask": 1}, "x/y": {"help": 9}})
    m = Metrics(store)
    for seconds in (0.04, 2.0, 7.26):
        m.record_wait("o/r", seconds)
    report = m.report("o/r")
    assert report["commands"] == {"total": 5, "by_command": {"review": 3, "ask": 1, "ping": 1}}
    assert report["queue"] == {"jobs": 3, "median_wait": 2.0, "max_wait": 7.3}


def test_empty_repo_reports_zeros():
    report = Metrics(StateStore(None)).report("o/r")
    assert report["commands"]["total"] == 0
    assert report["queue"] == {"jobs": 0, "median_wait": None, "max_wait": None}


def test_only_recent_waits_are_kept_and_unknown_repos_are_skipped():
    store = StateStore(None)
    m = Metrics(store)
    for i in range(MAX_WAITS + 5):
        m.record_wait("o/r", i)
    m.record_wait("", 1.0)
    waits = store.get("metrics")["o/r"]["queue_waits"]
    assert len(waits) == MAX_WAITS and waits[0] == 5
    assert list(store.get("metrics")) == ["o/r"]


def test_queue_reports_how_long_each_job_waited():
    # Clock reads: first submit, its start, second submit, its start.
    ticks = iter([10.0, 12.5, 20.0, 20.25])
    waited = []
    q = AIQueue(client=None, on_wait=lambda repo, s: waited.append((repo, s)),
                clock=lambda: next(ticks))
    q.submit(lambda model: None, "o/r")
    q.join()
    q.submit(lambda model: None)
    q.join()
    assert waited == [("o/r", 2.5), ("", 0.25)]


def test_a_failing_wait_hook_does_not_drop_the_job():
    ran = []

    def hook(repo, seconds):
        raise RuntimeError("boom")

    q = AIQueue(client=None, on_wait=hook)
    q.submit(lambda model: ran.append(True), "o/r")
    q.join()
    assert ran == [True]


def test_stats_endpoint_is_off_without_a_token():
    c = TestClient(create_app("s", StateStore(None)))
    assert c.get("/api/stats/o/r").status_code == 404


def test_stats_endpoint_needs_the_token():
    store = StateStore(None)
    store.set("stats", {"o/r": {"ping": 2}})
    c = TestClient(create_app("s", store, stats_token="t0ken"))
    assert c.get("/api/stats/o/r").status_code == 401
    assert c.get("/api/stats/o/r", headers={"Authorization": "Bearer nope"}).status_code == 401
    res = c.get("/api/stats/o/r", headers={"Authorization": "Bearer t0ken"})
    assert res.status_code == 200
    assert res.json()["repo"] == "o/r" and res.json()["commands"]["total"] == 2


def test_app_records_waits_from_its_ai_queue():
    store = StateStore(None)
    q = AIQueue(client=None)
    create_app("s", store, ai=q)
    q.submit(lambda model: None, "o/r")
    q.join()
    assert Metrics(store).report("o/r")["queue"]["jobs"] == 1
