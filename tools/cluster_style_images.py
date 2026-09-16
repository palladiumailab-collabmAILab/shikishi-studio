# mypy: disable-error-code=type-arg

"""Cluster illustration images by visual style and copy them to stable folders.

The input tree is read-only.  Outputs contain copied images/captions, a
machine-readable manifest, run configuration, and contact sheets for review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from transformers import AutoImageProcessor, AutoModel

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
DEFAULT_SEED = 20260825


@dataclass(frozen=True)
class ImageRecord:
    source: Path
    width: int
    height: int
    sha256: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="facebook/dinov2-small")
    parser.add_argument("--min-clusters", type=int, default=4)
    parser.add_argument("--max-clusters", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def discover_images(input_dir: Path) -> list[ImageRecord]:
    if not input_dir.is_dir():
        raise ValueError(f"Input directory does not exist: {input_dir}")
    records: list[ImageRecord] = []
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        try:
            with Image.open(path) as image:
                image.load()
                width, height = image.size
                if width < 32 or height < 32:
                    raise ValueError(f"image is too small: {width}x{height}")
            records.append(ImageRecord(path, width, height, sha256(path)))
        except (OSError, UnidentifiedImageError, ValueError) as error:
            raise ValueError(f"Unreadable image {path}: {error}") from error
    if not records:
        raise ValueError(f"No supported images found in: {input_dir}")
    return records


def style_features(path: Path) -> np.ndarray:
    """Return deterministic low-level color/line features complementary to DINO."""
    with Image.open(path) as image:
        rgb = np.asarray(ImageOps.fit(image.convert("RGB"), (64, 64)), dtype=np.float32) / 255.0
    gray = rgb.mean(axis=2)
    hsv = np.asarray(
        Image.fromarray((rgb * 255).astype(np.uint8), "RGB").convert("HSV"), dtype=np.float32
    )
    hsv /= 255.0
    dx = np.diff(gray, axis=1, append=gray[:, -1:])
    dy = np.diff(gray, axis=0, append=gray[-1:, :])
    magnitude = np.sqrt(dx * dx + dy * dy)
    angle = (np.arctan2(dy, dx) + math.pi) / (2 * math.pi)
    orientation = np.histogram(angle, bins=18, range=(0.0, 1.0), weights=magnitude)[0]
    histograms = [
        np.histogram(channel, bins=16, range=(0.0, 1.0), density=True)[0]
        for channel in (rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2], hsv[:, :, 0], hsv[:, :, 1], gray)
    ]
    contrast = np.abs(gray - gray.mean())
    flatness = np.array(
        [
            float(np.mean(magnitude < 0.04)),
            float(np.mean(magnitude > 0.20)),
            float(np.mean(contrast < 0.08)),
            float(np.mean(hsv[:, :, 1] < 0.12)),
        ],
        dtype=np.float32,
    )
    thumbnail = np.asarray(
        ImageOps.fit(Image.fromarray((gray * 255).astype(np.uint8)), (16, 16)), dtype=np.float32
    )
    vector = np.concatenate([*histograms, orientation, flatness, thumbnail.ravel()])
    return vector.astype(np.float32)  # type: ignore[no-any-return]


def extract_dino_features(
    records: list[ImageRecord], model_name: str, batch_size: int
) -> np.ndarray:
    processor = AutoImageProcessor.from_pretrained(model_name)  # type: ignore[no-untyped-call]
    model = AutoModel.from_pretrained(model_name)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()
    embeddings: list[np.ndarray] = []
    with torch.inference_mode():
        for start in range(0, len(records), batch_size):
            batch_images: list[Image.Image] = []
            for record in records[start : start + batch_size]:
                with Image.open(record.source) as image:
                    batch_images.append(image.convert("RGB"))
            inputs = processor(images=batch_images, return_tensors="pt")
            inputs = {key: value.to(device) for key, value in inputs.items()}
            outputs = model(**inputs)
            patch_tokens = outputs.last_hidden_state[:, 1:, :]
            patch_mean = patch_tokens.mean(dim=1)
            patch_std = patch_tokens.std(dim=1)
            batch = torch.cat([patch_mean * 0.3, patch_std * 0.7], dim=1)
            batch = torch.nn.functional.normalize(batch, dim=1)
            embeddings.append(batch.cpu().numpy().astype(np.float32))
            print(f"embedded {min(start + batch_size, len(records))}/{len(records)}", flush=True)
    return np.concatenate(embeddings, axis=0)


def normalize_rows(values: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    return values / np.maximum(norms, 1e-8)  # type: ignore[no-any-return]


def combined_features(records: list[ImageRecord], dino: np.ndarray) -> np.ndarray:
    handcrafted = np.stack([style_features(record.source) for record in records])
    centered = handcrafted - handcrafted.mean(axis=0, keepdims=True)
    scale = centered.std(axis=0, keepdims=True)
    handcrafted = normalize_rows(centered / np.maximum(scale, 1e-6))
    dino = normalize_rows(dino)
    return normalize_rows(np.concatenate([dino * 0.75, handcrafted * 0.25], axis=1))


def kmeans(
    values: np.ndarray, clusters: int, seed: int, iterations: int = 40
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    centers = np.empty((clusters, values.shape[1]), dtype=np.float32)
    first = int(rng.integers(values.shape[0]))
    centers[0] = values[first]
    distances = np.full(values.shape[0], np.inf, dtype=np.float32)
    for index in range(1, clusters):
        distances = np.minimum(distances, np.maximum(1.0 - values @ centers[index - 1], 0.0))
        probabilities = distances / max(float(distances.sum()), 1e-8)
        centers[index] = values[int(rng.choice(values.shape[0], p=probabilities))]
    labels = np.zeros(values.shape[0], dtype=np.int32)
    for _ in range(iterations):
        new_labels = np.argmax(values @ centers.T, axis=1).astype(np.int32)
        if np.array_equal(labels, new_labels):
            break
        labels = new_labels
        for index in range(clusters):
            members = values[labels == index]
            if len(members):
                centers[index] = normalize_rows(members.mean(axis=0, keepdims=True))[0]
    distances = 1.0 - np.sum(values * centers[labels], axis=1)
    return labels, distances


def silhouette_sample(values: np.ndarray, labels: np.ndarray, seed: int, limit: int = 400) -> float:
    rng = np.random.default_rng(seed)
    selected = (
        np.arange(len(values))
        if len(values) <= limit
        else np.sort(rng.choice(len(values), limit, replace=False))
    )
    sample = values[selected]
    distances = np.clip(1.0 - sample @ values.T, 0.0, 2.0)
    scores: list[float] = []
    for row, item_index in enumerate(selected):
        own = labels[item_index]
        same = labels == own
        same[item_index] = False
        a = float(distances[row, same].mean()) if np.any(same) else 0.0
        b = min(
            float(distances[row, labels == other].mean())
            for other in sorted(set(labels.tolist()))
            if other != own
        )
        scores.append((b - a) / max(a, b, 1e-8))
    return float(np.mean(scores))


def choose_clusters(
    values: np.ndarray, minimum: int, maximum: int, seed: int
) -> tuple[int, dict[int, float]]:
    if minimum < 2 or maximum < minimum:
        raise ValueError("Cluster range must satisfy 2 <= min-clusters <= max-clusters")
    maximum = min(maximum, max(2, len(values) // 10))
    scores: dict[int, float] = {}
    best: tuple[float, int] | None = None
    for clusters in range(minimum, maximum + 1):
        labels, _ = kmeans(values, clusters, seed + clusters)
        score = silhouette_sample(values, labels, seed + clusters)
        scores[clusters] = score
        print(f"k={clusters} silhouette={score:.4f}", flush=True)
        candidate = (score, -clusters)
        if best is None or candidate > best:
            best = candidate
    assert best is not None
    return -best[1], scores


def write_contact_sheet(paths: list[Path], labels: list[str], output: Path, title: str) -> None:
    cell_w, cell_h = 220, 250
    columns = 5
    rows = max(1, math.ceil(len(paths) / columns))
    sheet = Image.new("RGB", (cell_w * columns, cell_h * rows + 36), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 8), title, fill=(20, 20, 20))
    for index, (path, label) in enumerate(zip(paths, labels, strict=True)):
        try:
            with Image.open(path) as image:
                image = ImageOps.contain(image.convert("RGB"), (cell_w - 12, cell_h - 48))
                x = (index % columns) * cell_w + (cell_w - image.width) // 2
                y = 36 + (index // columns) * cell_h + 4
                sheet.paste(image, (x, y))
            draw.text(
                ((index % columns) * cell_w + 6, 36 + (index // columns) * cell_h + cell_h - 36),
                label[:34],
                fill=(20, 20, 20),
            )
        except (OSError, UnidentifiedImageError):
            continue
    sheet.save(output, quality=90)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def copy_outputs(
    records: list[ImageRecord], labels: np.ndarray, distances: np.ndarray, output: Path
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    counters: dict[int, int] = {}
    for record, label, distance in zip(records, labels.tolist(), distances.tolist(), strict=True):
        cluster = int(label) + 1
        counters[cluster] = counters.get(cluster, 0) + 1
        destination_dir = output / f"style_{cluster:02d}"
        destination_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"style_{cluster:02d}_{counters[cluster]:04d}__"
        destination = destination_dir / f"{prefix}{record.source.name}"
        shutil.copy2(record.source, destination)
        caption = record.source.with_suffix(".txt")
        caption_destination = destination.with_suffix(".txt")
        if caption.is_file():
            shutil.copy2(caption, caption_destination)
        rows.append(
            {
                "cluster": f"style_{cluster:02d}",
                "distance_to_centroid": f"{float(distance):.8f}",
                "source": str(record.source),
                "source_sha256": record.sha256,
                "output_image": str(destination),
                "output_caption": str(caption_destination) if caption.is_file() else "",
                "width": record.width,
                "height": record.height,
            }
        )
    return rows


def main() -> None:
    args = parse_args()
    input_dir = args.input.resolve()
    output = args.output.resolve()
    if input_dir == output or output.is_relative_to(input_dir):
        raise ValueError("Output must be separate from the input tree")
    if output.exists() and any(output.iterdir()) and not args.force:
        raise ValueError(f"Output is not empty; use --force only for a deliberate rerun: {output}")
    if args.force and output.exists():
        for child in output.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    output.mkdir(parents=True, exist_ok=True)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    records = discover_images(input_dir)
    print(f"validated {len(records)} images", flush=True)
    dino = extract_dino_features(records, args.model, args.batch_size)
    features = combined_features(records, dino)
    clusters, silhouette_scores = choose_clusters(
        features, args.min_clusters, args.max_clusters, args.seed
    )
    labels, distances = kmeans(features, clusters, args.seed + 1000)
    rows = copy_outputs(records, labels, distances, output)
    reports = output / "reports"
    reports.mkdir(exist_ok=True)
    write_csv(
        reports / "clustering_manifest.csv",
        sorted(rows, key=lambda row: (row["cluster"], row["source"])),
        [
            "cluster",
            "distance_to_centroid",
            "source",
            "source_sha256",
            "output_image",
            "output_caption",
            "width",
            "height",
        ],
    )
    summary = []
    for cluster in range(1, clusters + 1):
        members = [row for row in rows if row["cluster"] == f"style_{cluster:02d}"]
        summary.append({"cluster": f"style_{cluster:02d}", "images": len(members)})
        nearest = sorted(
            ((float(row["distance_to_centroid"]), Path(row["output_image"])) for row in members),
            key=lambda item: item[0],
        )[:20]
        contact_dir = reports / "contact_sheets"
        contact_dir.mkdir(exist_ok=True)
        write_contact_sheet(
            [path for _, path in nearest],
            [path.name for _, path in nearest],
            contact_dir / f"style_{cluster:02d}.jpg",
            f"style_{cluster:02d} ({len(members)} images)",
        )
    write_csv(reports / "cluster_summary.csv", summary, ["cluster", "images"])
    config = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "input": str(input_dir),
        "output": str(output),
        "model": args.model,
        "seed": args.seed,
        "min_clusters": args.min_clusters,
        "max_clusters": args.max_clusters,
        "selected_clusters": clusters,
        "silhouette_scores": {str(key): value for key, value in silhouette_scores.items()},
        "feature_recipe": (
            "DINOv2 spatial-token mean/std 70% + standardized color/line/contrast features 30%"
        ),
        "validated_images": len(records),
        "source_unchanged": True,
    }
    (reports / "run_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {"clusters": clusters, "images": len(records), "output": str(output)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
