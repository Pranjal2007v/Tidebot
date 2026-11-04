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
from typing import Callable, Optional

from .ai import AIClient

Job = Callable[[AIClient], None]


class AIQueue:
    def __init__(self, client: AIClient):
        self.client = client
        self._jobs: "queue.Queue[Job]" = queue.Queue()
        self._lock = threading.Lock()
        self._pending = 0
        self._worker: Optional[threading.Thread] = None

    @property
    def pending(self) -> int:
        """Jobs waiting or running."""
        with self._lock:
            return self._pending

    def submit(self, job: Job) -> int:
        """Queue ``job`` and return how many jobs are ahead of it."""
        with self._lock:
            ahead = self._pending
            self._pending += 1
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="tidebot-ai",
                                                daemon=True)
                self._worker.start()
        self._jobs.put(job)
        return ahead

    def join(self) -> None:
        """Wait until every queued job has finished."""
        self._jobs.join()

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
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
