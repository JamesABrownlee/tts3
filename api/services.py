"""Shared API helpers for synthesis and announcements."""

from __future__ import annotations

from time import time

from app.media import StoredAudio
from app.services import ServiceContainer


async def synthesize_to_store(services: ServiceContainer, *, text: str, voice_id: str, max_seconds: int) -> StoredAudio:
    if not services.voice_catalog.is_valid(voice_id):
        raise ValueError("Unknown voice_id")
    generated = await services.tts_provider.synthesize(text, voice_id, max_seconds=max_seconds)
    return await services.api_audio_store.store_generated(generated)


async def broadcast_obs_audio(
    services: ServiceContainer,
    *,
    stored: StoredAudio,
    text: str,
    voice_id: str,
) -> int:
    payload = {
        "type": "announcement",
        "text": text,
        "voice_id": voice_id,
        "audio_url": f"/audio/{stored.file_id}",
        "timestamp": time(),
    }
    return await services.obs_broker.broadcast(payload)
