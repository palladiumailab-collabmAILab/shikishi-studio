"""Tests for goal-focused style-LoRA dataset curation."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from shikishi.style_curation import (
    StyleCurationConfig,
    clean_caption,
    export_curated_style_dataset,
    load_candidates,
    select_candidates,
)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path: Path) -> StyleCurationConfig:
    source = tmp_path / "source"
    source.mkdir()
    definitions = [
        (
            "primary.jpg",
            "train",
            "style_01_clean_lineart",
            "single_female",
            "full_body",
            "False",
            "simple_bg_character",
        ),
        (
            "composite.jpg",
            "validation",
            "style_03_composite_scene",
            "single_female",
            "upper_body",
            "False",
            "detailed_bg_character",
        ),
        (
            "diverse.jpg",
            "test",
            "style_02_dark_flat",
            "group_or_male",
            "other",
            "False",
            "group_or_male",
        ),
        (
            "duplicate.jpg",
            "train",
            "style_04_pastel_soft",
            "single_female",
            "other",
            "True",
            "simple_bg_character",
        ),
        (
            "sketch.jpg",
            "train",
            "style_01_clean_lineart",
            "single_female",
            "other",
            "False",
            "simple_bg_character",
        ),
    ]
    labels: list[dict[str, str]] = []
    splits: list[dict[str, str]] = []
    clusters: list[dict[str, str]] = []
    for image, split, cluster, subject, framing, duplicate, archetype in definitions:
        caption = Path(image).with_suffix(".txt").name
        (source / image).write_bytes(image.encode())
        extra = ", sketch" if image == "sketch.jpg" else ""
        (source / caption).write_text(
            f"ixy, ixy_style, 1girl, solo, bad_id, blue_hair{extra}\n", encoding="utf-8"
        )
        labels.append(
            {
                "image": image,
                "caption": caption,
                "archetype": archetype,
                "subject": subject,
                "background": "simple_white",
                "framing": framing,
                "school_uniform": "False",
                "source_duplicate_flag": duplicate,
                "metadata_noise_flag": "False",
                "recommendation": "core_candidate",
            }
        )
        splits.append({"image": image, "split": split})
        clusters.append({"source": f"C:\\source\\{image}", "cluster": cluster})
    labels_csv = tmp_path / "labels.csv"
    splits_csv = tmp_path / "splits.csv"
    clusters_csv = tmp_path / "clusters.csv"
    _write_csv(labels_csv, labels)
    _write_csv(splits_csv, splits)
    _write_csv(clusters_csv, clusters)
    return StyleCurationConfig(
        source_dir=source,
        curation_labels=labels_csv,
        split_manifest=splits_csv,
        clustering_manifest=clusters_csv,
        output_dir=tmp_path / "output",
        composite_aux_limit=10,
        diversity_aux_limit=10,
    )


def test_selection_excludes_duplicates_variants_and_review_styles(tmp_path: Path) -> None:
    config = _fixture(tmp_path)

    selected = select_candidates(load_candidates(config), config)

    assert [item.image for item in selected["primary"]] == ["primary.jpg"]
    assert [item.image for item in selected["composite_aux"]] == ["composite.jpg"]
    assert [item.image for item in selected["diversity_aux"]] == ["diverse.jpg"]


def test_clean_caption_keeps_content_and_replaces_old_style_tags(tmp_path: Path) -> None:
    caption = tmp_path / "caption.txt"
    caption.write_text("ixy, ixy_style, 1girl, blue_hair, bad_id, commentary\n", encoding="utf-8")

    assert clean_caption(caption, "ixy_style_v2") == "ixy_style_v2, 1girl, blue_hair"


def test_export_is_traceable_and_does_not_modify_sources(tmp_path: Path) -> None:
    config = _fixture(tmp_path)
    original_caption = (config.source_dir / "primary.txt").read_bytes()

    counts = export_curated_style_dataset(config)

    assert counts == {
        "test_diversity_aux": 1,
        "train_fullbody_boost": 1,
        "train_primary": 1,
        "validation_composite_aux": 1,
    }
    train = config.output_dir / "train" / "1_ixy_style_v2_primary"
    assert (train / "primary.jpg").read_bytes() == b"primary.jpg"
    assert (train / "primary.txt").read_text(encoding="utf-8") == (
        "ixy_style_v2, 1girl, solo, blue_hair\n"
    )
    assert (config.source_dir / "primary.txt").read_bytes() == original_caption
    assert (config.output_dir / "reports" / "selection_manifest.csv").is_file()
    assert (config.output_dir / "reports" / "provenance.json").is_file()

    with pytest.raises(ValueError, match="already exists"):
        export_curated_style_dataset(config)
