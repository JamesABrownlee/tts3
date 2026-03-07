"""Domain service helpers for session state and intro behavior."""

from __future__ import annotations

from time import time

from domain.types import GuildRuntimeState, GuildSettings


def should_announce_speaker(settings: GuildSettings, state: GuildRuntimeState, speaker_id: int) -> bool:
    if settings.intro_mode == "always":
        return True
    if settings.intro_mode == "on_change":
        return state.last_speaker_discord_id != speaker_id
    if settings.intro_mode == "first_only":
        return speaker_id not in state.heard_speakers
    return True


def mark_speaker(state: GuildRuntimeState, speaker_id: int) -> None:
    state.last_speaker_discord_id = speaker_id
    state.heard_speakers.add(speaker_id)


def start_session(state: GuildRuntimeState, *, voice_channel_id: int, text_channel_id: int) -> GuildRuntimeState:
    state.active_voice_channel_id = voice_channel_id
    state.active_text_channel_id = text_channel_id
    state.last_speaker_discord_id = None
    state.session_started_at = time()
    state.currently_connected = True
    state.heard_speakers.clear()
    return state


def reset_session(state: GuildRuntimeState) -> GuildRuntimeState:
    state.active_voice_channel_id = None
    state.active_text_channel_id = None
    state.last_speaker_discord_id = None
    state.session_started_at = None
    state.currently_connected = False
    state.heard_speakers.clear()
    return state
