from types import SimpleNamespace

import pytest

from studio.schemas import GenerateRequest
from studio.services.jobs import GenerationQueue


class FakeGenerator:
    @property
    def is_ready(self) -> bool:
        return True

    def generate(self, request, model):
        return []


class FakeRegistry:
    def get(self, model_id):
        return SimpleNamespace(id=model_id or "default")


def test_rejects_invalid_queue_configuration() -> None:
    with pytest.raises(ValueError):
        GenerationQueue(FakeGenerator(), FakeRegistry(), 0)
    with pytest.raises(ValueError):
        GenerationQueue(FakeGenerator(), FakeRegistry(), 1, job_retention_seconds=-1)
    with pytest.raises(ValueError):
        GenerationQueue(FakeGenerator(), FakeRegistry(), 1, max_completed_jobs=-1)


def test_cancelling_unknown_job_returns_none() -> None:
    queue = GenerationQueue(FakeGenerator(), FakeRegistry(), 1)
    try:
        assert queue.cancel("missing") is None
    finally:
        queue.stop()


def test_cannot_cancel_after_job_started() -> None:
    queue = GenerationQueue(FakeGenerator(), FakeRegistry(), 1)
    queue.start()
    try:
        job = queue.submit(GenerateRequest(prompt="test"))
        import time
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            state = queue.get(job.id)
            if state is not None and state.status != "queued":
                break
            time.sleep(0.01)
        state = queue.get(job.id)
        if state is not None and state.status == "running":
            with pytest.raises(ValueError):
                queue.cancel(job.id)
    finally:
        queue.stop()
