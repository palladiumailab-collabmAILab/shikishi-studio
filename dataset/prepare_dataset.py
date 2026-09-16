"""Prepare a conservative, reproducible Style LoRA dataset from Danbooru captions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import random
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import imagehash
import yaml
from PIL import Image, UnidentifiedImageError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SAFE_TAG = re.compile(r"^[a-z0-9_:!?'()&+\-.]+$")


def ratio(value: int, total: int, *, precision: int = 1) -> str:
    """Format a count ratio without dividing by zero for empty datasets."""
    if total == 0:
        return f"{0:.{precision}%}"
    return f"{value / total:.{precision}%}"


@dataclass(slots=True)
class Item:
    image: Path
    caption: Path
    width: int
    height: int
    file_hash: str
    phash: imagehash.ImageHash | None
    tags: list[str]
    review_reasons: list[str] = field(default_factory=list)

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("Config must be a YAML mapping.")
    return data


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tokenise_tags(text: str) -> set[str]:
    result: set[str] = set()
    for raw_tag in text.replace("\r", " ").replace("\n", " ").split(","):
        tag = re.sub(r"\s+", "_", raw_tag.strip().lower())
        tag = tag.strip("_")
        if not tag or not SAFE_TAG.fullmatch(tag):
            continue
        result.add(tag)
    return result


def normalise_tags(text: str, config: dict[str, Any], categories: dict[str, str]) -> list[str]:
    remove_tags = {str(tag).strip().lower() for tag in config.get("remove_tags", [])}
    patterns = [
        re.compile(pattern, re.IGNORECASE) for pattern in config.get("remove_tag_patterns", [])
    ]
    remove_categories = {str(category).lower() for category in config.get("remove_categories", [])}
    result: set[str] = set()
    for tag in tokenise_tags(text):
        if tag in remove_tags or any(pattern.search(tag) for pattern in patterns):
            continue
        if categories.get(tag, "").lower() in remove_categories:
            continue
        result.add(tag)
    return sorted(result)


def load_categories(config: dict[str, Any], config_path: Path) -> dict[str, str]:
    configured = config.get("tag_category_file")
    if not configured:
        return {}
    path = Path(str(configured))
    if not path.is_absolute():
        path = config_path.parent / path
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"tag", "category"}.issubset(reader.fieldnames):
            raise ValueError("tag_category_file needs CSV columns: tag,category")
        return {row["tag"].strip().lower(): row["category"].strip().lower() for row in reader}


def source_layout(input_path: Path) -> tuple[Path, Path]:
    images = input_path / "images"
    tags = input_path / "tags"
    if images.is_dir():
        return images, tags if tags.is_dir() else images
    return input_path, input_path


def find_caption(image: Path, tags_root: Path) -> Path | None:
    candidate = tags_root / f"{image.stem}.txt"
    return candidate if candidate.is_file() else None


def image_metrics(
    path: Path, phash_enabled: bool
) -> tuple[int, int, imagehash.ImageHash | None, float]:
    try:
        with Image.open(path) as probe:
            probe.verify()
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            thumb = image.convert("RGB")
            thumb.thumbnail((128, 128))
            pixels = list(thumb.getdata())
            blank_ratio = sum(max(pixel) >= 248 and min(pixel) >= 238 for pixel in pixels) / len(
                pixels
            )
            value = imagehash.phash(thumb) if phash_enabled else None
            return width, height, value, blank_ratio
    except (OSError, UnidentifiedImageError, ValueError) as error:
        raise ValueError(str(error)) from error


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def connected_groups(size: int, pairs: list[tuple[int, int]]) -> list[list[int]]:
    union_find = UnionFind(size)
    for left, right in pairs:
        union_find.union(left, right)
    groups: dict[int, list[int]] = {}
    for index in range(size):
        groups.setdefault(union_find.find(index), []).append(index)
    return list(groups.values())


def split_items(
    items: list[Item], pairs: list[tuple[int, int]], ratio: float, seed: int
) -> dict[int, str]:
    target = max(1, round(len(items) * ratio)) if items else 0
    groups = connected_groups(len(items), pairs)
    random.Random(seed).shuffle(groups)
    validation: set[int] = set()
    for group in groups:
        if len(validation) + len(group) <= target:
            validation.update(group)
    if not validation and groups:
        validation.update(min(groups, key=len))
    return {index: "validation" if index in validation else "train" for index in range(len(items))}


def report_markdown(
    items: list[Item],
    excluded: list[dict[str, Any]],
    duplicate_count: int,
    near_count: int,
    review_count: int,
    split_counts: Counter[str],
    tag_counts: Counter[str],
    warning_ratio: float,
) -> str:
    dimensions = Counter(f"{item.width}x{item.height}" for item in items)
    orientations = Counter(
        "portrait"
        if item.height > item.width
        else "landscape"
        if item.width > item.height
        else "square"
        for item in items
    )
    framings = {
        tag: sum(tag in item.tags for item in items)
        for tag in ("upper_body", "full_body", "cowboy_shot")
    }
    people = {
        tag: sum(tag in item.tags for item in items)
        for tag in ("1girl", "1boy", "solo", "multiple_girls")
    }
    lines = [
        "# Dataset preparation report",
        "",
        "## Summary",
        "",
        f"- Valid images: {len(items)}",
        f"- Excluded images: {len(excluded)}",
        f"- Exact duplicates removed: {duplicate_count}",
        f"- Near-duplicate candidate pairs: {near_count}",
        f"- Images requiring review: {review_count}",
        f"- Train images: {split_counts['train']}",
        f"- Validation images: {split_counts['validation']}",
        "",
        "## Orientation",
        "",
    ]
    lines.extend(f"- {name}: {count}" for name, count in sorted(orientations.items()))
    lines.extend(["", "## Content tag coverage", ""])
    lines.extend(
        f"- {tag}: {count} ({ratio(count, len(items))})"
        for tag, count in {**people, **framings}.items()
    )
    lines.extend(["", "## Most common resolutions", ""])
    lines.extend(f"- {name}: {count}" for name, count in dimensions.most_common(15))
    dominant = [
        (tag, count)
        for tag, count in tag_counts.most_common()
        if len(items) > 0 and count / len(items) >= warning_ratio
    ]
    lines.extend(["", "## Bias warnings", ""])
    if dominant:
        lines.extend(
            f"- `{tag}` appears in {ratio(count, len(items))} of captions."
            for tag, count in dominant
        )
    else:
        lines.append("- No tag exceeded the configured warning threshold.")
    return "\n".join(lines) + "\n"


def prepare(input_path: Path, output_path: Path, config_path: Path, overwrite: bool) -> None:
    config = load_config(config_path)
    input_path, output_path = input_path.resolve(), output_path.resolve()
    if (
        input_path == output_path
        or input_path in output_path.parents
        or output_path in input_path.parents
    ):
        raise ValueError("Output must not overlap the source directory.")
    if output_path.exists() and any(output_path.iterdir()):
        if not overwrite:
            raise FileExistsError("Output exists. Use --overwrite to replace it.")
        shutil.rmtree(output_path)
    reports = output_path.parent / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=reports / "processing.log",
        format="%(asctime)s %(levelname)s %(message)s",
        level=logging.INFO,
        force=True,
    )
    categories = load_categories(config, config_path)
    images_root, tags_root = source_layout(input_path)
    image_paths = sorted(
        path for path in images_root.rglob("*") if path.suffix.lower() in IMAGE_EXTENSIONS
    )
    excluded: list[dict[str, Any]] = []
    valid: list[Item] = []
    hash_owner: dict[str, Path] = {}
    quality = config.get("quality_filter", {})
    phash_enabled = bool(config.get("duplicate", {}).get("phash_enabled", True))

    for image_path in image_paths:
        caption_path = find_caption(image_path, tags_root)
        if caption_path is None:
            excluded.append({"source_image": str(image_path), "reason": "missing_caption"})
            continue
        try:
            width, height, phash, blank_ratio = image_metrics(image_path, phash_enabled)
        except ValueError as error:
            excluded.append({"source_image": str(image_path), "reason": f"unreadable:{error}"})
            continue
        ratio = width / height
        if width < int(config["min_width"]) or height < int(config["min_height"]):
            excluded.append({"source_image": str(image_path), "reason": "below_minimum_resolution"})
            continue
        if ratio < float(config["min_aspect_ratio"]) or ratio > float(config["max_aspect_ratio"]):
            excluded.append({"source_image": str(image_path), "reason": "extreme_aspect_ratio"})
            continue
        digest = sha256(image_path)
        if digest in hash_owner:
            excluded.append(
                {
                    "source_image": str(image_path),
                    "reason": f"exact_duplicate_of:{hash_owner[digest]}",
                }
            )
            continue
        hash_owner[digest] = image_path
        caption_text = caption_path.read_text(encoding="utf-8", errors="replace")
        raw_tags = tokenise_tags(caption_text)
        tags = normalise_tags(caption_text, config, categories)
        reviews: list[str] = []
        if quality.get("enabled", True):
            if image_path.suffix.lower() in {".jpg", ".jpeg"} and image_path.stat().st_size / (
                width * height
            ) < float(quality["jpeg_min_bytes_per_pixel"]):
                reviews.append("possible_jpeg_compression")
            if blank_ratio >= float(quality["high_blank_ratio"]):
                reviews.append("large_blank_area")
            review_tags = set(quality.get("review_tags", []))
            tagged = sorted(review_tags.intersection(tags))
            if tagged:
                reviews.append("source_tags:" + "|".join(tagged))
            if {"duplicate", "pixel-perfect_duplicate"}.intersection(raw_tags):
                reviews.append("source_duplicate_tag")
        if reviews and bool(quality.get("auto_delete", False)):
            excluded.append(
                {"source_image": str(image_path), "reason": "quality_filter:" + ";".join(reviews)}
            )
            continue
        valid.append(Item(image_path, caption_path, width, height, digest, phash, tags, reviews))

    threshold = int(config.get("duplicate", {}).get("phash_threshold", 5))
    near_rows: list[dict[str, Any]] = []
    near_edges: list[tuple[int, int]] = []
    if phash_enabled:
        for left in range(len(valid)):
            for right in range(left + 1, len(valid)):
                if valid[left].phash is None or valid[right].phash is None:
                    continue
                distance = valid[left].phash - valid[right].phash
                if distance <= threshold:
                    near_edges.append((left, right))
                    near_rows.append(
                        {
                            "source_image_a": str(valid[left].image),
                            "source_image_b": str(valid[right].image),
                            "phash_distance": distance,
                            "action": "review_and_keep",
                        }
                    )

    assignments = split_items(
        valid, near_edges, float(config["validation_ratio"]), int(config["random_seed"])
    )
    tag_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    review_rows: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    for index, item in enumerate(valid, start=1):
        split = assignments[index - 1]
        split_counts[split] += 1
        tag_counts.update(item.tags)
        destination_dir = output_path / split
        destination_dir.mkdir(exist_ok=True)
        destination_image = destination_dir / f"{index:06d}{item.image.suffix.lower()}"
        destination_caption = destination_image.with_suffix(".txt")
        shutil.copy2(item.image, destination_image)
        destination_caption.write_text(", ".join(item.tags) + "\n", encoding="utf-8")
        manifest.append(
            {
                "output_image": str(destination_image.relative_to(output_path)),
                "split": split,
                "source_image": str(item.image),
                "source_caption": str(item.caption),
                "width": item.width,
                "height": item.height,
                "aspect_ratio": f"{item.aspect_ratio:.4f}",
                "tag_count": len(item.tags),
            }
        )
        if item.review_reasons:
            review_rows.append(
                {"source_image": str(item.image), "reasons": ";".join(item.review_reasons)}
            )

    write_csv(reports / "excluded_images.csv", excluded, ["source_image", "reason"])
    write_csv(
        reports / "duplicate_candidates.csv",
        near_rows,
        ["source_image_a", "source_image_b", "phash_distance", "action"],
    )
    write_csv(reports / "review_candidates.csv", review_rows, ["source_image", "reasons"])
    write_csv(
        reports / "split_manifest.csv",
        manifest,
        list(manifest[0])
        if manifest
        else [
            "output_image",
            "split",
            "source_image",
            "source_caption",
            "width",
            "height",
            "aspect_ratio",
            "tag_count",
        ],
    )
    frequency_rows = [
        {
            "tag": tag,
            "count": count,
            "ratio": f"{count / len(valid):.6f}" if valid else "0.000000",
        }
        for tag, count in tag_counts.most_common()
    ]
    write_csv(reports / "tag_frequency.csv", frequency_rows, ["tag", "count", "ratio"])
    warning_ratio = float(config.get("dominant_tag_warning_ratio", 0.75))
    (reports / "dataset_report.md").write_text(
        report_markdown(
            valid,
            excluded,
            sum("exact_duplicate" in row["reason"] for row in excluded),
            len(near_rows),
            len(review_rows),
            split_counts,
            tag_counts,
            warning_ratio,
        ),
        encoding="utf-8",
    )
    summary = {
        "Original images": len(image_paths),
        "Valid images": len(valid),
        "Exact duplicates": sum("exact_duplicate" in row["reason"] for row in excluded),
        "Near duplicates": len(near_rows),
        "Quality rejected": len(excluded),
        "Review required": len(review_rows),
        "Train images": split_counts["train"],
        "Validation images": split_counts["validation"],
    }
    logging.info("Completed: %s", json.dumps(summary, ensure_ascii=False))
    for key, value in summary.items():
        print(f"{key}: {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    prepare(args.input, args.output, args.config, args.overwrite)


if __name__ == "__main__":
    main()
