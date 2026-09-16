"""Create captioned datasets that are compatible with SDXL LoRA training."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})


def normalize_tags(tags: str) -> str:
    """Return a comma-separated, duplicate-free caption from user supplied tags."""
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags.split(","):
        clean_tag = tag.strip()
        if clean_tag and clean_tag not in seen:
            normalized.append(clean_tag)
            seen.add(clean_tag)
    if not normalized:
        raise ValueError("At least one non-empty tag is required.")
    return ", ".join(normalized)


def image_files(directory: Path) -> list[Path]:
    """Return supported images immediately inside a directory, ordered by name."""
    if not directory.is_dir():
        raise ValueError(f"Image directory does not exist: {directory}")
    return sorted(
        (path for path in directory.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS),
        key=lambda path: path.name.lower(),
    )


@dataclass(frozen=True)
class DatasetConfig:
    """Settings for an SDXL style-LoRA dataset export."""

    source_dir: Path
    output_dir: Path
    dataset_name: str
    trigger_word: str
    repeats: int = 10

    def __post_init__(self) -> None:
        """Validate values supplied at the command boundary."""
        if not self.dataset_name.strip():
            raise ValueError("Dataset name must not be empty.")
        if not self.trigger_word.strip():
            raise ValueError("Trigger word must not be empty.")
        if self.repeats < 1:
            raise ValueError("Repeats must be at least 1.")

    @property
    def training_directory(self) -> Path:
        """Return the Kohya-compatible repeated image directory."""
        return self.output_dir / self.dataset_name / f"{self.repeats}_{self.dataset_name}"


def export_dataset(config: DatasetConfig) -> int:
    """Copy images and normalized captions into a Kohya-compatible directory."""
    images = image_files(config.source_dir)
    if not images:
        raise ValueError(f"No supported images found in: {config.source_dir}")

    target_directory = config.training_directory
    target_directory.mkdir(parents=True, exist_ok=True)
    copied = 0
    for image in images:
        source_caption = image.with_suffix(".txt")
        if not source_caption.is_file():
            raise ValueError(f"Missing caption for image: {image.name}")
        source_tags = source_caption.read_text(encoding="utf-8").strip()
        caption = normalize_tags(f"{config.trigger_word}, {source_tags}")
        shutil.copy2(image, target_directory / image.name)
        (target_directory / f"{image.stem}.txt").write_text(caption + "\n", encoding="utf-8")
        copied += 1
    return copied


def package_dataset(config: DatasetConfig) -> Path:
    """Create a ZIP archive ready to upload to Google Drive for Colab training."""
    if not config.training_directory.is_dir():
        raise ValueError(
            "Dataset export is missing. Run export-style-dataset before packaging for Colab."
        )
    archive_base = config.output_dir / f"{config.dataset_name}-colab"
    return Path(
        shutil.make_archive(str(archive_base), "zip", config.output_dir, config.dataset_name)
    )


def split_archive(archive_path: Path, part_size_megabytes: int) -> list[Path]:
    """Split a ZIP into numbered parts suitable for Drive upload limits."""
    if not archive_path.is_file():
        raise ValueError(f"Archive does not exist: {archive_path}")
    if part_size_megabytes < 1:
        raise ValueError("Part size must be at least 1 MB.")

    part_size_bytes = part_size_megabytes * 1024 * 1024
    output_paths: list[Path] = []
    with archive_path.open("rb") as source:
        index = 1
        while chunk := source.read(part_size_bytes):
            output_path = archive_path.with_name(f"{archive_path.name}.part{index:03d}")
            output_path.write_bytes(chunk)
            output_paths.append(output_path)
            index += 1
    return output_paths
