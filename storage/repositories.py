"""Repository objects for SQLite persistence."""

from __future__ import annotations

import json
from dataclasses import replace

from domain.types import GuildRuntimeState, GuildSettings, UserVoicePreference
from storage.db import Database
from storage.models import default_guild_settings, now_ts


class UserRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self, discord_id: int) -> UserVoicePreference | None:
        row = await self.db.fetchone("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        if row is None:
            return None
        return UserVoicePreference(
            discord_id=row["discord_id"],
            display_name=row["display_name"],
            nickname=row["nickname"],
            voice_id=row["voice_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def upsert(self, discord_id: int, *, display_name: str | None, nickname: str | None, voice_id: str | None) -> UserVoicePreference:
        existing = await self.get(discord_id)
        current = now_ts()
        if existing is None:
            await self.db.execute(
                """
                INSERT INTO users (discord_id, display_name, nickname, voice_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (discord_id, display_name, nickname, voice_id, current, current),
            )
        else:
            await self.db.execute(
                """
                UPDATE users
                SET display_name = ?, nickname = ?, voice_id = ?, updated_at = ?
                WHERE discord_id = ?
                """,
                (display_name, nickname, voice_id, current, discord_id),
            )
        preference = await self.get(discord_id)
        if preference is None:
            raise RuntimeError("Failed to persist user preference")
        return preference


class GuildSettingsRepository:
    def __init__(self, db: Database, fallback_voice_id: str) -> None:
        self.db = db
        self.fallback_voice_id = fallback_voice_id

    async def get(self, guild_id: int) -> GuildSettings:
        row = await self.db.fetchone("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,))
        if row is None:
            settings = default_guild_settings(guild_id, self.fallback_voice_id)
            await self.save(settings)
            return settings
        return GuildSettings(
            guild_id=row["guild_id"],
            allowed_text_channel_ids=json.loads(row["allowed_text_channel_ids"]),
            narrator_voice_id=row["narrator_voice_id"],
            fallback_user_voice_id=row["fallback_user_voice_id"],
            narration_enabled=bool(row["narration_enabled"]),
            announce_links=bool(row["announce_links"]),
            announce_images=bool(row["announce_images"]),
            announce_files=bool(row["announce_files"]),
            same_vc_only=bool(row["same_vc_only"]),
            intro_mode=row["intro_mode"],
            max_combined_audio_seconds=row["max_combined_audio_seconds"],
            idle_disconnect_seconds=row["idle_disconnect_seconds"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def save(self, settings: GuildSettings) -> GuildSettings:
        await self.db.execute(
            """
            INSERT INTO guild_settings (
                guild_id, allowed_text_channel_ids, narrator_voice_id, fallback_user_voice_id,
                narration_enabled, announce_links, announce_images, announce_files, same_vc_only,
                intro_mode, max_combined_audio_seconds, idle_disconnect_seconds, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                allowed_text_channel_ids = excluded.allowed_text_channel_ids,
                narrator_voice_id = excluded.narrator_voice_id,
                fallback_user_voice_id = excluded.fallback_user_voice_id,
                narration_enabled = excluded.narration_enabled,
                announce_links = excluded.announce_links,
                announce_images = excluded.announce_images,
                announce_files = excluded.announce_files,
                same_vc_only = excluded.same_vc_only,
                intro_mode = excluded.intro_mode,
                max_combined_audio_seconds = excluded.max_combined_audio_seconds,
                idle_disconnect_seconds = excluded.idle_disconnect_seconds,
                updated_at = excluded.updated_at
            """,
            (
                settings.guild_id,
                json.dumps(settings.allowed_text_channel_ids),
                settings.narrator_voice_id,
                settings.fallback_user_voice_id,
                int(settings.narration_enabled),
                int(settings.announce_links),
                int(settings.announce_images),
                int(settings.announce_files),
                int(settings.same_vc_only),
                settings.intro_mode,
                min(settings.max_combined_audio_seconds, 20),
                settings.idle_disconnect_seconds,
                settings.created_at,
                settings.updated_at,
            ),
        )
        return settings

    async def update(self, guild_id: int, **changes: object) -> GuildSettings:
        current = await self.get(guild_id)
        updated = replace(current, **changes, updated_at=now_ts())
        return await self.save(updated)

    async def list_guild_ids(self) -> list[int]:
        rows = await self.db.fetchall("SELECT guild_id FROM guild_settings ORDER BY guild_id ASC")
        return [int(row["guild_id"]) for row in rows]


class GuildRuntimeRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self, guild_id: int) -> GuildRuntimeState:
        row = await self.db.fetchone("SELECT * FROM guild_runtime_state WHERE guild_id = ?", (guild_id,))
        if row is None:
            state = GuildRuntimeState(guild_id=guild_id)
            await self.save(state)
            return state
        return GuildRuntimeState(
            guild_id=row["guild_id"],
            active_voice_channel_id=row["active_voice_channel_id"],
            active_text_channel_id=row["active_text_channel_id"],
            last_speaker_discord_id=row["last_speaker_discord_id"],
            session_started_at=row["session_started_at"],
        )

    async def save(self, state: GuildRuntimeState) -> GuildRuntimeState:
        await self.db.execute(
            """
            INSERT INTO guild_runtime_state (
                guild_id, active_voice_channel_id, active_text_channel_id,
                last_speaker_discord_id, session_started_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                active_voice_channel_id = excluded.active_voice_channel_id,
                active_text_channel_id = excluded.active_text_channel_id,
                last_speaker_discord_id = excluded.last_speaker_discord_id,
                session_started_at = excluded.session_started_at,
                updated_at = excluded.updated_at
            """,
            (
                state.guild_id,
                state.active_voice_channel_id,
                state.active_text_channel_id,
                state.last_speaker_discord_id,
                state.session_started_at,
                now_ts(),
            ),
        )
        return state
