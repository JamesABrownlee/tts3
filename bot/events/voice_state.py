"""Voice state handler registration."""

from __future__ import annotations

import discord

from bot.services import SpeechOrchestrator


async def handle_voice_state_update(
    orchestrator: SpeechOrchestrator,
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    if member.guild is None:
        return
    await orchestrator.handle_voice_transition(member, before, after)
