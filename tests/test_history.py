import logging
from dataclasses import replace

from studio.config import Settings
from studio.schemas import CharacterReference, EvaluationRequest, GeneratedImage, GenerateRequest
from studio.services.history import HistoryStore
from studio.services.registry import ModelRegistry


def test_history_round_trip(tmp_path) -> None:
    settings = replace(Settings.from_environment(), output_dir=tmp_path)
    registry = ModelRegistry(settings)
    store = HistoryStore(settings)
    image = GeneratedImage(filename="sample.png", image_url="/images/sample.png", seed=42)
    store.image_path(image.filename).touch()

    store.save(image, GenerateRequest(prompt="test"), registry.get(None))

    history = store.list_items()
    assert len(history) == 1
    assert history[0].seed == 42
    assert history[0].model_id == settings.default_model_id
    assert history[0].use_trigger_words is True
    assert history[0].standard_proportions is True
    assert history[0].base_model_revision == registry.get(None).base_model_revision

    evaluation = store.save_evaluation(
        image.filename,
        EvaluationRequest(identity_score=4, style_score=5, pose_score=3, notes="A/B"),
    )
    assert evaluation.identity_score == 4
    assert store.image_path(image.filename).with_suffix(".evaluation.json").exists()


def test_corrupt_history_is_skipped_with_filename_warning(tmp_path, caplog) -> None:
    settings = replace(Settings.from_environment(), output_dir=tmp_path)
    (tmp_path / "broken.png.json").write_text("not json", encoding="utf-8")
    store = HistoryStore(settings)

    with caplog.at_level(logging.WARNING):
        assert store.list_items() == []

    assert "broken.png.json" in caplog.text


def test_history_preserves_structured_reference_provenance(tmp_path) -> None:
    settings = replace(Settings.from_environment(), output_dir=tmp_path)
    store = HistoryStore(settings)
    registry = ModelRegistry(settings)
    image = GeneratedImage(filename="references.png", image_url="/images/references.png", seed=7)
    store.image_path(image.filename).touch()
    request = GenerateRequest(
        prompt="test",
        character_references=[
            CharacterReference(reference_image_id="a" * 32, role="appearance"),
            CharacterReference(reference_image_id="b" * 32, role="face", zoom=2),
        ],
        pose_reference_image_id="c" * 32,
        pose_reference_strength=0.3,
    )

    store.save(image, request, registry.get(None))

    item = store.list_items()[0]
    assert [reference.role for reference in item.character_references] == [
        "appearance",
        "face",
    ]
    assert item.pose_reference_image_id == "c" * 32
    assert item.pose_reference_strength == 0.3
