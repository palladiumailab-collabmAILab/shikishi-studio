"""Tests for caption and Kohya dataset preparation."""

from pathlib import Path

import pytest

from shikishi.dataset import (
    DatasetConfig,
    export_dataset,
    normalize_tags,
    package_dataset,
    split_archive,
)


def test_normalize_tags_removes_empty_values_and_duplicates() -> None:
    """Tags are suitable for an SDXL training caption."""
    assert normalize_tags(" style_x, , portrait, style_x ") == "style_x, portrait"


def test_export_dataset_copies_captioned_pairs_with_trigger_word(tmp_path: Path) -> None:
    """The export follows Kohya's ``repeats_dataset-name`` directory convention."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "art.png").write_bytes(b"image")
    (source / "art.txt").write_text("watercolor, soft lighting\n", encoding="utf-8")
    config = DatasetConfig(source, tmp_path / "datasets", "my_style", "mystyle", repeats=12)

    assert export_dataset(config) == 1
    assert (config.training_directory / "art.png").read_bytes() == b"image"
    assert (config.training_directory / "art.txt").read_text(encoding="utf-8") == (
        "mystyle, watercolor, soft lighting\n"
    )


def test_export_dataset_rejects_images_without_captions(tmp_path: Path) -> None:
    """A training archive cannot be produced with accidental missing labels."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "art.png").write_bytes(b"image")
    config = DatasetConfig(source, tmp_path / "datasets", "my_style", "mystyle")

    with pytest.raises(ValueError, match="Missing caption"):
        export_dataset(config)


def test_package_dataset_creates_a_colab_zip(tmp_path: Path) -> None:
    """Colab receives the export as a single archive with its directory layout intact."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "art.png").write_bytes(b"image")
    (source / "art.txt").write_text("watercolor\n", encoding="utf-8")
    config = DatasetConfig(source, tmp_path / "datasets", "my_style", "mystyle")
    export_dataset(config)

    archive = package_dataset(config)

    assert archive.is_file()
    assert archive.name == "my_style-colab.zip"


def test_split_archive_creates_numbered_parts(tmp_path: Path) -> None:
    """A large archive can be transferred through a constrained upload channel."""
    archive = tmp_path / "dataset.zip"
    archive.write_bytes(b"abcdefghij")

    parts = split_archive(archive, 1)

    assert parts == [tmp_path / "dataset.zip.part001"]
    assert parts[0].read_bytes() == b"abcdefghij"
