from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

import bot.services as orchestrator_module
from domain.routing import can_narrate_message, is_text_channel_eligible
from domain.services import reset_session, should_announce_speaker, start_session


@pytest.mark.asyncio
async def test_eligible_text_channel_logic(services):
    settings = await services.guild_settings_repository.get(10)
    assert is_text_channel_eligible(settings, 999) is True
    constrained = replace(settings, allowed_text_channel_ids=[10, 11])
    assert is_text_channel_eligible(constrained, 10) is True
    assert is_text_channel_eligible(constrained, 99) is False


@pytest.mark.asyncio
async def test_session_start_when_idle_and_message_comes_from_user_in_vc(services):
    state = services.runtime_states.get(1)
    start_session(state, voice_channel_id=22, text_channel_id=44)
    assert state.active_voice_channel_id == 22
    assert state.active_text_channel_id == 44
    assert state.currently_connected is True


@pytest.mark.asyncio
async def test_ignore_message_when_author_not_in_vc(services):
    settings = await services.guild_settings_repository.get(11)
    state = services.runtime_states.get(11)
    assert can_narrate_message(settings, state, author_voice_channel_id=None, text_channel_id=1) is False


@pytest.mark.asyncio
async def test_ignore_second_group_while_first_active(services):
    settings = await services.guild_settings_repository.get(12)
    state = services.runtime_states.get(12)
    start_session(state, voice_channel_id=50, text_channel_id=9)
    assert can_narrate_message(settings, state, author_voice_channel_id=77, text_channel_id=9) is False


@pytest.mark.asyncio
async def test_intro_behavior_first_same_changed(services):
    settings = await services.guild_settings_repository.get(13)
    state = services.runtime_states.get(13)
    assert should_announce_speaker(settings, state, 1) is True
    state.last_speaker_discord_id = 1
    assert should_announce_speaker(settings, state, 1) is False
    assert should_announce_speaker(settings, state, 2) is True


@pytest.mark.asyncio
async def test_session_ends_when_active_vc_becomes_empty(orchestrator, services, monkeypatch):
    class FakeVoiceChannel:
        def __init__(self) -> None:
            self.members = [SimpleNamespace(bot=True)]

    monkeypatch.setattr(orchestrator_module.discord, "VoiceChannel", FakeVoiceChannel)
    state = services.runtime_states.get(99)
    start_session(state, voice_channel_id=123, text_channel_id=456)
    settings = await services.guild_settings_repository.get(99)
    await services.guild_settings_repository.save(replace(settings, idle_disconnect_seconds=0))
    channel = FakeVoiceChannel()
    guild = SimpleNamespace(
        id=99,
        get_channel=lambda channel_id: channel if channel_id == 123 else None,
    )
    await orchestrator.schedule_disconnect_if_empty(guild)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert state.active_voice_channel_id is None


@pytest.mark.asyncio
async def test_reset_session_clears_state(services):
    state = services.runtime_states.get(33)
    start_session(state, voice_channel_id=7, text_channel_id=8)
    reset_session(state)
    assert state.active_voice_channel_id is None
    assert state.currently_connected is False


@pytest.mark.asyncio
async def test_notts_prefix_is_ignored(orchestrator, services, monkeypatch):
    queued: list[object] = []

    async def fake_enqueue(event):
        queued.append(event)

    monkeypatch.setattr(services.queue_manager, "enqueue", fake_enqueue)
    message = SimpleNamespace(
        guild=SimpleNamespace(id=201, get_member=lambda member_id: member),
        author=None,
        content="notts ignore this",
        id=301,
        channel=SimpleNamespace(id=401),
        attachments=[],
    )
    member = SimpleNamespace(id=501, bot=False, display_name="Alice", nick=None, voice=SimpleNamespace(channel=SimpleNamespace(id=601, members=[SimpleNamespace(bot=False)])))
    message.author = member
    await orchestrator.handle_message(message)
    assert queued == []


@pytest.mark.asyncio
async def test_forced_tts_from_non_vc_user_uses_active_session(orchestrator, services, monkeypatch):
    state = services.runtime_states.get(202)
    start_session(state, voice_channel_id=777, text_channel_id=888)

    parsed_inputs: list[str] = []
    queued: list[object] = []

    def fake_parse(message, content):
        parsed_inputs.append(content)
        return SimpleNamespace(kind="text_only", spoken_text=content, has_attachment=False, attachment_is_image=False, attachment_is_file=False)

    async def fake_build_event(message, member, settings, runtime_state, parsed, voice_channel_id):
        return SimpleNamespace(
            guild_id=message.guild.id,
            event_id="evt-1",
            message_id=message.id,
            segments=[SimpleNamespace(text=parsed.spoken_text)],
            voice_channel_id=voice_channel_id,
        )

    async def fake_enqueue(event):
        queued.append(event)

    monkeypatch.setattr(orchestrator, "_parse_discord_message", fake_parse)
    monkeypatch.setattr(orchestrator, "_build_event", fake_build_event)
    monkeypatch.setattr(services.queue_manager, "enqueue", fake_enqueue)

    member = SimpleNamespace(id=502, bot=False, display_name="Bob", nick=None, voice=None)
    guild = SimpleNamespace(id=202, get_member=lambda member_id: member)
    message = SimpleNamespace(
        guild=guild,
        author=member,
        content="tts read this to the channel",
        id=302,
        channel=SimpleNamespace(id=888),
        attachments=[],
    )

    await orchestrator.handle_message(message)

    assert parsed_inputs == ["read this to the channel"]
    assert len(queued) == 1
    assert queued[0].voice_channel_id == 777
