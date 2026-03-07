"""External announcer endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from api.dependencies import get_services, require_api_key
from api.models import AnnouncementRequest, AnnouncementResponse, ChatAnnouncementRequest
from api.services import broadcast_obs_audio, synthesize_to_store
from app.services import ServiceContainer


router = APIRouter()


@router.post("/api/announce", response_model=AnnouncementResponse, dependencies=[Depends(require_api_key)])
async def announce(
    request: Request,
    payload: AnnouncementRequest,
    services: ServiceContainer = Depends(get_services),
) -> AnnouncementResponse:
    if payload.target != "obs":
        raise HTTPException(status_code=400, detail="Unsupported target")
    try:
        stored = await synthesize_to_store(services, text=payload.text, voice_id=payload.voice_id, max_seconds=20)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    delivered = await broadcast_obs_audio(services, stored=stored, text=payload.text, voice_id=payload.voice_id)
    return AnnouncementResponse(
        queued=True,
        target=payload.target,
        file_id=stored.file_id,
        audio_url=str(request.url_for("get_audio", file_id=stored.file_id)),
        voice_id=payload.voice_id,
        text=payload.text,
        delivered_clients=delivered,
    )


@router.post("/api/announce/chat", response_model=AnnouncementResponse, dependencies=[Depends(require_api_key)])
async def announce_chat(
    request: Request,
    payload: ChatAnnouncementRequest,
    services: ServiceContainer = Depends(get_services),
) -> AnnouncementResponse:
    if payload.target != "obs":
        raise HTTPException(status_code=400, detail="Unsupported target")
    formatted_text = f"{payload.user} said {payload.message}"
    try:
        stored = await synthesize_to_store(services, text=formatted_text, voice_id=payload.voice_id, max_seconds=20)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    delivered = await broadcast_obs_audio(services, stored=stored, text=formatted_text, voice_id=payload.voice_id)
    return AnnouncementResponse(
        queued=True,
        target=payload.target,
        file_id=stored.file_id,
        audio_url=str(request.url_for("get_audio", file_id=stored.file_id)),
        voice_id=payload.voice_id,
        text=formatted_text,
        delivered_clients=delivered,
    )
