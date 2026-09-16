from studio.config import Settings
from studio.services.registry import ModelRegistry


def test_default_model_is_available() -> None:
    settings = Settings.from_environment()
    registry = ModelRegistry(settings)

    model = registry.get(None)

    assert model.id == settings.default_model_id
    assert model.lora_path.exists()
    assert registry.list_summaries()[0].lora_filename == "ixy_style.safetensors"
    assert model.trigger_words == ["ixy_style"]
    assert model.base_model_revision == "d3b6e92692668975622e7fef65ab01c74bc15a15"


def test_base_model_environment_override_is_applied(monkeypatch) -> None:
    monkeypatch.setenv("BASE_MODEL", "/models/local-illustrious")
    settings = Settings.from_environment()

    model = ModelRegistry(settings).get(None)

    assert model.base_model == "/models/local-illustrious"
    assert model.base_model_revision is None


def test_ip_adapter_defaults_are_pinned_and_use_safetensors() -> None:
    settings = Settings.from_environment()

    assert settings.ip_adapter_revision == "018e402774aeeddd60609b4ecdb7e298259dc729"
    assert settings.ip_adapter_weight_name == "ip-adapter-plus_sdxl_vit-h.safetensors"
    assert settings.ip_adapter_face_weight_name == "ip-adapter-plus-face_sdxl_vit-h.safetensors"
    assert settings.ip_adapter_image_encoder_subfolder == "models/image_encoder"


def test_ip_adapter_image_encoder_can_be_selected(monkeypatch) -> None:
    monkeypatch.setenv("IP_ADAPTER_IMAGE_ENCODER_SUBFOLDER", "models/image_encoder")

    settings = Settings.from_environment()

    assert settings.ip_adapter_image_encoder_subfolder == "models/image_encoder"
