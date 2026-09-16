from __future__ import annotations

import hashlib
import io
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import cast

from PIL import Image, ImageOps, UnidentifiedImageError

from studio.config import Settings
from studio.schemas import ReferenceImageRecord

ALLOWED_IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}


class ReferenceImageStore:
    """Validates and preserves uploaded reference images and normalized derivatives."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._source_dir = settings.reference_dir / "source"
        self._normalized_dir = settings.reference_dir / "normalized"
        self._metadata_dir = settings.reference_dir / "metadata"
        self._lock = Lock()
        for path in (self._source_dir, self._normalized_dir, self._metadata_dir):
            path.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, claimed_media_type: str) -> ReferenceImageRecord:
        if not data:
            raise ValueError("参照画像が空です")
        if len(data) > self._settings.max_reference_image_bytes:
            raise ValueError("参照画像は10MB以下にしてください")
        try:
            with Image.open(io.BytesIO(data)) as probe:
                image_format = probe.format
                width, height = probe.size
                probe.verify()
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
            raise ValueError("PNG、JPEG、WebPの有効な画像を指定してください") from exc
        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise ValueError("PNG、JPEG、WebPのみ使用できます")
        media_type, extension = ALLOWED_IMAGE_FORMATS[image_format]
        if claimed_media_type.split(";", 1)[0].lower() != media_type:
            raise ValueError("画像のContent-Typeと実際の形式が一致しません")
        if width * height > self._settings.max_reference_pixels:
            raise ValueError("参照画像は1,600万画素以下にしてください")

        source_sha256 = hashlib.sha256(data).hexdigest()
        with self._lock:
            existing = self._find_by_sha256(source_sha256)
            if existing is not None:
                return existing
            reference_id = uuid.uuid4().hex
            self._source_path(reference_id, extension).write_bytes(data)
            with Image.open(io.BytesIO(data)) as source:
                transposed = ImageOps.exif_transpose(source)
                if transposed is None:
                    raise RuntimeError("参照画像の向きを補正できません")
                normalized = transposed.convert("RGB")
                normalized.save(self.normalized_path(reference_id), format="PNG", optimize=True)
                normalized_width, normalized_height = normalized.size
            record = ReferenceImageRecord(
                id=reference_id,
                created_at=datetime.now(UTC).isoformat(),
                media_type=media_type,
                source_sha256=source_sha256,
                source_size_bytes=len(data),
                width=normalized_width,
                height=normalized_height,
                preview_url=f"/api/reference-images/{reference_id}",
            )
            self._write_atomic(self._metadata_path(reference_id), record.model_dump_json(indent=2))
            return record

    def _find_by_sha256(self, source_sha256: str) -> ReferenceImageRecord | None:
        for metadata_path in self._metadata_dir.glob("*.json"):
            try:
                record = ReferenceImageRecord.model_validate_json(
                    metadata_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            if record.source_sha256 == source_sha256 and self.normalized_path(record.id).exists():
                return record
        return None

    def get(self, reference_id: str) -> ReferenceImageRecord:
        if len(reference_id) != 32 or any(
            character not in "0123456789abcdef" for character in reference_id
        ):
            raise ValueError("参照画像IDが不正です")
        try:
            return ReferenceImageRecord.model_validate_json(
                self._metadata_path(reference_id).read_text(encoding="utf-8")
            )
        except FileNotFoundError as exc:
            raise ValueError(f"参照画像が見つかりません: {reference_id}") from exc

    def normalized_path(self, reference_id: str) -> Path:
        return self._normalized_dir / f"{reference_id}.png"

    def prepare(
        self,
        reference_id: str,
        width: int,
        height: int,
        focus_x: float,
        focus_y: float,
        zoom: float,
    ) -> Image.Image:
        self.get(reference_id)
        with Image.open(self.normalized_path(reference_id)) as source:
            image = source.convert("RGB")
        source_width, source_height = image.size
        target_ratio = width / height
        source_ratio = source_width / source_height
        if source_ratio >= target_ratio:
            crop_height = source_height / zoom
            crop_width = crop_height * target_ratio
        else:
            crop_width = source_width / zoom
            crop_height = crop_width / target_ratio
        center_x = focus_x * source_width
        center_y = focus_y * source_height
        left = min(max(center_x - crop_width / 2, 0), source_width - crop_width)
        top = min(max(center_y - crop_height / 2, 0), source_height - crop_height)
        cropped = image.crop(
            (round(left), round(top), round(left + crop_width), round(top + crop_height))
        )
        return cast(Image.Image, cropped.resize((width, height), Image.Resampling.LANCZOS))

    def _source_path(self, reference_id: str, extension: str) -> Path:
        return self._source_dir / f"{reference_id}{extension}"

    def _metadata_path(self, reference_id: str) -> Path:
        return self._metadata_dir / f"{reference_id}.json"

    @staticmethod
    def _write_atomic(path: Path, content: str) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(content, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
