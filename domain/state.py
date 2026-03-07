"""In-memory runtime state management."""

from __future__ import annotations

import asyncio

from domain.types import GuildRuntimeState


class RuntimeStateStore:
    """Tracks mutable runtime state for each guild."""

    def __init__(self) -> None:
        self._states: dict[int, GuildRuntimeState] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def get(self, guild_id: int) -> GuildRuntimeState:
        state = self._states.get(guild_id)
        if state is None:
            state = GuildRuntimeState(guild_id=guild_id)
            self._states[guild_id] = state
        return state

    def get_lock(self, guild_id: int) -> asyncio.Lock:
        lock = self._locks.get(guild_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[guild_id] = lock
        return lock

    def clear_session(self, guild_id: int) -> GuildRuntimeState:
        state = self.get(guild_id)
        state.active_voice_channel_id = None
        state.active_text_channel_id = None
        state.last_speaker_discord_id = None
        state.last_narrator_voice_id = None
        state.session_started_at = None
        state.currently_connected = False
        state.heard_speakers.clear()
        if state.disconnect_task is not None:
            state.disconnect_task.cancel()
            state.disconnect_task = None
        return state
