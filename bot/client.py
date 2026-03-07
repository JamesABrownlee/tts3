"""Discord bot construction and lifecycle."""

from __future__ import annotations

import logging

import aiohttp
import discord
from discord.ext import commands

from app.config import Settings
from audio.player import AudioPlayer
from audio.queue import GuildQueueManager
from audio.voice_connection import VoiceConnectionManager
from bot.commands.service import ServiceCommands
from bot.commands.voice import VoiceCommands
from bot.events.messages import handle_message
from bot.events.voice_state import handle_voice_state_update
from bot.service_container import ServiceContainer
from bot.services import SpeechOrchestrator
from domain.state import RuntimeStateStore
from storage.db import Database
from storage.repositories import GuildRuntimeRepository, GuildSettingsRepository, UserRepository
from tts.provider import HttpTTSProvider
from tts.voices import DEFAULT_VOICES, VoiceCatalog


logger = logging.getLogger(__name__)


class TTSBot(commands.Bot):
    def __init__(self, services: ServiceContainer, orchestrator: SpeechOrchestrator) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)
        self.services = services
        self.orchestrator = orchestrator

    async def setup_hook(self) -> None:
        self.tree.add_command(VoiceCommands(self.services))
        self.tree.add_command(ServiceCommands(self.services, self.orchestrator.end_session))
        await self.tree.sync()

    async def on_ready(self) -> None:
        logger.info("bot_ready", extra={"extra": {"user": str(self.user)}})

    async def on_message(self, message: discord.Message) -> None:
        await handle_message(self.orchestrator, message)

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        await handle_voice_state_update(self.orchestrator, member, before, after)

    async def close(self) -> None:
        await self.services.http_session.close()
        await self.services.db.close()
        await super().close()


async def create_bot(settings: Settings) -> TTSBot:
    db = Database(settings.sqlite_path)
    await db.connect()
    await db.apply_migrations()
    http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=settings.tts_http_timeout))
    services = ServiceContainer(
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
    )
    orchestrator = SpeechOrchestrator(services)
    return TTSBot(services, orchestrator)
