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


@pytest.mark.asyncio
async def test_join_active_channel_triggers_welcome_when_enabled(orchestrator, services, monkeypatch):
    settings = await services.guild_settings_repository.get(501)
    await services.guild_settings_repository.save(replace(settings, welcome_enabled=True))
    state = services.runtime_states.get(501)
    start_session(state, voice_channel_id=700, text_channel_id=800)

    queued: list[object] = []

    async def fake_enqueue(event):
        queued.append(event)

    monkeypatch.setattr(services.queue_manager, "enqueue", fake_enqueue)
    async def fake_schedule_disconnect(guild):
        return None
    monkeypatch.setattr(orchestrator, "schedule_disconnect_if_empty", fake_schedule_disconnect)
    monkeypatch.setattr("bot.services.build_welcome_text", lambda name, current_time: f"Hello {name}")
    member = SimpleNamespace(id=1, bot=False, guild=SimpleNamespace(id=501), nick="Ali", display_name="Alice", name="Alice")
    before = SimpleNamespace(channel=None)
    after = SimpleNamespace(channel=SimpleNamespace(id=700))

    await orchestrator.handle_voice_transition(member, before, after)

    assert len(queued) == 1
    assert queued[0].segments[0].kind == "narrator"
    assert queued[0].segments[0].text == "Hello Ali"


@pytest.mark.asyncio
async def test_leave_active_channel_triggers_farewell_when_enabled(orchestrator, services, monkeypatch):
    settings = await services.guild_settings_repository.get(502)
    await services.guild_settings_repository.save(replace(settings, farewell_enabled=True))
    state = services.runtime_states.get(502)
    start_session(state, voice_channel_id=701, text_channel_id=801)

    queued: list[object] = []

    async def fake_enqueue(event):
        queued.append(event)

    monkeypatch.setattr(services.queue_manager, "enqueue", fake_enqueue)
    async def fake_schedule_disconnect(guild):
        return None
    monkeypatch.setattr(orchestrator, "schedule_disconnect_if_empty", fake_schedule_disconnect)
    monkeypatch.setattr("bot.services.build_farewell_text", lambda name: f"Bye {name}")
    member = SimpleNamespace(id=2, bot=False, guild=SimpleNamespace(id=502), nick=None, display_name="Bob", name="Bob")
    before = SimpleNamespace(channel=SimpleNamespace(id=701))
    after = SimpleNamespace(channel=None)

    await orchestrator.handle_voice_transition(member, before, after)

    assert len(queued) == 1
    assert queued[0].segments[0].text == "Bye Bob"


@pytest.mark.asyncio
async def test_move_into_active_channel_triggers_welcome(orchestrator, services, monkeypatch):
    settings = await services.guild_settings_repository.get(503)
    await services.guild_settings_repository.save(replace(settings, welcome_enabled=True))
    state = services.runtime_states.get(503)
    start_session(state, voice_channel_id=702, text_channel_id=802)
    queued: list[object] = []
    async def fake_enqueue(event):
        queued.append(event)
    monkeypatch.setattr(services.queue_manager, "enqueue", fake_enqueue)
    async def fake_schedule_disconnect(guild):
        return None
    monkeypatch.setattr(orchestrator, "schedule_disconnect_if_empty", fake_schedule_disconnect)
    monkeypatch.setattr("bot.services.build_welcome_text", lambda name, current_time: f"{name} has joined")
    member = SimpleNamespace(id=3, bot=False, guild=SimpleNamespace(id=503), nick=None, display_name="Cara", name="Cara")
    before = SimpleNamespace(channel=SimpleNamespace(id=999))
    after = SimpleNamespace(channel=SimpleNamespace(id=702))
    await orchestrator.handle_voice_transition(member, before, after)
    assert len(queued) == 1


@pytest.mark.asyncio
async def test_move_out_of_active_channel_triggers_farewell(orchestrator, services, monkeypatch):
    settings = await services.guild_settings_repository.get(504)
    await services.guild_settings_repository.save(replace(settings, farewell_enabled=True))
    state = services.runtime_states.get(504)
    start_session(state, voice_channel_id=703, text_channel_id=803)
    queued: list[object] = []

    async def fake_enqueue(event):
        queued.append(event)

    monkeypatch.setattr(services.queue_manager, "enqueue", fake_enqueue)
    async def fake_schedule_disconnect(guild):
        return None
    monkeypatch.setattr(orchestrator, "schedule_disconnect_if_empty", fake_schedule_disconnect)
    monkeypatch.setattr("bot.services.build_farewell_text", lambda name: f"{name} has left")
    member = SimpleNamespace(id=4, bot=False, guild=SimpleNamespace(id=504), nick=None, display_name="Drew", name="Drew")
    before = SimpleNamespace(channel=SimpleNamespace(id=703))
    after = SimpleNamespace(channel=SimpleNamespace(id=900))
    await orchestrator.handle_voice_transition(member, before, after)
    assert len(queued) == 1


@pytest.mark.asyncio
async def test_moving_between_two_non_active_channels_does_nothing(orchestrator, services, monkeypatch):
    settings = await services.guild_settings_repository.get(505)
    await services.guild_settings_repository.save(replace(settings, welcome_enabled=True, farewell_enabled=True))
    state = services.runtime_states.get(505)
    start_session(state, voice_channel_id=704, text_channel_id=804)
    queued: list[object] = []

    async def fake_enqueue(event):
        queued.append(event)

    monkeypatch.setattr(services.queue_manager, "enqueue", fake_enqueue)
    async def fake_schedule_disconnect(guild):
        return None
    monkeypatch.setattr(orchestrator, "schedule_disconnect_if_empty", fake_schedule_disconnect)
    member = SimpleNamespace(id=5, bot=False, guild=SimpleNamespace(id=505), nick=None, display_name="Eli", name="Eli")
    before = SimpleNamespace(channel=SimpleNamespace(id=901))
    after = SimpleNamespace(channel=SimpleNamespace(id=902))
    await orchestrator.handle_voice_transition(member, before, after)
    assert queued == []


@pytest.mark.asyncio
async def test_bot_user_voice_transition_does_nothing(orchestrator, services, monkeypatch):
    settings = await services.guild_settings_repository.get(506)
    await services.guild_settings_repository.save(replace(settings, welcome_enabled=True, farewell_enabled=True))
    state = services.runtime_states.get(506)
    start_session(state, voice_channel_id=705, text_channel_id=805)
    queued: list[object] = []

    async def fake_enqueue(event):
        queued.append(event)

    monkeypatch.setattr(services.queue_manager, "enqueue", fake_enqueue)
    async def fake_schedule_disconnect(guild):
        return None
    monkeypatch.setattr(orchestrator, "schedule_disconnect_if_empty", fake_schedule_disconnect)
    member = SimpleNamespace(id=6, bot=True, guild=SimpleNamespace(id=506), nick=None, display_name="Bot", name="Bot")
    before = SimpleNamespace(channel=None)
    after = SimpleNamespace(channel=SimpleNamespace(id=705))
    await orchestrator.handle_voice_transition(member, before, after)
    assert queued == []


@pytest.mark.asyncio
async def test_join_active_channel_uses_live_voice_client_when_runtime_flag_is_stale(orchestrator, services, monkeypatch):
    settings = await services.guild_settings_repository.get(507)
    await services.guild_settings_repository.save(replace(settings, welcome_enabled=True))
    state = services.runtime_states.get(507)
    state.active_voice_channel_id = 706
    state.currently_connected = False
    queued: list[object] = []

    async def fake_enqueue(event):
        queued.append(event)

    async def fake_schedule_disconnect(guild):
        return None

    monkeypatch.setattr(services.queue_manager, "enqueue", fake_enqueue)
    monkeypatch.setattr(orchestrator, "schedule_disconnect_if_empty", fake_schedule_disconnect)
    monkeypatch.setattr("bot.services.build_welcome_text", lambda name, current_time: f"Hello {name}")

    voice_client = SimpleNamespace(is_connected=lambda: True, channel=SimpleNamespace(id=706))
    guild = SimpleNamespace(id=507, voice_client=voice_client)
    member = SimpleNamespace(id=7, bot=False, guild=guild, nick=None, display_name="Finn", name="Finn")
    before = SimpleNamespace(channel=None)
    after = SimpleNamespace(channel=SimpleNamespace(id=706))

    await orchestrator.handle_voice_transition(member, before, after)

    assert len(queued) == 1
    assert services.runtime_states.get(507).currently_connected is True
