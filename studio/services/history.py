from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path

from studio.config import Settings
from studio.schemas import (
    EvaluationRecord,
    EvaluationRequest,
    GeneratedImage,
    GenerateRequest,
    HistoryItem,
)
from studio.services.registry import ModelSpec

logger = logging.getLogger(__name__)


class HistoryStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def save(self, image: GeneratedImage, request: GenerateRequest, model: ModelSpec) -> None:
        metadata = HistoryItem(
            **image.model_dump(),
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            prompt=request.prompt,
            pose_prompt=request.pose_prompt,
            negative_prompt=request.negative_prompt,
            width=request.width,
            height=request.height,
            steps=request.steps,
            guidance_scale=request.guidance_scale,
            lora_scale=request.lora_scale,
            lora=model.lora_path.name,
            model_id=model.id,
            base_model=model.base_model,
            app_version=self._settings.app_version,
            single_subject=request.single_subject,
            standard_proportions=request.standard_proportions,
            use_trigger_words=request.use_trigger_words,
            character_profile_id=request.character_profile_id,
            base_model_revision=model.base_model_revision,
            reference_image_id=request.reference_image_id,
            reference_mode=request.reference_mode if request.reference_image_id else None,
            reference_strength=request.reference_strength if request.reference_image_id else None,
            reference_ip_adapter_scale=(
                request.reference_ip_adapter_scale if request.reference_image_id else None
            ),
            reference_focus_x=request.reference_focus_x if request.reference_image_id else None,
            reference_focus_y=request.reference_focus_y if request.reference_image_id else None,
            reference_zoom=request.reference_zoom if request.reference_image_id else None,
            character_references=request.character_references,
            reference_face_ip_adapter_scale=(
                request.reference_face_ip_adapter_scale
                if any(reference.role == "face" for reference in request.character_references)
                else None
            ),
            reference_face_refinement_strength=(
                request.reference_face_refinement_strength
                if any(reference.role == "face" for reference in request.character_references)
                else None
            ),
            pose_reference_image_id=request.pose_reference_image_id,
            pose_reference_strength=(
                request.pose_reference_strength if request.pose_reference_image_id else None
            ),
            pose_reference_focus_x=(
                request.pose_reference_focus_x if request.pose_reference_image_id else None
            ),
            pose_reference_focus_y=(
                request.pose_reference_focus_y if request.pose_reference_image_id else None
            ),
            pose_reference_zoom=(
                request.pose_reference_zoom if request.pose_reference_image_id else None
            ),
        )
        self._write_atomic(self._metadata_path(image.filename), metadata.model_dump_json(indent=2))

    def save_evaluation(self, filename: str, evaluation: EvaluationRequest) -> EvaluationRecord:
        safe_filename = Path(filename).name
        if safe_filename != filename or not safe_filename.lower().endswith(".png"):
            raise ValueError("生成画像のファイル名が不正です")
        if (
            not self.image_path(safe_filename).exists()
            or not self._metadata_path(safe_filename).exists()
        ):
            raise ValueError(f"生成画像が見つかりません: {safe_filename}")
        record = EvaluationRecord(
            **evaluation.model_dump(),
            filename=safe_filename,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        )
        self._write_atomic(self._evaluation_path(safe_filename), record.model_dump_json(indent=2))
        return record

    def list_items(self) -> list[HistoryItem]:
        items: list[HistoryItem] = []
        for metadata_path in sorted(
            self._settings.output_dir.glob("*.png.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            item = self._read_item(metadata_path)
            if item and self.image_path(item.filename).exists():
                items.append(item)
        return items

    def image_path(self, filename: str) -> Path:
        return self._settings.output_dir / Path(filename).name

    def _metadata_path(self, filename: str) -> Path:
        return self.image_path(filename).with_suffix(".png.json")

    def _evaluation_path(self, filename: str) -> Path:
        return self.image_path(filename).with_suffix(".evaluation.json")

    @staticmethod
    def _write_atomic(path: Path, content: str) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(content, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _read_item(self, metadata_path: Path) -> HistoryItem | None:
        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
            data["image_url"] = f"/images/{data['filename']}"
            return HistoryItem.model_validate(data)
        except (OSError, KeyError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("invalid_history_metadata path=%s error=%s", metadata_path.name, exc)
            return None
