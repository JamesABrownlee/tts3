"""Shared guild settings update logic with runtime side effects."""

from __future__ import annotations

import logging

from app.services import ServiceContainer
from domain.services import reset_session


logger = logging.getLogger(__name__)


async def update_guild_settings(services: ServiceContainer, guild_id: int, **changes: object):
    settings = await services.guild_settings_repository.update(guild_id, **changes)
    await _apply_runtime_settings(services, settings)
    return settings


async def _apply_runtime_settings(services: ServiceContainer, settings) -> None:
    state = services.runtime_states.get(settings.guild_id)
    state.last_speaker_discord_id = None
    state.heard_speakers.clear()
    await services.guild_runtime_repository.save(state)

    if settings.narration_enabled or state.active_voice_channel_id is None:
        return

    logger.info(
        "session_ended_due_to_settings_change",
        extra={"extra": {"guild_id": settings.guild_id, "reason": "narration_disabled"}},
    )
    await services.voice_connections.disconnect(settings.guild_id)
    reset_session(state)
    await services.guild_runtime_repository.save(state)
