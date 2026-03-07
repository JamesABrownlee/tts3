"""SQLite migrations."""

from __future__ import annotations

MIGRATIONS: list[tuple[str, str]] = [
    (
        "001_initial_schema",
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            applied_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            discord_id INTEGER PRIMARY KEY,
            display_name TEXT NULL,
            nickname TEXT NULL,
            voice_id TEXT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            allowed_text_channel_ids TEXT NOT NULL DEFAULT '[]',
            narrator_voice_id TEXT NULL,
            fallback_user_voice_id TEXT NULL,
            narration_enabled INTEGER NOT NULL DEFAULT 1,
            announce_links INTEGER NOT NULL DEFAULT 1,
            announce_images INTEGER NOT NULL DEFAULT 1,
            announce_files INTEGER NOT NULL DEFAULT 1,
            same_vc_only INTEGER NOT NULL DEFAULT 1,
            intro_mode TEXT NOT NULL DEFAULT 'on_change',
            max_combined_audio_seconds INTEGER NOT NULL DEFAULT 20,
            idle_disconnect_seconds INTEGER NOT NULL DEFAULT 15,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS guild_runtime_state (
            guild_id INTEGER PRIMARY KEY,
            active_voice_channel_id INTEGER NULL,
            active_text_channel_id INTEGER NULL,
            last_speaker_discord_id INTEGER NULL,
            session_started_at INTEGER NULL,
            updated_at INTEGER NOT NULL
        );
        """.strip(),
    ),
]
