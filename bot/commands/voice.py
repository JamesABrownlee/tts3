"""User voice slash commands."""

from __future__ import annotations

import discord
from discord import app_commands

from bot.service_container import ServiceContainer


class VoiceCommands(app_commands.Group):
    def __init__(self, services: ServiceContainer) -> None:
        super().__init__(name="voice", description="Manage your TTS voice")
        self.services = services

    async def _voice_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        narrator_voice_id: str | None = None
        if interaction.guild is not None:
            settings = await self.services.guild_settings_repository.get(interaction.guild.id)
            narrator_voice_id = settings.narrator_voice_id
        voices = self.services.voice_catalog.list_user_selectable(narrator_voice_id)
        current_lower = current.lower().strip()
        matches = [
            voice
            for voice in voices
            if not current_lower
            or current_lower in voice.voice_id.lower()
            or current_lower in voice.display_name.lower()
        ]
        return [
            app_commands.Choice(name=f"{voice.display_name} ({voice.voice_id})", value=voice.voice_id)
            for voice in matches[:25]
        ]

    @app_commands.command(name="list", description="List available user-selectable voices")
    async def list_voices(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Guild only.", ephemeral=True)
            return
        settings = await self.services.guild_settings_repository.get(interaction.guild.id)
        voices = self.services.voice_catalog.list_user_selectable(settings.narrator_voice_id)
        lines = [f"`{voice.voice_id}` - {voice.display_name}" for voice in voices]
        await interaction.response.send_message("\n".join(lines) or "No selectable voices available.", ephemeral=True)

    @app_commands.command(name="set", description="Set your preferred voice")
    @app_commands.autocomplete(voice_id=_voice_autocomplete)
    async def set_voice(self, interaction: discord.Interaction, voice_id: str) -> None:
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message("Guild only.", ephemeral=True)
            return
        settings = await self.services.guild_settings_repository.get(interaction.guild.id)
        allowed = {voice.voice_id for voice in self.services.voice_catalog.list_user_selectable(settings.narrator_voice_id)}
        if voice_id not in allowed:
            await interaction.response.send_message("Invalid voice for user selection.", ephemeral=True)
            return
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        await self.services.user_repository.upsert(
            interaction.user.id,
            display_name=member.display_name if member else interaction.user.display_name,
            nickname=member.nick if member else None,
            voice_id=voice_id,
        )
        await interaction.response.send_message(f"Voice set to `{voice_id}`.", ephemeral=True)

    @app_commands.command(name="clear", description="Clear your preferred voice")
    async def clear_voice(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message("Guild only.", ephemeral=True)
            return
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        await self.services.user_repository.upsert(
            interaction.user.id,
            display_name=member.display_name if member else interaction.user.display_name,
            nickname=member.nick if member else None,
            voice_id=None,
        )
        await interaction.response.send_message("Voice preference cleared.", ephemeral=True)

    @app_commands.command(name="current", description="Show your current voice selection")
    async def current_voice(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Guild only.", ephemeral=True)
            return
        settings = await self.services.guild_settings_repository.get(interaction.guild.id)
        user = await self.services.user_repository.get(interaction.user.id)
        narrator_voice_id = self.services.voice_catalog.resolve_narrator_voice(settings.narrator_voice_id)
        resolved = self.services.voice_catalog.resolve_user_voice(
            user.voice_id if user else settings.fallback_user_voice_id,
            narrator_voice_id,
        )
        current = user.voice_id if user and user.voice_id else "not set"
        await interaction.response.send_message(
            f"Selected: `{current}`\nResolved: `{resolved}`\nFallback: `{settings.fallback_user_voice_id}`",
            ephemeral=True,
        )

    @app_commands.command(name="preview", description="Preview a voice identifier")
    @app_commands.autocomplete(voice_id=_voice_autocomplete)
    async def preview_voice(self, interaction: discord.Interaction, voice_id: str) -> None:
        if not self.services.voice_catalog.is_valid(voice_id):
            await interaction.response.send_message("Unknown voice id.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Preview is not streamed through slash commands. Voice `{voice_id}` is valid and ready for narration.",
            ephemeral=True,
        )
