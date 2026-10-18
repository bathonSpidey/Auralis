"""A single-worker job queue.

Runs take one to a few minutes and the Pi has one Claude login and little
memory, so jobs run one at a time. State lives in memory only; anything worth
keeping (a real creation) is written to the Store by the runner.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"


class QueueFull(RuntimeError):
    pass


@dataclass
class Job:
    id: str
    kind: str  # playlist | song | commit
    prompt: str = ""
    depth: str = "auto"
    device_id: Optional[str] = None
    preview: bool = False
    parent: Optional[str] = None  # the preview a commit job turns real
    status: str = QUEUED
    stage: str = ""
    events: List[dict] = field(default_factory=list)
    created_at: float = 0.0
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    committed: bool = False


Runner = Callable[[Job, Callable[[str], None]], dict]


class JobQueue:
    def __init__(
        self,
        runner: Runner,
        max_queued: int = 3,
        keep: int = 30,
        clock: Callable[[], float] = time.time,
        autostart: bool = True,
    ):
        self.runner = runner
        self.max_queued = max_queued
        self.keep = keep
        self.clock = clock
        self._jobs: Dict[str, Job] = {}
        self._order: List[str] = []
        self._pending: List[str] = []
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._closed = False
        self._thread = threading.Thread(target=self._work, daemon=True, name="jobs")
        if autostart:
            self._thread.start()

    # ── public ──────────────────────────────────────────────────────────
    def submit(self, kind: str, **fields) -> Job:
        with self._lock:
            if len(self._pending) >= self.max_queued:
                raise QueueFull("The queue is full; wait for a run to finish.")
            job = Job(
                id=uuid.uuid4().hex[:12], kind=kind, created_at=self.clock(), **fields
            )
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._pending.append(job.id)
            self._trim()
            self._wake.notify()
            return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def snapshot(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._view(job) if job else None

    def recent(self) -> List[dict]:
        with self._lock:
            return [self._view(self._jobs[i]) for i in reversed(self._order)]

    def claim_commit(self, job_id: str) -> Job:
        """Mark a finished preview as being created, once."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status != DONE or not job.preview or not job.result:
                raise ValueError("Only a finished preview can be created")
            if job.committed:
                raise ValueError("This preview was already created")
            job.committed = True
            return job

    def release_commit(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].committed = False

    def discard(self, job_id: str) -> bool:
        """Cancel a queued job or drop a finished one. A running job cannot be
        stopped (its Claude process is mid-flight)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status == RUNNING:
                return False
            if job_id in self._pending:
                self._pending.remove(job_id)
            del self._jobs[job_id]
            self._order.remove(job_id)
            return True

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._wake.notify_all()

    # ── worker ──────────────────────────────────────────────────────────
    def run_pending(self) -> bool:
        """Run the next queued job in the calling thread (used by tests)."""
        with self._lock:
            if not self._pending:
                return False
            job = self._jobs[self._pending.pop(0)]
        self._run(job)
        return True

    def _work(self) -> None:
        while True:
            with self._lock:
                while not self._pending and not self._closed:
                    self._wake.wait()
                if self._closed:
                    return
                job = self._jobs[self._pending.pop(0)]
            self._run(job)

    def _run(self, job: Job) -> None:
        with self._lock:
            job.status = RUNNING
            job.started_at = self.clock()

        def progress(stage: str) -> None:
            with self._lock:
                job.stage = stage
                job.events.append({"stage": stage, "at": self.clock()})

        try:
            result = self.runner(job, progress)
        except (
            Exception
        ) as e:  # the page shows the message; nothing may kill the worker
            with self._lock:
                job.status, job.error = FAILED, _message(e)
                job.finished_at = self.clock()
            return
        with self._lock:
            job.status, job.result = DONE, result
            job.finished_at = self.clock()

    # ── internals ───────────────────────────────────────────────────────
    def _view(self, job: Job) -> dict:
        return {
            "id": job.id,
            "kind": job.kind,
            "prompt": job.prompt,
            "depth": job.depth,
            "preview": job.preview,
            "parent": job.parent,
            "status": job.status,
            "stage": job.stage,
            "events": list(job.events),
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "result": job.result,
            "error": job.error,
            "committed": job.committed,
        }

    def _trim(self) -> None:
        """Forget the oldest finished jobs so memory stays flat."""
        finished = [i for i in self._order if self._jobs[i].status in (DONE, FAILED)]
        for job_id in finished[: max(0, len(finished) - self.keep)]:
            del self._jobs[job_id]
            self._order.remove(job_id)


def _message(error: Exception) -> str:
    text = str(error).strip() or type(error).__name__
    return text[:400]
