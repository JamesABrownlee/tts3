from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import bot.services as services_module
from audio.generated_audio import GeneratedAudio
from domain.types import SpeechSegment, SpokenEvent


@dataclass
class FakeVoiceClient:
    guild: "FakeGuild"
    channel: "FakeVoiceChannel"
    connected: bool = True

    def is_connected(self) -> bool:
        return self.connected

    async def move_to(self, channel: "FakeVoiceChannel") -> None:
        self.channel = channel

    async def disconnect(self, force: bool = False) -> None:
        self.connected = False


@dataclass
class FakeVoiceChannel:
    guild: "FakeGuild"
    id: int
    members: list["FakeMember"]

    async def connect(self, reconnect: bool = True) -> FakeVoiceClient:
        client = FakeVoiceClient(self.guild, self, True)
        self.guild.voice_client = client
        return client


@dataclass
class FakeMember:
    id: int
    display_name: str
    nick: str | None
    bot: bool
    voice: SimpleNamespace | None


class FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id
        self.voice_client: FakeVoiceClient | None = None
        self._members: dict[int, FakeMember] = {}
        self._channels: dict[int, FakeVoiceChannel] = {}

    def add_member(self, member: FakeMember) -> None:
        self._members[member.id] = member

    def add_channel(self, channel: FakeVoiceChannel) -> None:
        self._channels[channel.id] = channel

    def get_member(self, member_id: int) -> FakeMember | None:
        return self._members.get(member_id)

    def get_channel(self, channel_id: int) -> FakeVoiceChannel | None:
        return self._channels.get(channel_id)


def _build_event(guild_id: int, voice_channel_id: int) -> SpokenEvent:
    return SpokenEvent(
        guild_id=guild_id,
        speaker_discord_id=101,
        speaker_display_name="Tester",
        message_id=202,
        text_channel_id=303,
        voice_channel_id=voice_channel_id,
        segments=[SpeechSegment(text="hello", voice_id="en_us_001", kind="user")],
        created_at=0.0,
        attempt_count=0,
        event_id="evt-1",
    )


@pytest.mark.asyncio
async def test_handle_message_requires_live_voice_client(orchestrator, services, monkeypatch):
    guild = FakeGuild(10)
    voice_channel = FakeVoiceChannel(guild=guild, id=20, members=[])
    member = FakeMember(id=42, display_name="Alice", nick=None, bot=False, voice=SimpleNamespace(channel=voice_channel))
    voice_channel.members.append(member)
    guild.add_member(member)
    guild.add_channel(voice_channel)
    message = SimpleNamespace(
        guild=guild,
        author=member,
        content="hello there",
        channel=SimpleNamespace(id=30),
        id=40,
        attachments=[],
    )

    monkeypatch.setattr(services_module.discord, "Member", FakeMember)
    monkeypatch.setattr(services_module.discord, "VoiceChannel", FakeVoiceChannel)
    monkeypatch.setattr(orchestrator, "ensure_live_voice_client", AsyncMock(return_value=None))

    await orchestrator.handle_message(message)

    queue = services.queue_manager.get_queue(guild.id)
    assert queue.qsize() == 0
    state = services.runtime_states.get(guild.id)
    assert state.active_voice_channel_id is None


@pytest.mark.asyncio
async def test_play_event_recovers_from_guild_voice_client(orchestrator, services, monkeypatch):
    guild = FakeGuild(55)
    voice_channel = FakeVoiceChannel(guild=guild, id=77, members=[])
    guild.add_channel(voice_channel)
    voice_client = FakeVoiceClient(guild=guild, channel=voice_channel, connected=True)
    guild.voice_client = voice_client
    services.voice_connections._guilds[guild.id] = guild

    async def fake_synthesize(text: str, voice_id: str, max_seconds: int) -> GeneratedAudio:
        return GeneratedAudio(path=Path("fake.wav"), content_type="audio/wav", voice_id=voice_id, text=text)

    play_calls: list[FakeVoiceClient] = []

    async def fake_play(client: FakeVoiceClient, audio: GeneratedAudio) -> None:
        play_calls.append(client)

    monkeypatch.setattr(services.tts_provider, "synthesize", fake_synthesize)
    monkeypatch.setattr(services.audio_player, "play", fake_play)

    event = _build_event(guild.id, voice_channel.id)
    await orchestrator._play_event(event)

    assert services.voice_connections.get(guild.id) is voice_client
    assert play_calls == [voice_client]


@pytest.mark.asyncio
async def test_play_event_reconnects_using_voice_channel(orchestrator, services, monkeypatch):
    guild = FakeGuild(88)
    voice_channel = FakeVoiceChannel(guild=guild, id=99, members=[])
    guild.add_channel(voice_channel)
    services.voice_connections._guilds[guild.id] = guild

    reconnected_client = FakeVoiceClient(guild=guild, channel=voice_channel, connected=True)

    async def fake_ensure_connected(channel: FakeVoiceChannel) -> FakeVoiceClient:
        return reconnected_client

    async def fake_synthesize(text: str, voice_id: str, max_seconds: int) -> GeneratedAudio:
        return GeneratedAudio(path=Path("fake.wav"), content_type="audio/wav", voice_id=voice_id, text=text)

    play_calls: list[FakeVoiceClient] = []

    async def fake_play(client: FakeVoiceClient, audio: GeneratedAudio) -> None:
        play_calls.append(client)

    monkeypatch.setattr(services.voice_connections, "ensure_connected", fake_ensure_connected)
    monkeypatch.setattr(services.tts_provider, "synthesize", fake_synthesize)
    monkeypatch.setattr(services.audio_player, "play", fake_play)
    monkeypatch.setattr(services_module.discord, "VoiceChannel", FakeVoiceChannel)

    event = _build_event(guild.id, voice_channel.id)
    await orchestrator._play_event(event)

    assert play_calls == [reconnected_client]


@pytest.mark.asyncio
async def test_narrator_announcement_requires_live_session(orchestrator, services, monkeypatch):
    guild = FakeGuild(123)
    voice_channel = FakeVoiceChannel(guild=guild, id=456, members=[])
    guild.add_channel(voice_channel)
    member = FakeMember(id=1, display_name="Bob", nick=None, bot=False, voice=None)
    state = services.runtime_states.get(guild.id)
    state.active_voice_channel_id = voice_channel.id
    state.currently_connected = True

    monkeypatch.setattr(orchestrator, "ensure_live_voice_client", AsyncMock(return_value=None))

    await orchestrator._enqueue_narrator_announcement(guild, voice_channel.id, member, "Welcome")

    queue = services.queue_manager.get_queue(guild.id)
    assert queue.qsize() == 0
    assert state.active_voice_channel_id is None


@pytest.mark.asyncio
async def test_stale_session_cleared_when_recovery_fails(orchestrator, services, monkeypatch):
    guild_id = 222
    state = services.runtime_states.get(guild_id)
    state.active_voice_channel_id = 333
    state.currently_connected = True

    monkeypatch.setattr(orchestrator, "ensure_live_voice_client", AsyncMock(return_value=None))

    event = _build_event(guild_id, 333)
    await orchestrator._play_event(event)

    assert state.active_voice_channel_id is None
