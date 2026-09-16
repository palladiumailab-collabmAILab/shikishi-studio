from __future__ import annotations

import gc
import logging
import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Any

import torch
from diffusers import (
    EulerAncestralDiscreteScheduler,
    StableDiffusionXLImg2ImgPipeline,
    StableDiffusionXLPipeline,
)
from PIL import Image
from transformers import CLIPVisionModelWithProjection

from studio.config import Settings
from studio.schemas import GeneratedImage, GenerateRequest
from studio.services.history import HistoryStore
from studio.services.references import ReferenceImageStore
from studio.services.registry import ModelSpec

SINGLE_SUBJECT_PROMPT = "solo, single character, one person"
SINGLE_SUBJECT_NEGATIVE = (
    "multiple people, multiple girls, multiple boys, 2girls, 3girls, 4girls, "
    "2boys, group, crowd, collage, split screen, comic, panels, grid"
)
STANDARD_PROPORTIONS_PROMPT = "normal proportions, detailed anatomy"
STANDARD_PROPORTIONS_NEGATIVE = "chibi, super deformed, oversized head, tiny body"
logger = logging.getLogger(__name__)


def build_conditioning(
    request: GenerateRequest, trigger_words: list[str] | None = None
) -> tuple[str, str]:
    """Return effective prompts while preserving the user's original request."""
    prompt_parts: list[str] = []
    if request.use_trigger_words:
        prompt_parts.extend(
            trigger
            for trigger in (trigger_words or [])
            if trigger.lower() not in request.prompt.lower()
        )
    if request.single_subject:
        prompt_parts.append(SINGLE_SUBJECT_PROMPT)
    if request.pose_prompt.strip():
        prompt_parts.append(request.pose_prompt.strip())
    if request.standard_proportions:
        prompt_parts.append(STANDARD_PROPORTIONS_PROMPT)
    prompt_parts.append(request.prompt)
    prompt = ", ".join(prompt_parts)
    negative_parts = [request.negative_prompt.strip()]
    if request.single_subject:
        negative_parts.append(SINGLE_SUBJECT_NEGATIVE)
    if request.standard_proportions:
        negative_parts.append(STANDARD_PROPORTIONS_NEGATIVE)
    negative_prompt = ", ".join(part for part in negative_parts if part)
    return prompt, negative_prompt


class ImageGenerator:
    """Owns the model lifecycle and serialises access to the GPU pipeline."""

    def __init__(
        self,
        settings: Settings,
        history_store: HistoryStore,
        reference_images: ReferenceImageStore | None = None,
    ) -> None:
        self._settings = settings
        self._history_store = history_store
        self._reference_images = reference_images
        # Diffusers attaches adapter methods dynamically and its type information
        # does not describe the runtime API. Keep that uncertainty at this boundary.
        self._pipelines: dict[str, Any] = {}
        self._img2img_pipelines: dict[str, Any] = {}
        self._lock = Lock()

    @property
    def is_ready(self) -> bool:
        return bool(self._pipelines)

    def generate(self, request: GenerateRequest, model: ModelSpec) -> list[GeneratedImage]:
        with self._lock:
            pipeline = (
                self._get_img2img_pipeline(model)
                if request.pose_reference_image_id is not None
                or (
                    request.reference_image_id is not None
                    and request.reference_mode in {"img2img", "img2img_ip_adapter"}
                )
                else self._get_pipeline(model)
            )
            pipeline.set_adapters(model.id, adapter_weights=request.lora_scale)
            prompt, negative_prompt = build_conditioning(request, model.trigger_words)
            initial_seed = (
                request.seed if request.seed is not None else int.from_bytes(os.urandom(4), "big")
            )
            generators = [
                torch.Generator(device=self._settings.device).manual_seed(initial_seed + index)
                for index in range(request.num_images)
            ]
            pipeline_arguments: dict[str, Any] = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": request.width,
                "height": request.height,
                "num_inference_steps": request.steps,
                "guidance_scale": request.guidance_scale,
                "generator": generators if request.num_images > 1 else generators[0],
                "num_images_per_prompt": request.num_images,
            }
            appearance_images: list[Image.Image] = []
            face_images: list[Image.Image] = []
            if request.reference_image_id is not None:
                if self._reference_images is None:
                    raise RuntimeError("参照画像ストアが設定されていません")
                reference_image = self._reference_images.prepare(
                    request.reference_image_id,
                    request.width,
                    request.height,
                    request.reference_focus_x,
                    request.reference_focus_y,
                    request.reference_zoom,
                )
                if request.reference_mode in {"img2img", "img2img_ip_adapter"}:
                    pipeline_arguments["image"] = reference_image
                    pipeline_arguments["strength"] = request.reference_strength
                if request.reference_mode in {"ip_adapter", "img2img_ip_adapter"}:
                    appearance_images.append(reference_image)
            if request.character_references:
                if self._reference_images is None:
                    raise RuntimeError("参照画像ストアが設定されていません")
                for reference in request.character_references:
                    image = self._reference_images.prepare(
                        reference.reference_image_id,
                        request.width,
                        request.height,
                        reference.focus_x,
                        reference.focus_y,
                        reference.zoom,
                    )
                    if reference.role == "face":
                        face_images.append(image)
                    else:
                        appearance_images.append(image)
            if request.pose_reference_image_id is not None:
                if self._reference_images is None:
                    raise RuntimeError("参照画像ストアが設定されていません")
                pipeline_arguments["image"] = self._reference_images.prepare(
                    request.pose_reference_image_id,
                    request.width,
                    request.height,
                    request.pose_reference_focus_x,
                    request.pose_reference_focus_y,
                    request.pose_reference_zoom,
                )
                pipeline_arguments["strength"] = request.pose_reference_strength
            stage_images = appearance_images or face_images
            stage_uses_face = bool(face_images and not appearance_images)
            uses_stage_adapter = bool(stage_images)
            if uses_stage_adapter:
                self._load_ip_adapter(
                    pipeline,
                    request.reference_ip_adapter_scale,
                    use_appearance=not stage_uses_face,
                    use_face=stage_uses_face,
                    face_scale=request.reference_face_ip_adapter_scale,
                )
                pipeline_arguments["ip_adapter_image"] = self._ip_adapter_images(stage_images)
            try:
                images = pipeline(**pipeline_arguments).images
            finally:
                if uses_stage_adapter:
                    self._unload_ip_adapter(pipeline)
            if appearance_images and face_images:
                images = self._refine_faces(
                    images,
                    face_images,
                    request,
                    model,
                    prompt,
                    negative_prompt,
                    initial_seed,
                )
            return [
                self._save_image(image, request, model, initial_seed + index)
                for index, image in enumerate(images)
            ]

    @staticmethod
    def _ip_adapter_images(images: list[Image.Image]) -> Image.Image | list[list[Image.Image]]:
        return images[0] if len(images) == 1 else [images]

    def _refine_faces(
        self,
        images: list[Any],
        face_images: list[Image.Image],
        request: GenerateRequest,
        model: ModelSpec,
        prompt: str,
        negative_prompt: str,
        initial_seed: int,
    ) -> list[Any]:
        pipeline = self._get_img2img_pipeline(model)
        pipeline.set_adapters(model.id, adapter_weights=request.lora_scale)
        self._load_ip_adapter(
            pipeline,
            request.reference_ip_adapter_scale,
            use_appearance=False,
            use_face=True,
            face_scale=request.reference_face_ip_adapter_scale,
        )
        refined = []
        try:
            for index, image in enumerate(images):
                generator = torch.Generator(device=self._settings.device).manual_seed(
                    initial_seed + index
                )
                refined.extend(
                    pipeline(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        image=image,
                        strength=request.reference_face_refinement_strength,
                        width=request.width,
                        height=request.height,
                        num_inference_steps=request.steps,
                        guidance_scale=request.guidance_scale,
                        generator=generator,
                        num_images_per_prompt=1,
                        ip_adapter_image=self._ip_adapter_images(face_images),
                    ).images
                )
        finally:
            self._unload_ip_adapter(pipeline)
        return refined

    def _get_pipeline(self, model: ModelSpec) -> Any:
        if model.id in self._pipelines:
            return self._pipelines[model.id]

        pipeline_factory: Any = StableDiffusionXLPipeline
        scheduler_factory: Any = EulerAncestralDiscreteScheduler
        pipeline = pipeline_factory.from_pretrained(
            model.base_model,
            revision=model.base_model_revision,
            torch_dtype=self._settings.torch_dtype,
            use_safetensors=True,
        )
        pipeline.scheduler = scheduler_factory.from_config(pipeline.scheduler.config)
        pipeline.load_lora_weights(
            model.lora_path.parent,
            weight_name=model.lora_path.name,
            adapter_name=model.id,
        )
        pipeline.set_adapters(model.id, adapter_weights=model.default_lora_scale)
        loaded_pipeline = pipeline.to(self._settings.device)
        if self._settings.device == "cuda":
            loaded_pipeline.enable_vae_slicing()
            loaded_pipeline.enable_attention_slicing()
        self._pipelines[model.id] = loaded_pipeline
        return loaded_pipeline

    def _get_img2img_pipeline(self, model: ModelSpec) -> Any:
        if model.id not in self._img2img_pipelines:
            pipeline_factory: Any = StableDiffusionXLImg2ImgPipeline
            self._img2img_pipelines[model.id] = pipeline_factory.from_pipe(
                self._get_pipeline(model)
            )
        return self._img2img_pipelines[model.id]

    def _load_ip_adapter(
        self,
        pipeline: Any,
        scale: float,
        *,
        use_appearance: bool = True,
        use_face: bool = False,
        face_scale: float = 0.25,
    ) -> None:
        try:
            if self._settings.device == "cuda" and str(pipeline.device).startswith("cuda"):
                pipeline.to("cpu")
                torch.cuda.empty_cache()
            image_encoder = self._load_ip_adapter_image_encoder()
            target_device = "cpu" if self._settings.device == "cuda" else pipeline.device
            pipeline.register_modules(
                image_encoder=image_encoder.to(
                    device=target_device,
                    dtype=self._settings.torch_dtype,
                )
            )
            pipeline.disable_attention_slicing()
            weight_names = []
            scales = []
            if use_appearance:
                weight_names.append(self._settings.ip_adapter_weight_name)
                scales.append(scale)
            if use_face:
                weight_names.append(self._settings.ip_adapter_face_weight_name)
                scales.append(face_scale)
            pipeline.load_ip_adapter(
                self._settings.ip_adapter_model,
                subfolder=self._settings.ip_adapter_subfolder,
                weight_name=weight_names[0] if len(weight_names) == 1 else weight_names,
                image_encoder_folder=None,
                revision=self._settings.ip_adapter_revision,
            )
            # ``from_pipe`` can leave newly loaded IP-Adapter projection layers in
            # float32 while the shared SDXL UNet is float16.  Keep those layers in
            # the configured inference dtype before Accelerate installs offload hooks.
            # Cast the complete composed pipeline together.  With ``from_pipe``,
            # casting only the newly attached UNet processors can leave prompt
            # embeddings/latents in float32 while the denoiser is float16.
            pipeline.to(dtype=self._settings.torch_dtype)
            if self._settings.device == "cuda":
                pipeline.enable_model_cpu_offload()
            pipeline.set_ip_adapter_scale(scales[0] if len(scales) == 1 else scales)
        except Exception as exc:
            rollback_failed = False
            try:
                self._unload_ip_adapter(pipeline)
            except RuntimeError:
                rollback_failed = True
                logger.exception("IP-Adapter rollback failed; cached pipelines were discarded")
            finally:
                # Img2img pipelines created with ``from_pipe`` share modules with
                # the text-to-image pipeline.  A failed adapter load can therefore
                # poison more than the object passed here.  Rebuild all pipelines
                # on the next request instead of guessing which modules changed.
                self._discard_pipeline_cache()
            rollback_note = (
                " ロールバックが完了しなかったため、パイプラインキャッシュを破棄しました。"
                if rollback_failed
                else " パイプライン状態を復元し、キャッシュを破棄しました。"
            )
            raise RuntimeError(
                "IP-Adapterを読み込めません。PCの空き容量・通信・モデル設定を確認してください。"
                + rollback_note
            ) from exc

    def _load_ip_adapter_image_encoder(self) -> Any:
        encoder_factory: Any = CLIPVisionModelWithProjection
        return encoder_factory.from_pretrained(
            self._settings.ip_adapter_model,
            subfolder=Path(self._settings.ip_adapter_image_encoder_subfolder).as_posix(),
            revision=self._settings.ip_adapter_revision,
            dtype=self._settings.torch_dtype,
            low_cpu_mem_usage=True,
        )

    def _unload_ip_adapter(self, pipeline: Any) -> None:
        """Release reference-only modules and restore the normal pipeline device."""
        errors: list[tuple[str, Exception]] = []

        def attempt(label: str, action: Callable[[], object]) -> None:
            try:
                action()
            except Exception as exc:  # third-party cleanup must continue after a failure
                errors.append((label, exc))

        attempt("remove hooks", pipeline.remove_all_hooks)
        attempt("unload adapter", pipeline.unload_ip_adapter)
        attempt("move pipeline to CPU", lambda: pipeline.to("cpu"))
        attempt(
            "unregister image encoder",
            lambda: pipeline.register_modules(image_encoder=None, feature_extractor=None),
        )
        attempt("collect garbage", gc.collect)
        if self._settings.device == "cuda":
            attempt("clear CUDA cache", torch.cuda.empty_cache)
            attempt("restore pipeline to CUDA", lambda: pipeline.to("cuda"))
            attempt("restore attention slicing", pipeline.enable_attention_slicing)
        if errors:
            self._discard_pipeline_cache()
            labels = ", ".join(label for label, _ in errors)
            raise RuntimeError(f"IP-Adapterの後始末に失敗しました: {labels}") from errors[0][1]

    def _discard_pipeline_cache(self) -> None:
        """Drop pipelines that may share partially mutated Diffusers modules."""
        self._img2img_pipelines.clear()
        self._pipelines.clear()

    def _save_image(
        self, image: Any, request: GenerateRequest, model: ModelSpec, seed: int
    ) -> GeneratedImage:
        filename = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.png"
        image.save(self._history_store.image_path(filename))
        result = GeneratedImage(filename=filename, image_url=f"/images/{filename}", seed=seed)
        self._history_store.save(result, request, model)
        return result
