from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from studio.config import Settings
from studio.schemas import CharacterReference, GenerateRequest
from studio.services.generator import ImageGenerator
from studio.services.history import HistoryStore
from studio.services.references import ReferenceImageStore
from studio.services.registry import ModelRegistry


class FakeImage:
    def save(self, path) -> None:
        path.write_bytes(b"image")


class FakeImageEncoder:
    def __init__(self) -> None:
        self.device = None
        self.dtype = None

    def to(self, device=None, dtype=None):
        self.device = device
        self.dtype = dtype
        return self


class FakePipeline:
    def __init__(self) -> None:
        self.adapter_name = None
        self.last_kwargs = {}
        self.calls = []
        self.ip_adapter_loaded = False
        self.ip_adapter_scale = None
        self.ip_adapter_kwargs = {}
        self.ip_adapter_loads = []
        self.device = "cpu"
        self.image_encoder = None
        self.to_calls = []
        self.dtype = None
        self.cpu_offload_enabled = False
        self.attention_slicing_disabled = False
        self.attention_slicing_enabled = False
        self.hooks_removed = False
        self.fail_ip_adapter_scale = False
        self.fail_unload = False

    def set_adapters(self, name, adapter_weights) -> None:
        self.adapter_name = name

    def __call__(self, **kwargs) -> SimpleNamespace:
        self.last_kwargs = kwargs
        self.calls.append(kwargs)
        return SimpleNamespace(images=[FakeImage()])

    def load_ip_adapter(self, *args, **kwargs) -> None:
        self.ip_adapter_loaded = True
        self.ip_adapter_kwargs = kwargs
        self.ip_adapter_loads.append(kwargs)

    def set_ip_adapter_scale(self, scale) -> None:
        if self.fail_ip_adapter_scale:
            raise RuntimeError("scale failure")
        self.ip_adapter_scale = scale

    def register_modules(self, **kwargs) -> None:
        self.image_encoder = kwargs["image_encoder"]

    def to(self, device=None, dtype=None):
        if device is not None:
            self.to_calls.append(device)
            self.device = device
        self.dtype = dtype or self.dtype
        return self

    def enable_model_cpu_offload(self) -> None:
        self.cpu_offload_enabled = True

    def disable_attention_slicing(self) -> None:
        self.attention_slicing_disabled = True

    def enable_attention_slicing(self) -> None:
        self.attention_slicing_enabled = True

    def remove_all_hooks(self) -> None:
        self.hooks_removed = True

    def unload_ip_adapter(self) -> None:
        if self.fail_unload:
            raise RuntimeError("unload failure")
        self.ip_adapter_loaded = False


def test_generator_uses_registry_model_id(tmp_path) -> None:
    settings = replace(Settings.from_environment(), output_dir=tmp_path)
    registry = ModelRegistry(settings)
    model = registry.get(None)
    pipeline = FakePipeline()
    generator = ImageGenerator(settings, HistoryStore(settings))
    generator._get_pipeline = lambda _: pipeline  # type: ignore[method-assign]

    result = generator.generate(GenerateRequest(prompt="test", seed=7), model)

    assert pipeline.adapter_name == model.id
    assert result[0].seed == 7
    assert pipeline.last_kwargs["prompt"].startswith(
        "ixy_style, solo, single character, one person, "
    )
    assert "multiple people" in pipeline.last_kwargs["negative_prompt"]


def test_generator_can_disable_single_subject_conditioning(tmp_path) -> None:
    settings = replace(Settings.from_environment(), output_dir=tmp_path)
    model = ModelRegistry(settings).get(None)
    pipeline = FakePipeline()
    generator = ImageGenerator(settings, HistoryStore(settings))
    generator._get_pipeline = lambda _: pipeline  # type: ignore[method-assign]

    generator.generate(
        GenerateRequest(
            prompt="two friends",
            negative_prompt="blurry",
            single_subject=False,
            standard_proportions=False,
            use_trigger_words=False,
        ),
        model,
    )

    assert pipeline.last_kwargs["prompt"] == "two friends"
    assert pipeline.last_kwargs["negative_prompt"] == "blurry"


def test_generator_defaults_to_standard_proportions_and_can_disable_it(tmp_path) -> None:
    settings = replace(Settings.from_environment(), output_dir=tmp_path)
    model = ModelRegistry(settings).get(None)
    pipeline = FakePipeline()
    generator = ImageGenerator(settings, HistoryStore(settings))
    generator._get_pipeline = lambda _: pipeline  # type: ignore[method-assign]

    generator.generate(GenerateRequest(prompt="portrait"), model)

    assert "normal proportions" in pipeline.last_kwargs["prompt"]
    assert "chibi" in pipeline.last_kwargs["negative_prompt"]

    generator.generate(
        GenerateRequest(prompt="chibi portrait", standard_proportions=False),
        model,
    )

    assert "normal proportions" not in pipeline.last_kwargs["prompt"]
    assert "chibi, super deformed" not in pipeline.last_kwargs["negative_prompt"]


def test_generator_does_not_duplicate_explicit_trigger_word(tmp_path) -> None:
    settings = replace(Settings.from_environment(), output_dir=tmp_path)
    model = ModelRegistry(settings).get(None)
    pipeline = FakePipeline()
    generator = ImageGenerator(settings, HistoryStore(settings))
    generator._get_pipeline = lambda _: pipeline  # type: ignore[method-assign]

    generator.generate(GenerateRequest(prompt="ixy_style, portrait"), model)

    assert pipeline.last_kwargs["prompt"].count("ixy_style") == 1


def test_generator_prioritizes_separate_pose_prompt(tmp_path) -> None:
    settings = replace(Settings.from_environment(), output_dir=tmp_path)
    model = ModelRegistry(settings).get(None)
    pipeline = FakePipeline()
    generator = ImageGenerator(settings, HistoryStore(settings))
    generator._get_pipeline = lambda _: pipeline  # type: ignore[method-assign]

    generator.generate(
        GenerateRequest(prompt="appearance details", pose_prompt="seated, hands on lap"),
        model,
    )

    assert pipeline.last_kwargs["prompt"].index("seated") < pipeline.last_kwargs["prompt"].index(
        "appearance details"
    )


def test_request_accepts_generated_unsigned_32_bit_seed() -> None:
    request = GenerateRequest(prompt="test", seed=2_891_333_975)

    assert request.seed == 2_891_333_975


def test_generator_uses_img2img_pipeline_for_reference(tmp_path) -> None:
    settings = replace(
        Settings.from_environment(),
        output_dir=tmp_path,
        reference_dir=tmp_path / "reference-images",
    )
    model = ModelRegistry(settings).get(None)
    reference_store = ReferenceImageStore(settings)
    source = BytesIO()
    Image.new("RGB", (80, 40), "green").save(source, format="PNG")
    reference = reference_store.save(source.getvalue(), "image/png")
    pipeline = FakePipeline()
    generator = ImageGenerator(settings, HistoryStore(settings), reference_store)
    generator._get_img2img_pipeline = lambda _: pipeline  # type: ignore[method-assign]

    generator.generate(
        GenerateRequest(
            prompt="test",
            width=512,
            height=512,
            reference_image_id=reference.id,
            reference_strength=0.35,
        ),
        model,
    )

    assert pipeline.last_kwargs["image"].size == (512, 512)
    assert pipeline.last_kwargs["strength"] == 0.35


def test_generator_loads_ip_adapter_only_for_reference_generation(tmp_path) -> None:
    settings = replace(
        Settings.from_environment(),
        output_dir=tmp_path,
        reference_dir=tmp_path / "reference-images",
    )
    model = ModelRegistry(settings).get(None)
    reference_store = ReferenceImageStore(settings)
    source = BytesIO()
    Image.new("RGB", (40, 40), "purple").save(source, format="PNG")
    reference = reference_store.save(source.getvalue(), "image/png")
    pipeline = FakePipeline()
    generator = ImageGenerator(settings, HistoryStore(settings), reference_store)
    generator._get_pipeline = lambda _: pipeline  # type: ignore[method-assign]
    image_encoder = FakeImageEncoder()
    generator._load_ip_adapter_image_encoder = (  # type: ignore[method-assign]
        lambda: image_encoder
    )

    generator.generate(
        GenerateRequest(
            prompt="test",
            width=512,
            height=512,
            reference_image_id=reference.id,
            reference_mode="ip_adapter",
            reference_ip_adapter_scale=0.6,
        ),
        model,
    )

    assert pipeline.ip_adapter_scale == 0.6
    assert pipeline.last_kwargs["ip_adapter_image"].size == (512, 512)
    assert "image" not in pipeline.last_kwargs
    assert pipeline.ip_adapter_loaded is False
    assert pipeline.hooks_removed is True
    assert pipeline.ip_adapter_kwargs["revision"] == settings.ip_adapter_revision
    assert pipeline.ip_adapter_kwargs["weight_name"].endswith(".safetensors")
    assert pipeline.ip_adapter_kwargs["image_encoder_folder"] is None
    assert image_encoder.device == pipeline.device


def test_ip_adapter_uses_cpu_offload_for_cuda_memory_limit(tmp_path) -> None:
    settings = replace(Settings.from_environment(), output_dir=tmp_path, device="cuda")
    pipeline = FakePipeline()
    pipeline.device = "cuda"
    image_encoder = FakeImageEncoder()
    generator = ImageGenerator(settings, HistoryStore(settings))
    generator._load_ip_adapter_image_encoder = (  # type: ignore[method-assign]
        lambda: image_encoder
    )

    generator._load_ip_adapter(pipeline, 0.55)

    assert pipeline.to_calls == ["cpu"]
    assert image_encoder.device == "cpu"
    assert pipeline.cpu_offload_enabled is True
    assert pipeline.attention_slicing_disabled is True


def test_ip_adapter_cleanup_restores_cuda_pipeline(tmp_path) -> None:
    settings = replace(Settings.from_environment(), output_dir=tmp_path, device="cuda")
    pipeline = FakePipeline()
    pipeline.device = "cpu"
    pipeline.image_encoder = FakeImageEncoder()
    pipeline.ip_adapter_loaded = True
    generator = ImageGenerator(settings, HistoryStore(settings))

    generator._unload_ip_adapter(pipeline)

    assert pipeline.hooks_removed is True
    assert pipeline.ip_adapter_loaded is False
    assert pipeline.image_encoder is None
    assert pipeline.to_calls == ["cpu", "cuda"]
    assert pipeline.device == "cuda"
    assert pipeline.attention_slicing_enabled is True


def test_ip_adapter_load_failure_restores_state_and_discards_cached_pipeline(tmp_path) -> None:
    settings = replace(Settings.from_environment(), output_dir=tmp_path)
    pipeline = FakePipeline()
    pipeline.fail_ip_adapter_scale = True
    generator = ImageGenerator(settings, HistoryStore(settings))
    generator._pipelines["broken"] = pipeline  # type: ignore[assignment]
    generator._load_ip_adapter_image_encoder = (  # type: ignore[method-assign]
        lambda: FakeImageEncoder()
    )

    with pytest.raises(RuntimeError, match="IP-Adapterを読み込めません"):
        generator._load_ip_adapter(pipeline, 0.55)

    assert pipeline.hooks_removed is True
    assert pipeline.ip_adapter_loaded is False
    assert pipeline.image_encoder is None
    assert generator._pipelines == {}


def test_ip_adapter_failed_rollback_still_discards_cached_pipeline(tmp_path) -> None:
    settings = replace(Settings.from_environment(), output_dir=tmp_path)
    pipeline = FakePipeline()
    pipeline.fail_ip_adapter_scale = True
    pipeline.fail_unload = True
    generator = ImageGenerator(settings, HistoryStore(settings))
    generator._pipelines["broken"] = pipeline  # type: ignore[assignment]
    generator._load_ip_adapter_image_encoder = (  # type: ignore[method-assign]
        lambda: FakeImageEncoder()
    )

    with pytest.raises(RuntimeError, match="キャッシュを破棄"):
        generator._load_ip_adapter(pipeline, 0.55)

    assert pipeline.image_encoder is None
    assert generator._pipelines == {}


def test_generator_separates_appearance_face_and_pose_references(tmp_path) -> None:
    settings = replace(
        Settings.from_environment(),
        output_dir=tmp_path,
        reference_dir=tmp_path / "reference-images",
    )
    model = ModelRegistry(settings).get(None)
    reference_store = ReferenceImageStore(settings)
    records = []
    for colour in ("blue", "cyan", "gray"):
        source = BytesIO()
        Image.new("RGB", (80, 120), colour).save(source, format="PNG")
        records.append(reference_store.save(source.getvalue(), "image/png"))
    pipeline = FakePipeline()
    generator = ImageGenerator(settings, HistoryStore(settings), reference_store)
    generator._get_img2img_pipeline = lambda _: pipeline  # type: ignore[method-assign]
    generator._load_ip_adapter_image_encoder = (  # type: ignore[method-assign]
        lambda: FakeImageEncoder()
    )

    generator.generate(
        GenerateRequest(
            prompt="test",
            width=512,
            height=512,
            character_references=[
                CharacterReference(reference_image_id=records[0].id, role="appearance"),
                CharacterReference(reference_image_id=records[1].id, role="face", zoom=2),
            ],
            pose_reference_image_id=records[2].id,
            pose_reference_strength=0.3,
            reference_ip_adapter_scale=0.35,
            reference_face_ip_adapter_scale=0.25,
        ),
        model,
    )

    assert len(pipeline.calls) == 2
    assert pipeline.calls[0]["image"].size == (512, 512)
    assert pipeline.calls[0]["strength"] == 0.3
    assert pipeline.calls[1]["image"].__class__ is FakeImage
    assert [load["weight_name"] for load in pipeline.ip_adapter_loads] == [
        settings.ip_adapter_weight_name,
        settings.ip_adapter_face_weight_name,
    ]
    assert pipeline.ip_adapter_scale == 0.25
