"""Discord bot construction and lifecycle."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from app.bootstrap import create_services
from app.config import Settings
from bot.commands.service import ServiceCommands
from bot.commands.voice import VoiceCommands
from bot.events.messages import handle_message
from bot.events.voice_state import handle_voice_state_update
from app.services import ServiceContainer
from bot.services import SpeechOrchestrator


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

async def create_bot(services: ServiceContainer) -> TTSBot:
    orchestrator = SpeechOrchestrator(services)
    return TTSBot(services, orchestrator)


async def create_bot_from_settings(settings: Settings) -> TTSBot:
    services = await create_services(settings)
    return await create_bot(services)
