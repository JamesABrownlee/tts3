"""Core domain datatypes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal


SegmentKind = Literal["narrator", "user"]
IntroMode = Literal["always", "on_change", "first_only"]
MessageKind = Literal["text_only", "link_only", "image_only", "file_only", "mixed", "empty"]


@dataclass(slots=True, frozen=True)
class SpeechSegment:
    text: str
    voice_id: str
    kind: SegmentKind


@dataclass(slots=True, frozen=True)
class SpokenEvent:
    guild_id: int
    speaker_discord_id: int | None
    speaker_display_name: str | None
    message_id: int | None
    text_channel_id: int | None
    voice_channel_id: int | None
    segments: list[SpeechSegment]
    created_at: float
    attempt_count: int
    event_id: str


@dataclass(slots=True)
class GuildRuntimeState:
    guild_id: int
    active_voice_channel_id: int | None = None
    active_text_channel_id: int | None = None
    last_speaker_discord_id: int | None = None
    session_started_at: float | None = None
    disconnect_task: asyncio.Task[None] | None = None
    queue_worker_task: asyncio.Task[None] | None = None
    currently_connected: bool = False
    heard_speakers: set[int] = field(default_factory=set)


@dataclass(slots=True, frozen=True)
class Voice:
    voice_id: str
    display_name: str
    provider_name: str
    selectable_for_users: bool
    selectable_for_narrator: bool


@dataclass(slots=True, frozen=True)
class GuildSettings:
    guild_id: int
    allowed_text_channel_ids: list[int]
    narrator_voice_id: str | None
    fallback_user_voice_id: str | None
    narration_enabled: bool
    announce_links: bool
    announce_images: bool
    announce_files: bool
    same_vc_only: bool
    intro_mode: IntroMode
    max_combined_audio_seconds: int
    idle_disconnect_seconds: int
    created_at: int
    updated_at: int


@dataclass(slots=True, frozen=True)
class UserVoicePreference:
    discord_id: int
    display_name: str | None
    nickname: str | None
    voice_id: str | None
    created_at: int
    updated_at: int


@dataclass(slots=True, frozen=True)
class ParsedMessage:
    kind: MessageKind
    spoken_text: str
    has_attachment: bool
    attachment_is_image: bool
    attachment_is_file: bool

