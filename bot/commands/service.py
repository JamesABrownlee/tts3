"""Guild service slash commands."""

from __future__ import annotations

from dataclasses import replace

import discord
from discord import app_commands

from bot.service_container import ServiceContainer


def _admin_only() -> app_commands.Check:
    return app_commands.checks.has_permissions(administrator=True)


class ServiceCommands(app_commands.Group):
    def __init__(self, services: ServiceContainer, end_session_callback) -> None:
        super().__init__(name="service", description="Manage guild TTS service")
        self.services = services
        self.end_session_callback = end_session_callback
        self.channels = ServiceChannels(services)
        self.narrator = ServiceNarrator(services)
        self.fallback_user_voice = FallbackUserVoice(services)
        self.intro_mode = IntroModeCommands(services)
        self.same_vc_only = SameVCOnlyCommands(services)
        self.idle_disconnect = IdleDisconnectCommands(services)
        self.session = SessionCommands(end_session_callback)
        self.add_command(self.channels)
        self.add_command(self.narrator)
        self.add_command(self.fallback_user_voice)
        self.add_command(self.intro_mode)
        self.add_command(self.same_vc_only)
        self.add_command(self.idle_disconnect)
        self.add_command(self.session)

    @app_commands.command(name="show", description="Show guild TTS service status")
    async def show(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Guild only.", ephemeral=True)
            return
        settings = await self.services.guild_settings_repository.get(interaction.guild.id)
        runtime = self.services.runtime_states.get(interaction.guild.id)
        channels = "all text channels" if not settings.allowed_text_channel_ids else ", ".join(f"<#{channel_id}>" for channel_id in settings.allowed_text_channel_ids)
        active_vc = f"<#{runtime.active_voice_channel_id}>" if runtime.active_voice_channel_id else "idle"
        active_tc = f"<#{runtime.active_text_channel_id}>" if runtime.active_text_channel_id else "idle"
        narrator = self.services.voice_catalog.resolve_narrator_voice(settings.narrator_voice_id)
        fallback = self.services.voice_catalog.resolve_user_voice(settings.fallback_user_voice_id, narrator)
        body = (
            f"Narration enabled: `{settings.narration_enabled}`\n"
            f"Eligible text channels: {channels}\n"
            f"Narrator voice: `{narrator}`\n"
            f"Fallback user voice: `{fallback}`\n"
            f"Same VC only: `{settings.same_vc_only}`\n"
            f"Intro mode: `{settings.intro_mode}`\n"
            f"Max combined audio seconds: `{settings.max_combined_audio_seconds}`\n"
            f"Idle disconnect seconds: `{settings.idle_disconnect_seconds}`\n"
            f"Current session state: `{'ACTIVE' if runtime.active_voice_channel_id else 'IDLE'}`\n"
            f"Active VC: {active_vc}\n"
            f"Active text channel: {active_tc}"
        )
        await interaction.response.send_message(body, ephemeral=True)

    @_admin_only()
    @app_commands.command(name="enable", description="Enable narration")
    async def enable(self, interaction: discord.Interaction) -> None:
        settings = await self.services.guild_settings_repository.get(interaction.guild_id)
        await self.services.guild_settings_repository.save(replace(settings, narration_enabled=True))
        await interaction.response.send_message("Narration enabled.", ephemeral=True)

    @_admin_only()
    @app_commands.command(name="disable", description="Disable narration")
    async def disable(self, interaction: discord.Interaction) -> None:
        settings = await self.services.guild_settings_repository.get(interaction.guild_id)
        await self.services.guild_settings_repository.save(replace(settings, narration_enabled=False))
        await interaction.response.send_message("Narration disabled.", ephemeral=True)


class ServiceChannels(app_commands.Group):
    def __init__(self, services: ServiceContainer) -> None:
        super().__init__(name="channels", description="Manage eligible text channels")
        self.services = services

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="add", description="Add an eligible text channel")
    async def add(self, interaction: discord.Interaction, text_channel: discord.TextChannel) -> None:
        settings = await self.services.guild_settings_repository.get(interaction.guild_id)
        ids = sorted(set([*settings.allowed_text_channel_ids, text_channel.id]))
        await self.services.guild_settings_repository.save(replace(settings, allowed_text_channel_ids=ids))
        await interaction.response.send_message(f"Added {text_channel.mention}.", ephemeral=True)

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="remove", description="Remove an eligible text channel")
    async def remove(self, interaction: discord.Interaction, text_channel: discord.TextChannel) -> None:
        settings = await self.services.guild_settings_repository.get(interaction.guild_id)
        ids = [channel_id for channel_id in settings.allowed_text_channel_ids if channel_id != text_channel.id]
        await self.services.guild_settings_repository.save(replace(settings, allowed_text_channel_ids=ids))
        await interaction.response.send_message(f"Removed {text_channel.mention}.", ephemeral=True)

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="clear", description="Allow all text channels")
    async def clear(self, interaction: discord.Interaction) -> None:
        settings = await self.services.guild_settings_repository.get(interaction.guild_id)
        await self.services.guild_settings_repository.save(replace(settings, allowed_text_channel_ids=[]))
        await interaction.response.send_message("Eligible text channels cleared. All channels are now allowed.", ephemeral=True)


class ServiceNarrator(app_commands.Group):
    def __init__(self, services: ServiceContainer) -> None:
        super().__init__(name="narrator", description="Manage narrator voice")
        self.services = services

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="set", description="Set narrator voice")
    async def set(self, interaction: discord.Interaction, voice_id: str) -> None:
        if not self.services.voice_catalog.is_valid(voice_id):
            await interaction.response.send_message("Unknown voice.", ephemeral=True)
            return
        settings = await self.services.guild_settings_repository.get(interaction.guild_id)
        await self.services.guild_settings_repository.save(replace(settings, narrator_voice_id=voice_id))
        await interaction.response.send_message(f"Narrator voice set to `{voice_id}`.", ephemeral=True)

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="show", description="Show narrator voice")
    async def show(self, interaction: discord.Interaction) -> None:
        settings = await self.services.guild_settings_repository.get(interaction.guild_id)
        narrator = self.services.voice_catalog.resolve_narrator_voice(settings.narrator_voice_id)
        await interaction.response.send_message(f"Narrator voice: `{narrator}`.", ephemeral=True)


class FallbackUserVoice(app_commands.Group):
    def __init__(self, services: ServiceContainer) -> None:
        super().__init__(name="fallback-user-voice", description="Manage fallback user voice")
        self.services = services

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="set", description="Set fallback user voice")
    async def set(self, interaction: discord.Interaction, voice_id: str) -> None:
        settings = await self.services.guild_settings_repository.get(interaction.guild_id)
        narrator = self.services.voice_catalog.resolve_narrator_voice(settings.narrator_voice_id)
        allowed = {voice.voice_id for voice in self.services.voice_catalog.list_user_selectable(settings.narrator_voice_id)}
        if voice_id not in allowed and not (len(allowed) == 0 and self.services.voice_catalog.is_valid(voice_id)):
            await interaction.response.send_message("Voice cannot be used as fallback user voice.", ephemeral=True)
            return
        resolved = self.services.voice_catalog.resolve_user_voice(voice_id, narrator)
        await self.services.guild_settings_repository.save(replace(settings, fallback_user_voice_id=resolved))
        await interaction.response.send_message(f"Fallback user voice set to `{resolved}`.", ephemeral=True)


class IntroModeCommands(app_commands.Group):
    def __init__(self, services: ServiceContainer) -> None:
        super().__init__(name="intro-mode", description="Manage intro behavior")
        self.services = services

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="set", description="Set intro mode")
    async def set(self, interaction: discord.Interaction, mode: str) -> None:
        if mode not in {"always", "on_change", "first_only"}:
            await interaction.response.send_message("Invalid intro mode.", ephemeral=True)
            return
        settings = await self.services.guild_settings_repository.get(interaction.guild_id)
        await self.services.guild_settings_repository.save(replace(settings, intro_mode=mode))
        await interaction.response.send_message(f"Intro mode set to `{mode}`.", ephemeral=True)


class SameVCOnlyCommands(app_commands.Group):
    def __init__(self, services: ServiceContainer) -> None:
        super().__init__(name="same-vc-only", description="Manage same VC routing")
        self.services = services

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="set", description="Enable or disable same VC restriction")
    async def set(self, interaction: discord.Interaction, value: bool) -> None:
        settings = await self.services.guild_settings_repository.get(interaction.guild_id)
        await self.services.guild_settings_repository.save(replace(settings, same_vc_only=value))
        await interaction.response.send_message(f"Same VC only set to `{value}`.", ephemeral=True)


class IdleDisconnectCommands(app_commands.Group):
    def __init__(self, services: ServiceContainer) -> None:
        super().__init__(name="idle-disconnect", description="Manage idle disconnect grace period")
        self.services = services

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="set", description="Set idle disconnect seconds")
    async def set(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 300]) -> None:
        settings = await self.services.guild_settings_repository.get(interaction.guild_id)
        await self.services.guild_settings_repository.save(replace(settings, idle_disconnect_seconds=int(seconds)))
        await interaction.response.send_message(f"Idle disconnect set to `{seconds}` seconds.", ephemeral=True)


class SessionCommands(app_commands.Group):
    def __init__(self, end_session_callback) -> None:
        super().__init__(name="session", description="Manage the current active session")
        self.end_session_callback = end_session_callback

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="end", description="Force end the current session")
    async def end(self, interaction: discord.Interaction) -> None:
        await self.end_session_callback(interaction.guild_id)
        await interaction.response.send_message("Session ended.", ephemeral=True)
