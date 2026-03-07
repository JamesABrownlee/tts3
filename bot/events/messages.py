"""Message event handler registration."""

from __future__ import annotations

import discord

from bot.services import SpeechOrchestrator


async def handle_message(orchestrator: SpeechOrchestrator, message: discord.Message) -> None:
    await orchestrator.handle_message(message)
