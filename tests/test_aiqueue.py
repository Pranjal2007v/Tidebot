import threading

from tidebot.aiqueue import AIQueue, waiting_note


def test_jobs_run_in_order_and_report_how_many_are_ahead():
    q = AIQueue(client="model")
    gate = threading.Event()
    seen = []

    def first(ai):
        gate.wait(5)
        seen.append(("first", ai))

    assert q.submit(first) == 0
    assert q.submit(lambda ai: seen.append(("second", ai))) == 1
    assert q.submit(lambda ai: seen.append(("third", ai))) == 2
    assert q.pending == 3
    gate.set()
    q.join()
    assert seen == [("first", "model"), ("second", "model"), ("third", "model")]
    assert q.pending == 0
    assert q.submit(lambda ai: None) == 0
    q.join()


def test_a_failing_job_does_not_stop_the_queue(capsys):
    q = AIQueue(client=None)
    seen = []

    def boom(ai):
        raise RuntimeError("model fell over")

    q.submit(boom)
    q.submit(lambda ai: seen.append("after"))
    q.join()
    assert seen == ["after"]
    assert "model fell over" in capsys.readouterr().out


def test_waiting_note():
    assert waiting_note("ask", 0) is None
    assert waiting_note("ask", 1) == ("`/ask` is queued behind 1 other AI job; "
                                      "the answer will be posted here.")
    assert "behind 3 other AI jobs" in waiting_note("summarize", 3)


def test_an_installation_with_its_own_model_shares_the_line():
    q = AIQueue(client="server model")
    own = q.using("their model")
    gate = threading.Event()
    seen = []
    assert q.submit(lambda ai: gate.wait(5)) == 0
    assert own.submit(lambda ai: seen.append(ai), "o/r") == 1
    assert q.submit(lambda ai: seen.append(ai)) == 2
    assert q.pending == 3
    gate.set()
    q.join()
    assert seen == ["their model", "server model"]


def test_the_wait_hook_hears_about_jobs_on_another_model():
    waited = []
    q = AIQueue(client=None, on_wait=lambda repo, s: waited.append(repo))
    q.using("their model").submit(lambda ai: None, "o/r")
    q.join()
    assert waited == ["o/r"]
