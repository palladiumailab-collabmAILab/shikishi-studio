from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path

import torch

from shikishi import __version__


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def is_loopback_bind_host(host: str) -> bool:
    normalized = host.strip().lower().strip("[]")
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class Settings:
    root_dir: Path
    static_dir: Path
    output_dir: Path
    reference_dir: Path
    model_registry_path: Path
    character_profiles_path: Path
    default_model_id: str
    device: str
    torch_dtype: torch.dtype
    app_version: str
    bind_host: str
    auth_token: str | None
    auth_session_ttl_seconds: int
    max_queue_size: int
    job_retention_seconds: int
    max_completed_jobs: int
    max_reference_image_bytes: int
    max_reference_pixels: int
    ip_adapter_model: str
    ip_adapter_subfolder: str
    ip_adapter_image_encoder_subfolder: str
    ip_adapter_weight_name: str
    ip_adapter_face_weight_name: str
    ip_adapter_revision: str | None
    base_model_override: str | None
    require_cuda: bool
    demo_warmup: bool
    demo_preload_ip_adapter: bool

    @property
    def auth_enabled(self) -> bool:
        return self.auth_token is not None or not is_loopback_bind_host(self.bind_host)

    @classmethod
    def from_environment(cls) -> Settings:
        root_dir = Path(__file__).resolve().parent.parent
        output_dir = root_dir / "generated"
        output_dir.mkdir(exist_ok=True)
        reference_dir = root_dir / "reference-images"
        reference_dir.mkdir(exist_ok=True)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        bind_host = os.getenv("SHIKISHI_BIND_HOST", "127.0.0.1").strip() or "127.0.0.1"
        auth_token = os.getenv("SHIKISHI_AUTH_TOKEN", "").strip() or None
        if not is_loopback_bind_host(bind_host) and auth_token is None:
            raise ValueError(
                "SHIKISHI_AUTH_TOKEN is required when SHIKISHI_BIND_HOST is non-loopback"
            )
        if auth_token is not None and len(auth_token) < 24:
            raise ValueError("SHIKISHI_AUTH_TOKEN must contain at least 24 characters")
        auth_session_ttl_seconds = int(os.getenv("SHIKISHI_AUTH_SESSION_TTL_SECONDS", "86400"))
        if auth_session_ttl_seconds <= 0:
            raise ValueError("SHIKISHI_AUTH_SESSION_TTL_SECONDS must be positive")
        return cls(
            root_dir=root_dir,
            static_dir=root_dir / "static",
            output_dir=output_dir,
            reference_dir=reference_dir,
            model_registry_path=root_dir / "models" / "registry.json",
            character_profiles_path=root_dir / "models" / "character_profiles.json",
            default_model_id=os.getenv("DEFAULT_MODEL_ID", "ixy-style-final"),
            device=device,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            app_version=os.getenv("APP_VERSION", __version__),
            bind_host=bind_host,
            auth_token=auth_token,
            auth_session_ttl_seconds=auth_session_ttl_seconds,
            max_queue_size=int(os.getenv("MAX_QUEUE_SIZE", "8")),
            job_retention_seconds=int(os.getenv("JOB_RETENTION_SECONDS", "86400")),
            max_completed_jobs=int(os.getenv("MAX_COMPLETED_JOBS", "200")),
            max_reference_image_bytes=int(
                os.getenv("MAX_REFERENCE_IMAGE_BYTES", str(10 * 1024 * 1024))
            ),
            max_reference_pixels=int(os.getenv("MAX_REFERENCE_PIXELS", "16000000")),
            ip_adapter_model=os.getenv("IP_ADAPTER_MODEL", "h94/IP-Adapter"),
            ip_adapter_subfolder=os.getenv("IP_ADAPTER_SUBFOLDER", "sdxl_models"),
            ip_adapter_image_encoder_subfolder=os.getenv(
                "IP_ADAPTER_IMAGE_ENCODER_SUBFOLDER", "models/image_encoder"
            ),
            ip_adapter_weight_name=os.getenv(
                "IP_ADAPTER_WEIGHT_NAME", "ip-adapter-plus_sdxl_vit-h.safetensors"
            ),
            ip_adapter_face_weight_name=os.getenv(
                "IP_ADAPTER_FACE_WEIGHT_NAME", "ip-adapter-plus-face_sdxl_vit-h.safetensors"
            ),
            ip_adapter_revision=os.getenv(
                "IP_ADAPTER_REVISION", "018e402774aeeddd60609b4ecdb7e298259dc729"
            )
            or None,
            base_model_override=os.getenv("BASE_MODEL") or None,
            require_cuda=_env_bool("REQUIRE_CUDA", False),
            demo_warmup=_env_bool("DEMO_WARMUP", False),
            demo_preload_ip_adapter=_env_bool("DEMO_PRELOAD_IP_ADAPTER", False),
        )
