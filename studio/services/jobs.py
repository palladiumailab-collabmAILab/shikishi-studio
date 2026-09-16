from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Condition, Event, Thread
from typing import TYPE_CHECKING, Protocol

from studio.schemas import GeneratedImage, GenerateRequest, JobResponse

if TYPE_CHECKING:
    from studio.services.registry import ModelSpec

logger = logging.getLogger(__name__)


class GenerationEngine(Protocol):
    """Minimal generation boundary used by the queue.

    Keeping this interface independent from the Diffusers-backed implementation
    lets queue state and failure handling be tested without importing ML code.
    """

    @property
    def is_ready(self) -> bool: ...

    def generate(self, request: GenerateRequest, model: ModelSpec) -> list[GeneratedImage]: ...


class ModelResolver(Protocol):
    """Resolve a request's model without coupling queue code to the registry."""

    def get(self, model_id: str | None) -> ModelSpec: ...


@dataclass(slots=True)
class GenerationJob:
    id: str
    request: GenerateRequest
    model: ModelSpec
    status: str = "queued"
    progress: float = 0.0
    message: str | None = "待機中"
    images: list[GeneratedImage] = field(default_factory=list)
    error: str | None = None
    finished_at: float | None = None

    def response(self) -> JobResponse:
        return JobResponse(
            id=self.id,
            status=self.status,
            progress=self.progress,
            message=self.message,
            images=self.images,
            error=self.error,
        )


class GenerationQueue:
    """A bounded, single-worker queue for GPU generation requests.

    Capacity is measured from the pending deque rather than from tombstones in
    a ``queue.Queue``. A cancellation therefore frees its slot atomically,
    even when the worker has not started yet.
    """

    def __init__(
        self,
        generator: GenerationEngine,
        registry: ModelResolver,
        max_size: int,
        *,
        job_retention_seconds: float = 24 * 60 * 60,
        max_completed_jobs: int = 200,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_size < 1:
            raise ValueError("max_size must be at least 1")
        if job_retention_seconds < 0:
            raise ValueError("job_retention_seconds must not be negative")
        if max_completed_jobs < 0:
            raise ValueError("max_completed_jobs must not be negative")
        self._generator = generator
        self._registry = registry
        self._max_size = max_size
        self._job_retention_seconds = job_retention_seconds
        self._max_completed_jobs = max_completed_jobs
        self._clock = clock
        self._pending: deque[str] = deque()
        self._jobs: dict[str, GenerationJob] = {}
        self._condition = Condition()
        self._shutdown = Event()
        self._worker = Thread(target=self._work, name="generation-worker", daemon=True)
        self._active_job_id: str | None = None

    def start(self) -> None:
        self._worker.start()

    def stop(self) -> None:
        self._shutdown.set()
        with self._condition:
            self._condition.notify_all()
        if self._worker.is_alive():
            self._worker.join(timeout=5)

    def submit(self, request: GenerateRequest) -> JobResponse:
        model = self._registry.get(request.model_id)
        job = GenerationJob(id=uuid.uuid4().hex, request=request, model=model)
        with self._condition:
            self._prune_locked()
            if len(self._pending) >= self._max_size:
                raise RuntimeError(
                    "生成キューが混み合っています。しばらくしてから再試行してください。"
                )
            self._jobs[job.id] = job
            self._pending.append(job.id)
            self._condition.notify()
            return job.response()

    def get(self, job_id: str) -> JobResponse | None:
        with self._condition:
            self._prune_locked()
            job = self._jobs.get(job_id)
            return job.response() if job else None

    def cancel(self, job_id: str) -> JobResponse | None:
        with self._condition:
            self._prune_locked()
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status != "queued":
                raise ValueError("実行開始後のジョブはキャンセルできません")
            # The worker and cancellation both hold this condition while they
            # transition state, so a job is either removed here or already
            # running; it can never be both.
            self._pending.remove(job_id)
            self._finish_locked(job, status="cancelled", message="キャンセル済み")
            self._condition.notify()
            return job.response()

    @property
    def active_job_id(self) -> str | None:
        with self._condition:
            return self._active_job_id

    @property
    def depth(self) -> int:
        with self._condition:
            return len(self._pending)

    @property
    def is_ready(self) -> bool:
        return self._generator.is_ready

    def _work(self) -> None:
        while True:
            with self._condition:
                while not self._pending and not self._shutdown.is_set():
                    self._condition.wait()
                if self._shutdown.is_set():
                    return
                job_id = self._pending.popleft()
                job = self._jobs.get(job_id)
                if job is None or job.status != "queued":
                    continue
                job.status = "running"
                job.progress = 0.1
                job.message = "モデルを準備しています"
                self._active_job_id = job_id
            try:
                with self._condition:
                    job.progress = 0.25
                    job.message = "画像を生成しています"
                images = self._generator.generate(job.request, job.model)
            except Exception as exc:
                logger.exception("generation_failed", extra={"job_id": job_id})
                with self._condition:
                    self._finish_locked(
                        job,
                        status="failed",
                        message="生成に失敗しました",
                        error=str(exc),
                    )
            else:
                with self._condition:
                    job.images = images
                    self._finish_locked(job, status="completed", message="生成が完了しました")
            finally:
                with self._condition:
                    self._active_job_id = None
                    self._prune_locked()

    def _finish_locked(
        self,
        job: GenerationJob,
        *,
        status: str,
        message: str,
        error: str | None = None,
    ) -> None:
        job.status = status
        job.progress = 1.0
        job.message = message
        job.error = error
        job.finished_at = self._clock()

    def _prune_locked(self) -> None:
        """Remove only terminal jobs, preserving all queued/running work."""
        now = self._clock()
        terminal_jobs = [
            job
            for job in self._jobs.values()
            if job.finished_at is not None and job.status in {"completed", "failed", "cancelled"}
        ]
        expired_ids: set[str] = set()
        for job in terminal_jobs:
            finished_at = job.finished_at
            if finished_at is not None and now - finished_at >= self._job_retention_seconds:
                expired_ids.add(job.id)
        retained = sorted(
            (job for job in terminal_jobs if job.id not in expired_ids),
            key=lambda job: job.finished_at if job.finished_at is not None else now,
        )
        excess = len(retained) - self._max_completed_jobs
        if excess > 0:
            expired_ids.update(job.id for job in retained[:excess])
        for job_id in expired_ids:
            self._jobs.pop(job_id, None)
