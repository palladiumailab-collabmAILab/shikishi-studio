from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CharacterReference(BaseModel):
    reference_image_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    role: Literal["appearance", "face"] = "appearance"
    focus_x: float = Field(default=0.5, ge=0, le=1)
    focus_y: float = Field(default=0.5, ge=0, le=1)
    zoom: float = Field(default=1.0, ge=1, le=4)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2_000)
    pose_prompt: str = Field(default="", max_length=300)
    negative_prompt: str = Field(default="lowres, blurry, bad anatomy, text, watermark")
    width: int = Field(default=1024, ge=512, le=1536, multiple_of=64)
    height: int = Field(default=1024, ge=512, le=1536, multiple_of=64)
    steps: int = Field(default=30, ge=1, le=60)
    guidance_scale: float = Field(default=5.5, ge=0, le=20)
    lora_scale: float = Field(default=0.85, ge=0, le=1.5)
    seed: int | None = Field(default=None, ge=0, le=4_294_967_295)
    num_images: int = Field(default=1, ge=1, le=4)
    model_id: str | None = None
    single_subject: bool = True
    standard_proportions: bool = True
    use_trigger_words: bool = True
    character_profile_id: str | None = Field(default=None, max_length=100)
    reference_image_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    reference_mode: Literal["img2img", "ip_adapter", "img2img_ip_adapter"] = "img2img"
    reference_strength: float = Field(default=0.4, ge=0.1, le=0.95)
    reference_ip_adapter_scale: float = Field(default=0.35, ge=0, le=1.5)
    reference_focus_x: float = Field(default=0.5, ge=0, le=1)
    reference_focus_y: float = Field(default=0.5, ge=0, le=1)
    reference_zoom: float = Field(default=1.0, ge=1, le=4)
    character_references: list[CharacterReference] = Field(default_factory=list, max_length=6)
    reference_face_ip_adapter_scale: float = Field(default=0.25, ge=0, le=1.5)
    reference_face_refinement_strength: float = Field(default=0.2, ge=0.1, le=0.5)
    pose_reference_image_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    pose_reference_strength: float = Field(default=0.3, ge=0.1, le=0.95)
    pose_reference_focus_x: float = Field(default=0.5, ge=0, le=1)
    pose_reference_focus_y: float = Field(default=0.5, ge=0, le=1)
    pose_reference_zoom: float = Field(default=1.0, ge=1, le=4)


class GeneratedImage(BaseModel):
    filename: str
    image_url: str
    seed: int


class EvaluationRequest(BaseModel):
    identity_score: int = Field(ge=1, le=5)
    style_score: int = Field(ge=1, le=5)
    pose_score: int = Field(ge=1, le=5)
    notes: str = Field(default="", max_length=500)


class EvaluationRecord(EvaluationRequest):
    filename: str
    created_at: str


class GenerateResponse(BaseModel):
    images: list[GeneratedImage]


class HistoryItem(GeneratedImage):
    created_at: str
    prompt: str
    pose_prompt: str = ""
    negative_prompt: str
    width: int
    height: int
    steps: int
    guidance_scale: float
    lora_scale: float
    lora: str
    model_id: str
    base_model: str
    app_version: str
    single_subject: bool | None = None
    standard_proportions: bool | None = None
    use_trigger_words: bool = True
    character_profile_id: str | None = None
    base_model_revision: str | None = None
    reference_image_id: str | None = None
    reference_mode: str | None = None
    reference_strength: float | None = None
    reference_ip_adapter_scale: float | None = None
    reference_focus_x: float | None = None
    reference_focus_y: float | None = None
    reference_zoom: float | None = None
    character_references: list[CharacterReference] = Field(default_factory=list)
    reference_face_ip_adapter_scale: float | None = None
    reference_face_refinement_strength: float | None = None
    pose_reference_image_id: str | None = None
    pose_reference_strength: float | None = None
    pose_reference_focus_x: float | None = None
    pose_reference_focus_y: float | None = None
    pose_reference_zoom: float | None = None


class StatusResponse(BaseModel):
    ready: bool
    device: str
    queue_depth: int
    active_job_id: str | None
    app_version: str


class ModelSummary(BaseModel):
    id: str
    name: str
    base_model: str
    lora_filename: str
    default_lora_scale: float
    trigger_words: list[str]
    base_model_revision: str | None = None


class CharacterProfileSummary(BaseModel):
    id: str
    name: str
    prompt: str
    negative_prompt: str = ""
    lora_scale: float = Field(ge=0, le=1.5)
    guidance_scale: float = Field(ge=0, le=20)
    single_subject: bool = True


class ReferenceImageRecord(BaseModel):
    id: str
    created_at: str
    media_type: str
    source_sha256: str
    source_size_bytes: int
    width: int
    height: int
    preview_url: str


class JobResponse(BaseModel):
    id: str
    status: str
    progress: float
    message: str | None = None
    images: list[GeneratedImage] = Field(default_factory=list)
    error: str | None = None
