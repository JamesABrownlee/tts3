"""Service wiring for the Discord bot."""

from __future__ import annotations

from dataclasses import dataclass

import aiohttp

from app.config import Settings
from audio.player import AudioPlayer
from audio.queue import GuildQueueManager
from audio.voice_connection import VoiceConnectionManager
from domain.state import RuntimeStateStore
from storage.db import Database
from storage.repositories import GuildRuntimeRepository, GuildSettingsRepository, UserRepository
from tts.provider import HttpTTSProvider
from tts.voices import DEFAULT_VOICES, VoiceCatalog


@dataclass(slots=True)
class ServiceContainer:
    settings: Settings
    db: Database
    http_session: aiohttp.ClientSession
    user_repository: UserRepository
    guild_settings_repository: GuildSettingsRepository
    guild_runtime_repository: GuildRuntimeRepository
    runtime_states: RuntimeStateStore
    queue_manager: GuildQueueManager
    voice_connections: VoiceConnectionManager
    audio_player: AudioPlayer
    tts_provider: HttpTTSProvider
    voice_catalog: VoiceCatalog
