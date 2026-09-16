from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Event
from types import SimpleNamespace

from studio.schemas import GenerateRequest
from studio.services.jobs import GenerationQueue


@dataclass
class FakeGenerator:
    ready: bool = False
    failure: Exception | None = None

    @property
    def is_ready(self) -> bool:
        return self.ready

    def generate(self, request: GenerateRequest, model: object) -> list[object]:
        if self.failure is not None:
            failure = self.failure
            self.failure = None
            raise failure
        return []


class FakeRegistry:
    def get(self, model_id: str | None) -> object:
        return SimpleNamespace(id=model_id or "default")


def wait_for_status(queue: GenerationQueue, job_id: str, expected: str) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = queue.get(job_id)
        if job is not None and job.status == expected:
            return
        Event().wait(0.01)
    raise AssertionError(f"Job {job_id} did not reach {expected}")


def test_stop_is_safe_when_unstarted_queue_is_full() -> None:
    queue = GenerationQueue(FakeGenerator(), FakeRegistry(), 1)
    queue.submit(GenerateRequest(prompt="queued"))

    queue.stop()


def test_cancelled_job_releases_queue_capacity() -> None:
    queue = GenerationQueue(FakeGenerator(), FakeRegistry(), 1)
    cancelled = queue.submit(GenerateRequest(prompt="cancel me"))

    assert queue.cancel(cancelled.id).status == "cancelled"  # type: ignore[union-attr]

    replacement = queue.submit(GenerateRequest(prompt="accepted after cancellation"))

    assert replacement.status == "queued"
    assert queue.depth == 1
    queue.stop()


def test_worker_survives_unexpected_job_failure() -> None:
    queue = GenerationQueue(FakeGenerator(failure=RuntimeError("boom")), FakeRegistry(), 2)
    queue.start()
    failed = queue.submit(GenerateRequest(prompt="fail"))
    wait_for_status(queue, failed.id, "failed")

    recovered = queue.submit(GenerateRequest(prompt="succeed"))
    wait_for_status(queue, recovered.id, "completed")

    assert queue.get(failed.id).error == "boom"  # type: ignore[union-attr]
    queue.stop()


def test_completed_job_retention_enforces_ttl_and_maximum() -> None:
    now = [0.0]
    queue = GenerationQueue(
        FakeGenerator(),
        FakeRegistry(),
        2,
        job_retention_seconds=5,
        max_completed_jobs=1,
        clock=lambda: now[0],
    )
    first = queue.submit(GenerateRequest(prompt="first"))
    queue.cancel(first.id)
    now[0] = 1
    second = queue.submit(GenerateRequest(prompt="second"))
    queue.cancel(second.id)

    assert queue.get(first.id) is None
    assert queue.get(second.id).status == "cancelled"  # type: ignore[union-attr]

    now[0] = 6
    assert queue.get(second.id) is None
    queue.stop()
