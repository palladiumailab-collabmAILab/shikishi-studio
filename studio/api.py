from __future__ import annotations

from pathlib import Path
from typing import cast

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from studio.schemas import (
    CharacterProfileSummary,
    EvaluationRecord,
    EvaluationRequest,
    GenerateRequest,
    HistoryItem,
    JobResponse,
    ModelSummary,
    ReferenceImageRecord,
    StatusResponse,
)
from studio.services.history import HistoryStore
from studio.services.jobs import GenerationQueue
from studio.services.profiles import CharacterProfileStore
from studio.services.references import ReferenceImageStore
from studio.services.registry import ModelRegistry

router = APIRouter()


def job_queue(request: Request) -> GenerationQueue:
    return cast(GenerationQueue, request.app.state.job_queue)


def history_store(request: Request) -> HistoryStore:
    return cast(HistoryStore, request.app.state.history_store)


def model_registry(request: Request) -> ModelRegistry:
    return cast(ModelRegistry, request.app.state.model_registry)


def character_profiles(request: Request) -> CharacterProfileStore:
    return cast(CharacterProfileStore, request.app.state.character_profiles)


def reference_images(request: Request) -> ReferenceImageStore:
    return cast(ReferenceImageStore, request.app.state.reference_images)


@router.get("/api/status", response_model=StatusResponse)
def status(request: Request) -> StatusResponse:
    settings = request.app.state.settings
    return StatusResponse(
        ready=job_queue(request).is_ready,
        device=settings.device,
        queue_depth=job_queue(request).depth,
        active_job_id=job_queue(request).active_job_id,
        app_version=settings.app_version,
    )


@router.get("/api/models", response_model=list[ModelSummary])
def models(request: Request) -> list[ModelSummary]:
    return model_registry(request).list_summaries()


@router.get("/api/character-profiles", response_model=list[CharacterProfileSummary])
def profiles(request: Request) -> list[CharacterProfileSummary]:
    return character_profiles(request).list_profiles()


@router.post("/api/reference-images", response_model=ReferenceImageRecord, status_code=201)
async def upload_reference_image(request: Request) -> ReferenceImageRecord:
    maximum = request.app.state.settings.max_reference_image_bytes
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > maximum:
            raise HTTPException(status_code=413, detail="参照画像は10MB以下にしてください")
    try:
        return reference_images(request).save(bytes(data), request.headers.get("content-type", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/reference-images/{reference_id}")
def reference_image(reference_id: str, request: Request) -> FileResponse:
    try:
        reference_images(request).get(reference_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        reference_images(request).normalized_path(reference_id), media_type="image/png"
    )


@router.post(
    "/api/reference-images/from-history/{filename}",
    response_model=ReferenceImageRecord,
    status_code=201,
)
def reference_image_from_history(filename: str, request: Request) -> ReferenceImageRecord:
    if filename != Path(filename).name or not filename.lower().endswith(".png"):
        raise HTTPException(status_code=404, detail="生成画像が見つかりません")
    source = history_store(request).image_path(filename)
    if not source.is_file():
        raise HTTPException(status_code=404, detail="生成画像が見つかりません")
    try:
        return reference_images(request).save(source.read_bytes(), "image/png")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/history", response_model=list[HistoryItem])
def history(request: Request) -> list[HistoryItem]:
    return history_store(request).list_items()


@router.post(
    "/api/history/{filename}/evaluation",
    response_model=EvaluationRecord,
    status_code=201,
)
def save_evaluation(
    filename: str, payload: EvaluationRequest, request: Request
) -> EvaluationRecord:
    try:
        return history_store(request).save_evaluation(filename, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/jobs", response_model=JobResponse, status_code=202)
def create_job(payload: GenerateRequest, request: Request) -> JobResponse:
    try:
        if payload.character_profile_id is not None:
            character_profiles(request).get(payload.character_profile_id)
        if payload.reference_image_id is not None:
            reference_images(request).get(payload.reference_image_id)
        for reference in payload.character_references:
            reference_images(request).get(reference.reference_image_id)
        if payload.pose_reference_image_id is not None:
            reference_images(request).get(payload.pose_reference_image_id)
        return job_queue(request).submit(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, request: Request) -> JobResponse:
    job = job_queue(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/api/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: str, request: Request) -> JobResponse:
    try:
        job = job_queue(request).cancel(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/download/{filename}")
def download(filename: str, request: Request) -> FileResponse:
    if filename != Path(filename).name or not filename.lower().endswith(".png"):
        raise HTTPException(status_code=404, detail="Image not found")
    path = history_store(request).image_path(filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/png", filename=path.name)


@router.get("/images/{filename}")
def generated_image(filename: str, request: Request) -> FileResponse:
    if filename != Path(filename).name or not filename.lower().endswith(".png"):
        raise HTTPException(status_code=404, detail="Image not found")
    path = history_store(request).image_path(filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/png")
