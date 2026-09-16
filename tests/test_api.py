from dataclasses import replace
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

import app as app_module
from app import create_app
from studio.config import Settings


class ReadyGenerator:
    def __init__(self) -> None:
        self.ready = False

    @property
    def is_ready(self) -> bool:
        return self.ready

    def generate(self, *_args: object) -> list[object]:
        return []


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 32), "blue").save(output, format="PNG")
    return output.getvalue()


def test_health_status_and_models() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/api/status").status_code == 200
        assert client.get("/api/models").json()[0]["id"] == "ixy-style-final"
        profiles = client.get("/api/character-profiles").json()
        assert profiles[0]["id"] == "hotarugusa"


def test_status_readiness_reflects_generator_state(monkeypatch) -> None:
    generator = ReadyGenerator()
    monkeypatch.setattr(app_module, "ImageGenerator", lambda *_args: generator)

    with TestClient(create_app()) as client:
        assert client.get("/api/status").json()["ready"] is False
        generator.ready = True
        assert client.get("/api/status").json()["ready"] is True


def test_home_exposes_active_model_for_mobile_clients() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="active-model"' in response.text
    assert 'id="single-subject"' in response.text
    assert 'id="character-preset"' in response.text
    assert 'id="character-reference-files"' in response.text
    assert 'id="pose-reference-file"' in response.text
    assert 'id="reference-face-ip-scale"' in response.text
    assert 'id="reference-face-refinement-strength"' in response.text
    assert 'id="pose-prompt"' in response.text
    assert 'id="quality-preset"' in response.text
    assert 'id="standard-proportions"' in response.text
    assert ".advanced[hidden]" in client.get("/static/reference.css").text
    assert ".composer-wrap.expanded" in client.get("/static/styles.css").text


def test_unknown_model_is_rejected() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/api/jobs", json={"prompt": "test", "model_id": "missing"})
        assert response.status_code == 400


def test_unknown_character_profile_is_rejected() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/jobs",
            json={"prompt": "test", "character_profile_id": "missing"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown character_profile_id: missing"


def test_reference_image_can_be_uploaded_and_previewed(tmp_path, monkeypatch) -> None:
    settings = replace(
        Settings.from_environment(),
        output_dir=tmp_path,
        reference_dir=tmp_path / "reference-images",
    )
    monkeypatch.setattr(app_module.Settings, "from_environment", lambda: settings)

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/reference-images",
            content=png_bytes(),
            headers={"content-type": "image/png"},
        )
        assert response.status_code == 201
        preview = client.get(response.json()["preview_url"])

    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"


def test_unknown_reference_image_is_rejected() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/jobs",
            json={"prompt": "test", "reference_image_id": "0" * 32},
        )

    assert response.status_code == 400
    assert "参照画像が見つかりません" in response.json()["detail"]


def test_unknown_structured_reference_images_are_rejected() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/jobs",
            json={
                "prompt": "test",
                "character_references": [{"reference_image_id": "0" * 32, "role": "face"}],
                "pose_reference_image_id": "1" * 32,
            },
        )

    assert response.status_code == 400
    assert "参照画像が見つかりません" in response.json()["detail"]


def test_more_than_six_character_references_are_rejected() -> None:
    references = [
        {"reference_image_id": f"{index:032x}", "role": "appearance"} for index in range(7)
    ]
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/jobs", json={"prompt": "test", "character_references": references}
        )

    assert response.status_code == 422


def test_generated_image_can_be_copied_to_reference_store(tmp_path, monkeypatch) -> None:
    settings = replace(
        Settings.from_environment(),
        output_dir=tmp_path / "generated",
        reference_dir=tmp_path / "reference-images",
    )
    settings.output_dir.mkdir()
    (settings.output_dir / "canonical.png").write_bytes(png_bytes())
    monkeypatch.setattr(app_module.Settings, "from_environment", lambda: settings)

    with TestClient(create_app()) as client:
        response = client.post("/api/reference-images/from-history/canonical.png")
        repeated = client.post("/api/reference-images/from-history/canonical.png")

    assert response.status_code == 201
    assert response.json()["source_sha256"]
    assert repeated.status_code == 201
    assert repeated.json()["id"] == response.json()["id"]
    assert (settings.output_dir / "canonical.png").exists()


def test_evaluation_for_missing_image_is_rejected() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/history/missing.png/evaluation",
            json={"identity_score": 3, "style_score": 4, "pose_score": 2},
        )

    assert response.status_code == 404


def test_only_generated_png_is_public_not_its_metadata(tmp_path, monkeypatch) -> None:
    settings = replace(
        Settings.from_environment(),
        output_dir=tmp_path,
        reference_dir=tmp_path / "reference-images",
    )
    (tmp_path / "sample.png").write_bytes(png_bytes())
    (tmp_path / "sample.png.json").write_text('{"prompt":"private"}', encoding="utf-8")
    monkeypatch.setattr(app_module.Settings, "from_environment", lambda: settings)

    with TestClient(create_app()) as client:
        image_response = client.get("/images/sample.png")
        metadata_response = client.get("/images/sample.png.json")
        metadata_download = client.get("/download/sample.png.json")

    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"
    assert metadata_response.status_code == 404
    assert metadata_download.status_code == 404
