"""Shared service bootstrap for Discord and API runtimes."""

from __future__ import annotations

import aiohttp

from app.config import Settings
from app.media import TempAudioStore
from app.obs import OBSBroker
from app.services import ServiceContainer
from audio.player import AudioPlayer
from audio.queue import GuildQueueManager
from audio.voice_connection import VoiceConnectionManager
from domain.state import RuntimeStateStore
from storage.db import Database
from storage.repositories import GuildRuntimeRepository, GuildSettingsRepository, UserRepository
from tts.provider import HttpTTSProvider
from tts.voices import DEFAULT_VOICES, VoiceCatalog


async def create_services(settings: Settings) -> ServiceContainer:
    db = Database(settings.sqlite_path)
    await db.connect()
    await db.apply_migrations()
    http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=settings.tts_http_timeout))
    return ServiceContainer(
        settings=settings,
        db=db,
        http_session=http_session,
        user_repository=UserRepository(db),
        guild_settings_repository=GuildSettingsRepository(db, settings.fallback_voice_id),
        guild_runtime_repository=GuildRuntimeRepository(db),
        runtime_states=RuntimeStateStore(),
        queue_manager=GuildQueueManager(),
        voice_connections=VoiceConnectionManager(),
        audio_player=AudioPlayer(settings),
        tts_provider=HttpTTSProvider(settings, http_session),
        voice_catalog=VoiceCatalog(DEFAULT_VOICES, settings.fallback_voice_id),
        api_audio_store=TempAudioStore(settings.api_audio_dir, ttl_seconds=settings.api_audio_ttl_seconds),
        obs_broker=OBSBroker(),
    )


async def close_services(services: ServiceContainer) -> None:
    await services.http_session.close()
    await services.db.close()
