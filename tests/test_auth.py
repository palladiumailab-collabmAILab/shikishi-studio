from dataclasses import replace

from fastapi.testclient import TestClient

import app as app_module
from app import create_app
from studio.config import Settings

TOKEN = "test-auth-token-0123456789abcdef"


def lan_settings(tmp_path):
    settings = replace(
        Settings.from_environment(),
        output_dir=tmp_path / "generated",
        reference_dir=tmp_path / "reference-images",
        bind_host="0.0.0.0",
        auth_token=TOKEN,
        auth_session_ttl_seconds=3600,
        require_cuda=False,
        demo_warmup=False,
    )
    settings.output_dir.mkdir()
    settings.reference_dir.mkdir()
    return settings


def test_non_loopback_configuration_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SHIKISHI_BIND_HOST", "0.0.0.0")
    monkeypatch.delenv("SHIKISHI_AUTH_TOKEN", raising=False)

    try:
        Settings.from_environment()
    except ValueError as exc:
        assert "SHIKISHI_AUTH_TOKEN" in str(exc)
    else:
        raise AssertionError("non-loopback bind must require an authentication token")


def test_non_loopback_routes_require_authentication(tmp_path, monkeypatch) -> None:
    settings = lan_settings(tmp_path)
    monkeypatch.setattr(app_module.Settings, "from_environment", lambda: settings)

    with TestClient(create_app()) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/status").status_code == 401
        assert client.get("/images/missing.png").status_code == 401
        assert client.get("/download/missing.png").status_code == 401
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").json() == {"status": "not_ready"}


def test_bearer_token_and_browser_session_authenticate(tmp_path, monkeypatch) -> None:
    settings = lan_settings(tmp_path)
    monkeypatch.setattr(app_module.Settings, "from_environment", lambda: settings)

    with TestClient(create_app()) as client:
        bearer = client.get("/api/status", headers={"Authorization": f"Bearer {TOKEN}"})
        assert bearer.status_code == 200

        login = client.post("/auth/login", data={"token": TOKEN})
        assert login.status_code == 200
        assert login.url.path == "/"
        assert client.get("/api/status").status_code == 200
        assert client.get("/readyz").json()["issues"] == ["model_not_loaded"]


def test_invalid_login_does_not_create_session(tmp_path, monkeypatch) -> None:
    settings = lan_settings(tmp_path)
    monkeypatch.setattr(app_module.Settings, "from_environment", lambda: settings)

    with TestClient(create_app()) as client:
        response = client.post("/auth/login", data={"token": "wrong-token"})
        assert response.status_code == 401
        assert client.get("/api/status").status_code == 401
