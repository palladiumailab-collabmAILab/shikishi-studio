from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

import app as app_module
from app import create_app
from studio.config import Settings
from tools.reset_demo_data import reset_demo_data


class ControllableGenerator:
    def __init__(self) -> None:
        self.ready = False
        self.prepare_calls = 0

    @property
    def is_ready(self) -> bool:
        return self.ready

    def prepare(self, *_args: object, **_kwargs: object) -> None:
        self.prepare_calls += 1
        self.ready = True

    def generate(self, *_args: object) -> list[object]:
        return []


def test_readyz_requires_loaded_model(tmp_path, monkeypatch) -> None:
    settings = replace(
        Settings.from_environment(),
        output_dir=tmp_path / "generated",
        reference_dir=tmp_path / "reference-images",
        require_cuda=False,
        demo_warmup=False,
    )
    settings.output_dir.mkdir()
    settings.reference_dir.mkdir()
    generator = ControllableGenerator()
    monkeypatch.setattr(app_module.Settings, "from_environment", lambda: settings)
    monkeypatch.setattr(app_module, "ImageGenerator", lambda *_args: generator)

    with TestClient(create_app()) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 503
        generator.ready = True
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "issues": []}


def test_demo_warmup_prepares_model_before_readiness(tmp_path, monkeypatch) -> None:
    settings = replace(
        Settings.from_environment(),
        output_dir=tmp_path / "generated",
        reference_dir=tmp_path / "reference-images",
        require_cuda=False,
        demo_warmup=True,
        demo_preload_ip_adapter=True,
    )
    settings.output_dir.mkdir()
    settings.reference_dir.mkdir()
    generator = ControllableGenerator()
    monkeypatch.setattr(app_module.Settings, "from_environment", lambda: settings)
    monkeypatch.setattr(app_module, "ImageGenerator", lambda *_args: generator)

    with TestClient(create_app()) as client:
        assert client.get("/readyz").status_code == 200

    assert generator.prepare_calls == 1


def test_reset_demo_data_preserves_other_directories(tmp_path) -> None:
    generated = tmp_path / "generated"
    references = tmp_path / "reference-images" / "source"
    models = tmp_path / "models"
    generated.mkdir()
    references.mkdir(parents=True)
    models.mkdir()
    (generated / "image.png").write_bytes(b"image")
    (references / "reference.png").write_bytes(b"reference")
    (models / "model.bin").write_bytes(b"model")

    files, _ = reset_demo_data(tmp_path, apply=False)
    assert files == 2
    assert (generated / "image.png").exists()

    reset_demo_data(tmp_path, apply=True)
    assert not (generated / "image.png").exists()
    assert not references.exists()
    assert (models / "model.bin").exists()
