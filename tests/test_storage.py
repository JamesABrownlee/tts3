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
