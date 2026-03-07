"""Storage row models and defaults."""

from __future__ import annotations

from dataclasses import replace
from time import time

from domain.types import GuildSettings


DEFAULT_INTRO_MODE = "on_change"


def now_ts() -> int:
    return int(time())


def default_guild_settings(guild_id: int, fallback_voice_id: str, *, timestamp: int | None = None) -> GuildSettings:
    current = timestamp or now_ts()
    return GuildSettings(
        guild_id=guild_id,
        allowed_text_channel_ids=[],
        narrator_voice_id=None,
        fallback_user_voice_id=fallback_voice_id,
        narration_enabled=True,
        welcome_enabled=False,
        farewell_enabled=False,
        announce_links=True,
        announce_images=True,
        announce_files=True,
        same_vc_only=True,
        intro_mode="on_change",
        max_combined_audio_seconds=20,
        idle_disconnect_seconds=15,
        created_at=current,
        updated_at=current,
    )


def touch_guild_settings(settings: GuildSettings, *, timestamp: int | None = None, **changes: object) -> GuildSettings:
    return replace(settings, updated_at=timestamp or now_ts(), **changes)
