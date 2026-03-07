from __future__ import annotations

from pathlib import Path
import sys
from uuid import uuid4

import aiohttp
import pytest
import pytest_asyncio

from app.config import Settings
from app.media import TempAudioStore
from app.obs import OBSBroker
from app.services import ServiceContainer
from audio.player import AudioPlayer
from audio.queue import GuildQueueManager
from audio.voice_connection import VoiceConnectionManager
from bot.services import SpeechOrchestrator
from domain.state import RuntimeStateStore
from storage.db import Database
from storage.repositories import GuildRuntimeRepository, GuildSettingsRepository, UserRepository
from tts.provider import HttpTTSProvider
from tts.voices import DEFAULT_VOICES, VoiceCatalog


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def settings() -> Settings:
    temp_root = Path.cwd() / ".test_tmp" / uuid4().hex
    temp_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        discord_token="token",
        sqlite_path=temp_root / "bot.sqlite3",
        tts_provider="http",
        log_level="INFO",
        temp_audio_dir=temp_root / "temp_audio",
        api_audio_dir=temp_root / "temp_audio" / "api",
        ffmpeg_path="ffmpeg",
        api_key="test-api-key",
        api_host="127.0.0.1",
        api_port=8000,
        api_audio_ttl_seconds=3600,
        tts_http_timeout=20,
        tiktok_tts_url="https://tiktok-tts.weilnet.workers.dev/api/generation",
        google_tts_url="https://translate.google.com/translate_tts",
        user_agent="Mozilla/5.0",
        fallback_voice_id="en_us_001",
        max_audio_seconds=20,
        voice_failure_threshold=3,
        voice_cooldown_duration=300,
    )


@pytest_asyncio.fixture()
async def services(settings: Settings) -> ServiceContainer:
    db = Database(settings.sqlite_path)
    await db.connect()
    await db.apply_migrations()
    session = aiohttp.ClientSession()
    container = ServiceContainer(
        settings=settings,
        db=db,
        http_session=session,
        user_repository=UserRepository(db),
        guild_settings_repository=GuildSettingsRepository(db, settings.fallback_voice_id),
        guild_runtime_repository=GuildRuntimeRepository(db),
        runtime_states=RuntimeStateStore(),
        queue_manager=GuildQueueManager(),
        voice_connections=VoiceConnectionManager(),
        audio_player=AudioPlayer(settings),
        tts_provider=HttpTTSProvider(settings, session),
        voice_catalog=VoiceCatalog(DEFAULT_VOICES, settings.fallback_voice_id),
        api_audio_store=TempAudioStore(settings.api_audio_dir, ttl_seconds=settings.api_audio_ttl_seconds),
        obs_broker=OBSBroker(),
    )
    yield container
    await session.close()
    await db.close()


@pytest.fixture()
def orchestrator(services: ServiceContainer) -> SpeechOrchestrator:
    return SpeechOrchestrator(services)
