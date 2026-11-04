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
