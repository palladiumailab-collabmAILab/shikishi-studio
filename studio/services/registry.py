from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from studio.config import Settings
from studio.schemas import ModelSummary


@dataclass(frozen=True, slots=True)
class ModelSpec:
    id: str
    name: str
    base_model: str
    lora_path: Path
    default_lora_scale: float
    trigger_words: list[str]
    base_model_revision: str | None
    training_base_model: str | None

    def summary(self) -> ModelSummary:
        return ModelSummary(
            id=self.id,
            name=self.name,
            base_model=self.base_model,
            lora_filename=self.lora_path.name,
            default_lora_scale=self.default_lora_scale,
            trigger_words=self.trigger_words,
            base_model_revision=self.base_model_revision,
        )


class ModelRegistry:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._models = self._load_models()

    def get(self, model_id: str | None) -> ModelSpec:
        selected_id = model_id or self._settings.default_model_id
        try:
            return self._models[selected_id]
        except KeyError as exc:
            raise ValueError(f"Unknown model_id: {selected_id}") from exc

    def list_summaries(self) -> list[ModelSummary]:
        return [model.summary() for model in self._models.values()]

    def _load_models(self) -> dict[str, ModelSpec]:
        raw_registry = json.loads(self._settings.model_registry_path.read_text(encoding="utf-8"))
        models = {}
        for raw_model in raw_registry.get("models", []):
            configured_base_model = raw_model["base_model"]
            base_model = self._settings.base_model_override or configured_base_model
            base_model_revision = raw_model.get("base_model_revision")
            if base_model != configured_base_model:
                base_model_revision = None
            model = ModelSpec(
                id=raw_model["id"],
                name=raw_model["name"],
                base_model=base_model,
                lora_path=self._settings.root_dir / raw_model["lora_path"],
                default_lora_scale=float(raw_model.get("default_lora_scale", 1.0)),
                trigger_words=list(raw_model.get("trigger_words", [])),
                base_model_revision=base_model_revision,
                training_base_model=raw_model.get("training_base_model"),
            )
            if not model.lora_path.exists():
                raise FileNotFoundError(f"LoRA weight not found: {model.lora_path}")
            models[model.id] = model
        if not models:
            raise ValueError("Model registry contains no models")
        return models
