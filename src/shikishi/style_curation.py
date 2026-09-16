"""Curate a goal-focused, traceable style-LoRA dataset from review evidence."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shikishi.dataset import IMAGE_EXTENSIONS, normalize_tags

DEFAULT_REMOVED_TAGS = frozenset(
    {
        "ixy",
        "ixy_style",
        "commentary",
        "commentary_request",
        "translation_request",
        "duplicate",
        "pixel-perfect_duplicate",
        "revision",
        "highres",
        "absurdres",
        "masterpiece",
        "best_quality",
        "high_quality",
        "bad_id",
        "bad_pixiv_id",
        "untranslatable_commentary",
    }
)
DEFAULT_REVIEW_TAGS = frozenset(
    {"comic", "manga", "4koma", "sketch", "lineart", "multiple_views", "text"}
)
GOAL_CLUSTERS = frozenset({"style_01_clean_lineart", "style_02_dark_flat", "style_04_pastel_soft"})
SPLITS = ("train", "validation", "test")


@dataclass(frozen=True)
class StyleCurationConfig:
    """Inputs and deterministic selection limits for one derived dataset version."""

    source_dir: Path
    curation_labels: Path
    split_manifest: Path
    clustering_manifest: Path
    output_dir: Path
    dataset_name: str = "ixy_style_v2"
    trigger_word: str = "ixy_style_v2"
    composite_aux_limit: int = 128
    diversity_aux_limit: int = 48
    seed: int = 42

    def __post_init__(self) -> None:
        if not self.source_dir.is_dir():
            raise ValueError(f"Source directory does not exist: {self.source_dir}")
        for path in (self.curation_labels, self.split_manifest, self.clustering_manifest):
            if not path.is_file():
                raise ValueError(f"Required manifest does not exist: {path}")
        if not self.dataset_name.strip() or not self.trigger_word.strip():
            raise ValueError("Dataset name and trigger word must not be empty.")
        if self.composite_aux_limit < 0 or self.diversity_aux_limit < 0:
            raise ValueError("Auxiliary selection limits must not be negative.")


@dataclass(frozen=True)
class Candidate:
    """Joined curation, split, cluster, and caption evidence for one source image."""

    image: str
    caption: str
    split: str
    cluster: str
    archetype: str
    subject: str
    background: str
    framing: str
    source_duplicate: bool
    review_tags: tuple[str, ...]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def _basename(value: str) -> str:
    return value.replace("\\", "/").rsplit("/", maxsplit=1)[-1]


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def _caption_tags(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    return [tag.strip().lower() for tag in raw.split(",") if tag.strip()]


def load_candidates(config: StyleCurationConfig) -> list[Candidate]:
    """Join the existing review manifests without reclassifying source artwork."""
    splits = {row["image"]: row["split"] for row in _read_csv(config.split_manifest)}
    clusters = {
        _basename(row["source"]): row["cluster"] for row in _read_csv(config.clustering_manifest)
    }
    candidates: list[Candidate] = []
    for row in _read_csv(config.curation_labels):
        image = row["image"]
        caption = row["caption"]
        if image not in splits:
            raise ValueError(f"Image is missing from split manifest: {image}")
        if image not in clusters:
            raise ValueError(f"Image is missing from clustering manifest: {image}")
        caption_path = config.source_dir / caption
        if not caption_path.is_file():
            raise ValueError(f"Caption is missing: {caption_path}")
        tags = set(_caption_tags(caption_path))
        candidates.append(
            Candidate(
                image=image,
                caption=caption,
                split=splits[image],
                cluster=clusters[image],
                archetype=row["archetype"],
                subject=row["subject"],
                background=row["background"],
                framing=row["framing"],
                source_duplicate=_as_bool(row["source_duplicate_flag"]),
                review_tags=tuple(sorted(tags & DEFAULT_REVIEW_TAGS)),
            )
        )
    invalid_splits = sorted({item.split for item in candidates} - set(SPLITS))
    if invalid_splits:
        raise ValueError(f"Unsupported split names: {invalid_splits}")
    return candidates


def _stable_key(item: Candidate, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{item.image}".encode()).hexdigest()


def _balanced_sample(candidates: Iterable[Candidate], limit: int, seed: int) -> list[Candidate]:
    """Select deterministically in round-robin order across visual strata."""
    groups: dict[tuple[str, str, str], list[Candidate]] = defaultdict(list)
    for item in candidates:
        groups[(item.framing, item.background, item.archetype)].append(item)
    for group in groups.values():
        group.sort(key=lambda item: _stable_key(item, seed))
    selected: list[Candidate] = []
    ordered_keys = sorted(groups)
    while len(selected) < limit and ordered_keys:
        remaining: list[tuple[str, str, str]] = []
        for key in ordered_keys:
            group = groups[key]
            if group and len(selected) < limit:
                selected.append(group.pop(0))
            if group:
                remaining.append(key)
        ordered_keys = remaining
    return selected


def _split_limits(total: int) -> dict[str, int]:
    train = round(total * 0.8)
    validation = round(total * 0.1)
    return {"train": train, "validation": validation, "test": total - train - validation}


def select_candidates(
    candidates: Iterable[Candidate], config: StyleCurationConfig
) -> dict[str, list[Candidate]]:
    """Create mutually exclusive primary and low-weight auxiliary groups."""
    eligible = [
        item
        for item in candidates
        if not item.source_duplicate and item.archetype != "variant_style" and not item.review_tags
    ]
    selected: dict[str, list[Candidate]] = {
        "primary": [
            item
            for item in eligible
            if item.subject == "single_female" and item.cluster in GOAL_CLUSTERS
        ],
        "composite_aux": [],
        "diversity_aux": [],
    }
    composite_limits = _split_limits(config.composite_aux_limit)
    diversity_limits = _split_limits(config.diversity_aux_limit)
    for split in SPLITS:
        selected["composite_aux"].extend(
            _balanced_sample(
                (
                    item
                    for item in eligible
                    if item.split == split
                    and item.subject == "single_female"
                    and item.cluster == "style_03_composite_scene"
                ),
                composite_limits[split],
                config.seed,
            )
        )
        selected["diversity_aux"].extend(
            _balanced_sample(
                (
                    item
                    for item in eligible
                    if item.split == split
                    and item.subject != "single_female"
                    and item.cluster in GOAL_CLUSTERS
                ),
                diversity_limits[split],
                config.seed,
            )
        )
    return selected


def clean_caption(path: Path, trigger_word: str) -> str:
    """Keep visual/content labels while removing source-management metadata."""
    tags = [tag for tag in _caption_tags(path) if tag not in DEFAULT_REMOVED_TAGS]
    return normalize_tags(", ".join([trigger_word, *tags]))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_pair(
    item: Candidate,
    destination: Path,
    config: StyleCurationConfig,
) -> tuple[Path, str]:
    source_image = config.source_dir / item.image
    if not source_image.is_file() or source_image.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError(f"Source image is missing or unsupported: {source_image}")
    destination.mkdir(parents=True, exist_ok=True)
    output_image = destination / item.image
    shutil.copy2(source_image, output_image)
    caption = clean_caption(config.source_dir / item.caption, config.trigger_word)
    output_image.with_suffix(".txt").write_text(caption + "\n", encoding="utf-8")
    return output_image, caption


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["source_image"]
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def export_curated_style_dataset(config: StyleCurationConfig) -> dict[str, int]:
    """Write a new derived dataset, manifests, and immutable-source provenance."""
    if config.output_dir.exists():
        raise ValueError(f"Output directory already exists: {config.output_dir}")
    selected = select_candidates(load_candidates(config), config)
    manifest: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    train_root = config.output_dir / "train"
    for group, items in selected.items():
        for item in items:
            if item.split == "train":
                destination = train_root / f"1_{config.dataset_name}_{group}"
            else:
                destination = config.output_dir / item.split
            output_image, caption = _copy_pair(item, destination, config)
            counts[f"{item.split}_{group}"] += 1
            manifest.append(
                {
                    "source_image": str((config.source_dir / item.image).resolve()),
                    "source_sha256": _sha256(config.source_dir / item.image),
                    "output_image": str(output_image.relative_to(config.output_dir)),
                    "split": item.split,
                    "selection_group": group,
                    "cluster": item.cluster,
                    "archetype": item.archetype,
                    "subject": item.subject,
                    "background": item.background,
                    "framing": item.framing,
                    "caption": caption,
                }
            )
    full_body_train = [
        item
        for item in selected["primary"]
        if item.split == "train" and item.framing == "full_body"
    ]
    boost_dir = train_root / f"1_{config.dataset_name}_fullbody_boost"
    for item in full_body_train:
        output_image, caption = _copy_pair(item, boost_dir, config)
        counts["train_fullbody_boost"] += 1
        manifest.append(
            {
                "source_image": str((config.source_dir / item.image).resolve()),
                "source_sha256": _sha256(config.source_dir / item.image),
                "output_image": str(output_image.relative_to(config.output_dir)),
                "split": "train",
                "selection_group": "fullbody_boost",
                "cluster": item.cluster,
                "archetype": item.archetype,
                "subject": item.subject,
                "background": item.background,
                "framing": item.framing,
                "caption": caption,
            }
        )
    reports = config.output_dir / "reports"
    _write_csv(reports / "selection_manifest.csv", manifest)
    provenance = {
        "created_at": datetime.now(UTC).isoformat(),
        "config": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(config).items()
        },
        "input_sha256": {
            "curation_labels": _sha256(config.curation_labels),
            "split_manifest": _sha256(config.split_manifest),
            "clustering_manifest": _sha256(config.clustering_manifest),
        },
        "counts": dict(sorted(counts.items())),
        "policy": {
            "goal_clusters": sorted(GOAL_CLUSTERS),
            "removed_tags": sorted(DEFAULT_REMOVED_TAGS),
            "review_tags_excluded": sorted(DEFAULT_REVIEW_TAGS),
            "generated_examples_used_for_training": False,
        },
    }
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return dict(sorted(counts.items()))
