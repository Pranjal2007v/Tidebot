"""Run AI work one job at a time.

The README's Architecture section puts an AI queue between the router and
the model so a small server never runs several slow model calls at once.
``AIQueue`` keeps one worker thread that takes jobs in the order they came
in. A job is any function of the ``AIClient``; it posts its own reply when
it is done, so the webhook can answer GitHub right away.

One queue serves every installation of the App. An installation with its own
model submits through ``queue.using(client)``: its jobs wait in the same line
but run against that client.

So that one busy installation can't fill the line for everyone, the queue can
cap how many jobs each installation has waiting or running at once. A job
over the cap is refused with ``QueueFull`` instead of being queued.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Dict, Optional, Tuple

from .ai import AIClient

Job = Callable[[AIClient], None]
# Called with the repo and the seconds a job waited before it started.
WaitHook = Callable[[str, float], None]
_Entry = Tuple[Job, str, float, Optional[AIClient], Optional[int]]


class QueueFull(Exception):
    """An installation already has as many AI jobs queued as it may."""

    def __init__(self, installation: int, limit: int):
        super().__init__(f"installation {installation} has {limit} AI jobs queued")
        self.installation = installation
        self.limit = limit


class AIQueue:
    def __init__(self, client: Optional[AIClient], on_wait: Optional[WaitHook] = None,
                 clock: Callable[[], float] = time.monotonic,
                 per_installation: int = 0):
        """``per_installation`` caps each installation's jobs; 0 means no cap."""
        self.client = client
        self.on_wait = on_wait
        self.per_installation = per_installation
        self._clock = clock
        self._jobs: "queue.Queue[_Entry]" = queue.Queue()
        self._lock = threading.Lock()
        self._pending = 0
        self._by_installation: Dict[int, int] = {}
        self._worker: Optional[threading.Thread] = None

    @property
    def pending(self) -> int:
        """Jobs waiting or running."""
        with self._lock:
            return self._pending

    def pending_for(self, installation: int) -> int:
        """Jobs waiting or running for one installation."""
        with self._lock:
            return self._by_installation.get(installation, 0)

    def submit(self, job: Job, repo: str = "", client: Optional[AIClient] = None,
               installation: Optional[int] = None) -> int:
        """Queue ``job`` for ``repo`` and return how many jobs are ahead of it.

        The job gets ``client`` when one is given, else the queue's own. With
        an ``installation`` that is already at the cap, nothing is queued and
        ``QueueFull`` is raised.
        """
        with self._lock:
            if installation is not None:
                mine = self._by_installation.get(installation, 0)
                if self.per_installation and mine >= self.per_installation:
                    raise QueueFull(installation, self.per_installation)
                self._by_installation[installation] = mine + 1
            ahead = self._pending
            self._pending += 1
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="tidebot-ai",
                                                daemon=True)
                self._worker.start()
        self._jobs.put((job, repo, self._clock(), client, installation))
        return ahead

    def using(self, client: Optional[AIClient],
              installation: Optional[int] = None) -> "BoundQueue":
        """This queue, with every job run against ``client`` and counted
        against ``installation``'s cap."""
        return BoundQueue(self, client, installation)

    def join(self) -> None:
        """Wait until every queued job has finished."""
        self._jobs.join()

    def _run(self) -> None:
        while True:
            job, repo, queued, client, installation = self._jobs.get()
            if self.on_wait is not None:
                try:
                    self.on_wait(repo, self._clock() - queued)
                except Exception as err:  # a metrics problem must not drop the job
                    print(f"tidebot: recording the queue wait failed: {err!r}")
            try:
                job(client if client is not None else self.client)
            except Exception as err:  # one bad job must not stop the queue
                print(f"tidebot: AI job failed: {err!r}")
            finally:
                with self._lock:
                    self._pending -= 1
                    if installation is not None:
                        left = self._by_installation[installation] - 1
                        if left:
                            self._by_installation[installation] = left
                        else:
                            del self._by_installation[installation]
                self._jobs.task_done()


class BoundQueue:
    """What one installation sees: the shared queue, its client and its cap."""

    def __init__(self, queue: AIQueue, client: Optional[AIClient],
                 installation: Optional[int] = None):
        self.queue = queue
        self.client = client
        self.installation = installation

    def submit(self, job: Job, repo: str = "") -> int:
        return self.queue.submit(job, repo, self.client, self.installation)


def waiting_note(name: str, ahead: int) -> Optional[str]:
    """The reply for a command that has to wait, or None when it runs next."""
    if ahead <= 0:
        return None
    jobs = "job" if ahead == 1 else "jobs"
    return f"`/{name}` is queued behind {ahead} other AI {jobs}; the answer will be posted here."


def full_note(name: str, limit: int) -> str:
    """The reply for a command refused because its installation is at the cap."""
    jobs = "job" if limit == 1 else "jobs"
    return (f"`/{name}` wasn't queued: this installation already has {limit} AI {jobs} "
            "waiting. Try again once those answers are posted.")
