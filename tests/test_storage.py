from __future__ import annotations

from dataclasses import replace

import pytest

from storage.db import Database


@pytest.mark.asyncio
async def test_database_schema_creation_and_migrations(settings):
    db = Database(settings.sqlite_path)
    await db.connect()
    await db.apply_migrations()
    try:
        rows = await db.fetchall("SELECT name FROM sqlite_master WHERE type = 'table'")
        names = {row["name"] for row in rows}
        assert {"users", "guild_settings", "guild_runtime_state", "schema_migrations"} <= names
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_user_voice_persistence(services):
    saved = await services.user_repository.upsert(1, display_name="Alice", nickname="Ali", voice_id="en_us_002")
    loaded = await services.user_repository.get(1)
    assert saved.voice_id == "en_us_002"
    assert loaded is not None
    assert loaded.nickname == "Ali"


@pytest.mark.asyncio
async def test_guild_settings_persistence(services):
    settings = await services.guild_settings_repository.get(123)
    updated = await services.guild_settings_repository.save(
        replace(
            settings,
            allowed_text_channel_ids=[1, 2],
            narrator_voice_id="en_us_007",
            fallback_user_voice_id="en_us_002",
            narration_enabled=False,
            welcome_enabled=True,
            farewell_enabled=True,
            announce_images=False,
            same_vc_only=False,
            intro_mode="always",
            max_combined_audio_seconds=19,
            idle_disconnect_seconds=30,
        )
    )
    loaded = await services.guild_settings_repository.get(123)
    assert updated.narrator_voice_id == "en_us_007"
    assert loaded.allowed_text_channel_ids == [1, 2]
    assert loaded.same_vc_only is False
    assert loaded.welcome_enabled is True
    assert loaded.farewell_enabled is True


@pytest.mark.asyncio
async def test_guild_settings_defaults_welcome_and_farewell_off(services):
    settings = await services.guild_settings_repository.get(321)
    assert settings.welcome_enabled is False
    assert settings.farewell_enabled is False


@pytest.mark.asyncio
async def test_existing_guild_settings_migrate_welcome_and_farewell_safely(settings):
    db = Database(settings.sqlite_path)
    await db.connect()
    try:
        await db.execute(
            """
            CREATE TABLE schema_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                applied_at INTEGER NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE guild_settings (
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
            )
            """
        )
        await db.execute(
            """
            INSERT INTO guild_settings (
                guild_id, allowed_text_channel_ids, narrator_voice_id, fallback_user_voice_id,
                narration_enabled, announce_links, announce_images, announce_files, same_vc_only,
                intro_mode, max_combined_audio_seconds, idle_disconnect_seconds, created_at, updated_at
            ) VALUES (?, '[]', NULL, ?, 1, 1, 1, 1, 1, 'on_change', 20, 15, 1, 1)
            """,
            (444, settings.fallback_voice_id),
        )
        await db.apply_migrations()
        repository = __import__("storage.repositories", fromlist=["GuildSettingsRepository"]).GuildSettingsRepository(db, settings.fallback_voice_id)
        loaded = await repository.get(444)
        assert loaded.welcome_enabled is False
        assert loaded.farewell_enabled is False
    finally:
        await db.close()
