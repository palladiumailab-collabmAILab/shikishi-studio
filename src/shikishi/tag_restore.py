"""Restore missing Danbooru tag sidecars for previously downloaded images."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from shikishi.dataset import IMAGE_EXTENSIONS

POST_ID_PATTERN = re.compile(r"^danbooru_(?P<post_id>\d+)_")
API_URL = "https://safebooru.donmai.us/posts/{post_id}.json"
USER_AGENT = "shikishi/0.1 (local tag restoration)"


@dataclass(frozen=True)
class TagRestoreConfig:
    """Settings for restoring tags without replacing existing captions."""

    images_dir: Path
    request_delay_seconds: float = 0.6

    def __post_init__(self) -> None:
        """Validate configuration supplied at the command boundary."""
        if not self.images_dir.is_dir():
            raise ValueError(f"Image directory does not exist: {self.images_dir}")
        if self.request_delay_seconds < 0:
            raise ValueError("Request delay must not be negative.")


@dataclass(frozen=True)
class TagRestoreResult:
    """Counts produced by one resumable tag restoration pass."""

    restored: int
    skipped_existing: int
    skipped_unrecognized: int
    missing_posts: int


def post_id_from_path(image_path: Path) -> int | None:
    """Extract a Danbooru post ID from a gallery-dl image filename."""
    match = POST_ID_PATTERN.match(image_path.name)
    return int(match.group("post_id")) if match else None


def fetch_tags(post_id: int) -> str | None:
    """Fetch comma-separated tags for one public Safebooru post."""
    request = Request(API_URL.format(post_id=post_id), headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed public API URL
            payload = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise RuntimeError(f"Safebooru returned HTTP {error.code} for post {post_id}.") from error
    except URLError as error:
        raise RuntimeError(f"Unable to reach Safebooru for post {post_id}.") from error

    tag_string = payload.get("tag_string")
    if not isinstance(tag_string, str) or not tag_string.strip():
        raise RuntimeError(f"Safebooru returned no tags for post {post_id}.")
    return ", ".join(tag_string.split())


def restore_tags(config: TagRestoreConfig) -> TagRestoreResult:
    """Create missing sidecar captions, leaving existing user edits unchanged."""
    restored = 0
    skipped_existing = 0
    skipped_unrecognized = 0
    missing_posts = 0

    images = sorted(
        (
            path
            for path in config.images_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ),
        key=lambda path: path.name.lower(),
    )
    for image in images:
        caption_path = image.with_suffix(".txt")
        if caption_path.exists():
            skipped_existing += 1
            continue
        post_id = post_id_from_path(image)
        if post_id is None:
            skipped_unrecognized += 1
            continue
        tags = fetch_tags(post_id)
        if tags is None:
            missing_posts += 1
            continue
        caption_path.write_text(tags + "\n", encoding="utf-8")
        restored += 1
        time.sleep(config.request_delay_seconds)

    return TagRestoreResult(restored, skipped_existing, skipped_unrecognized, missing_posts)
