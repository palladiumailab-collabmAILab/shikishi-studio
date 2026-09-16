"""Download tagged images from Safebooru with gallery-dl."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

IMAGE_FILTER = "extension in ('jpg', 'jpeg', 'png', 'webp', 'gif')"
INVALID_WINDOWS_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class DownloadConfig:
    """Settings for a Safebooru tag download."""

    tag: str
    page: int
    output_dir: Path
    dry_run: bool = False

    def __post_init__(self) -> None:
        """Validate configuration before running an external command."""
        if not self.tag.strip():
            raise ValueError("Safebooru tag must not be empty.")
        if self.page < 1:
            raise ValueError("Safebooru page must be at least 1.")

    @property
    def tag_directory(self) -> Path:
        """Return a Windows-safe directory dedicated to this tag."""
        safe_tag = INVALID_WINDOWS_FILENAME.sub("_", self.tag).rstrip(". ")
        if not safe_tag:
            raise ValueError("Safebooru tag cannot form a valid directory name.")
        return self.output_dir / safe_tag

    @property
    def source_url(self) -> str:
        """Return the Safebooru listing URL for the requested tag and page."""
        query = urlencode({"page": self.page, "tags": self.tag})
        return f"https://safebooru.donmai.us/posts?{query}"


def build_command(config: DownloadConfig) -> list[str]:
    """Return a gallery-dl command for the configured public listing."""
    output_dir = config.tag_directory.resolve()
    archive_path = output_dir / "gallery-dl-archive.sqlite"
    command = [
        "gallery-dl",
        "--directory",
        str(output_dir),
        "--download-archive",
        str(archive_path),
        "--filter",
        IMAGE_FILTER,
        "--windows-filenames",
        "--write-tags",
    ]

    if config.dry_run:
        command.append("--simulate")

    command.append(config.source_url)
    return command


def download_images(config: DownloadConfig) -> None:
    """Create the tag directory and execute gallery-dl."""
    config.tag_directory.mkdir(parents=True, exist_ok=True)
    command = build_command(config)

    print(f"Downloading Safebooru images tagged '{config.tag}' …")
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as error:
        raise RuntimeError(
            "gallery-dl is unavailable. Install the download dependency before "
            "running this command."
        ) from error

    if config.dry_run:
        print("Dry run complete; no files were downloaded.")
    else:
        print(f"Download complete: {config.tag_directory.resolve()}")
