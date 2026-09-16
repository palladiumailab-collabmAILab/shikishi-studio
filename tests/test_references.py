from dataclasses import replace
from io import BytesIO

import pytest
from PIL import Image

from studio.config import Settings
from studio.services.references import ReferenceImageStore


def png_bytes(size: tuple[int, int] = (80, 40)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "#336699").save(output, format="PNG")
    return output.getvalue()


def make_store(tmp_path) -> ReferenceImageStore:
    settings = replace(
        Settings.from_environment(),
        output_dir=tmp_path,
        reference_dir=tmp_path / "reference-images",
    )
    return ReferenceImageStore(settings)


def test_reference_store_preserves_source_and_creates_normalized_preview(tmp_path) -> None:
    store = make_store(tmp_path)

    record = store.save(png_bytes(), "image/png")

    assert store.get(record.id) == record
    assert record.width == 80
    assert record.height == 40
    assert len(record.source_sha256) == 64
    assert store.normalized_path(record.id).exists()


def test_reference_store_rejects_mismatched_content_type(tmp_path) -> None:
    store = make_store(tmp_path)

    with pytest.raises(ValueError, match="Content-Type"):
        store.save(png_bytes(), "image/jpeg")


def test_reference_store_reuses_existing_record_for_identical_source(tmp_path) -> None:
    store = make_store(tmp_path)
    source = png_bytes()

    first = store.save(source, "image/png")
    second = store.save(source, "image/png")

    assert second == first
    assert len(list((tmp_path / "reference-images" / "metadata").glob("*.json"))) == 1


def test_prepare_applies_crop_and_target_size(tmp_path) -> None:
    store = make_store(tmp_path)
    record = store.save(png_bytes((200, 100)), "image/png")

    prepared = store.prepare(record.id, 64, 128, focus_x=1, focus_y=0.5, zoom=2)

    assert prepared.size == (64, 128)
