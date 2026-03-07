"""Audio synthesis routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from api.dependencies import get_services, require_api_key
from api.models import SynthesizeRequest, SynthesizeResponse
from api.services import synthesize_to_store
from app.services import ServiceContainer


router = APIRouter()


@router.post("/api/synthesize", response_model=SynthesizeResponse, dependencies=[Depends(require_api_key)])
async def synthesize_audio(
    request: Request,
    payload: SynthesizeRequest,
    services: ServiceContainer = Depends(get_services),
):
    try:
        stored = await synthesize_to_store(services, text=payload.text, voice_id=payload.voice_id, max_seconds=payload.max_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.download:
        return FileResponse(stored.path, media_type=stored.content_type, filename=stored.path.name)
    return SynthesizeResponse(
        file_id=stored.file_id,
        voice_id=stored.voice_id,
        text=stored.text,
        audio_url=str(request.url_for("get_audio", file_id=stored.file_id)),
        content_type=stored.content_type,
    )


@router.get("/audio/{file_id}", name="get_audio")
async def get_audio(file_id: str, services: ServiceContainer = Depends(get_services)):
    stored = services.api_audio_store.get(file_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(stored.path, media_type=stored.content_type, filename=stored.path.name)
