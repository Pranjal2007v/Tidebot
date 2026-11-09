"""Run AI work one job at a time.

The README's Architecture section puts an AI queue between the router and
the model so a small server never runs several slow model calls at once.
``AIQueue`` keeps one worker thread that takes jobs in the order they came
in. A job is any function of the ``AIClient``; it posts its own reply when
it is done, so the webhook can answer GitHub right away.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Optional, Tuple

from .ai import AIClient

Job = Callable[[AIClient], None]
# Called with the repo and the seconds a job waited before it started.
WaitHook = Callable[[str, float], None]


class AIQueue:
    def __init__(self, client: AIClient, on_wait: Optional[WaitHook] = None,
                 clock: Callable[[], float] = time.monotonic):
        self.client = client
        self.on_wait = on_wait
        self._clock = clock
        self._jobs: "queue.Queue[Tuple[Job, str, float]]" = queue.Queue()
        self._lock = threading.Lock()
        self._pending = 0
        self._worker: Optional[threading.Thread] = None

    @property
    def pending(self) -> int:
        """Jobs waiting or running."""
        with self._lock:
            return self._pending

    def submit(self, job: Job, repo: str = "") -> int:
        """Queue ``job`` for ``repo`` and return how many jobs are ahead of it."""
        with self._lock:
            ahead = self._pending
            self._pending += 1
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="tidebot-ai",
                                                daemon=True)
                self._worker.start()
        self._jobs.put((job, repo, self._clock()))
        return ahead

    def join(self) -> None:
        """Wait until every queued job has finished."""
        self._jobs.join()

    def _run(self) -> None:
        while True:
            job, repo, queued = self._jobs.get()
            if self.on_wait is not None:
                try:
                    self.on_wait(repo, self._clock() - queued)
                except Exception as err:  # a metrics problem must not drop the job
                    print(f"tidebot: recording the queue wait failed: {err!r}")
            try:
                job(self.client)
            except Exception as err:  # one bad job must not stop the queue
                print(f"tidebot: AI job failed: {err!r}")
            finally:
                with self._lock:
                    self._pending -= 1
                self._jobs.task_done()


def waiting_note(name: str, ahead: int) -> Optional[str]:
    """The reply for a command that has to wait, or None when it runs next."""
    if ahead <= 0:
        return None
    jobs = "job" if ahead == 1 else "jobs"
    return f"`/{name}` is queued behind {ahead} other AI {jobs}; the answer will be posted here."
