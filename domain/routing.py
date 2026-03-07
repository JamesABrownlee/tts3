"""Routing helpers for guild sessions."""

from __future__ import annotations

from domain.types import GuildRuntimeState, GuildSettings


def is_text_channel_eligible(settings: GuildSettings, text_channel_id: int) -> bool:
    if not settings.allowed_text_channel_ids:
        return True
    return text_channel_id in settings.allowed_text_channel_ids


def can_narrate_message(
    settings: GuildSettings,
    runtime_state: GuildRuntimeState,
    *,
    author_voice_channel_id: int | None,
    text_channel_id: int,
) -> bool:
    if not settings.narration_enabled:
        return False
    if not is_text_channel_eligible(settings, text_channel_id):
        return False
    if author_voice_channel_id is None:
        return False
    if runtime_state.active_voice_channel_id is None:
        return True
    if settings.same_vc_only and author_voice_channel_id != runtime_state.active_voice_channel_id:
        return False
    if runtime_state.active_text_channel_id is not None and text_channel_id != runtime_state.active_text_channel_id:
        return False
    return author_voice_channel_id == runtime_state.active_voice_channel_id
