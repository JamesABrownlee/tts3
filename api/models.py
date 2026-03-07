"""Pydantic models for the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from domain.types import IntroMode


class VoiceResponse(BaseModel):
    voice_id: str
    display_name: str
    provider_name: str
    selectable_for_users: bool
    selectable_for_narrator: bool


class GuildSettingsResponse(BaseModel):
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


class GuildSettingsUpdateRequest(BaseModel):
    allowed_text_channel_ids: list[int] | None = None
    narrator_voice_id: str | None = None
    fallback_user_voice_id: str | None = None
    narration_enabled: bool | None = None
    announce_links: bool | None = None
    announce_images: bool | None = None
    announce_files: bool | None = None
    same_vc_only: bool | None = None
    intro_mode: IntroMode | None = None
    max_combined_audio_seconds: int | None = Field(default=None, ge=1, le=20)
    idle_disconnect_seconds: int | None = Field(default=None, ge=0, le=300)


class SynthesizeRequest(BaseModel):
    text: str
    voice_id: str
    max_seconds: int = Field(default=20, ge=1, le=20)
    download: bool = False

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Text must not be empty")
        return stripped


class SynthesizeResponse(BaseModel):
    file_id: str
    voice_id: str
    text: str
    audio_url: str
    content_type: str


class AnnouncementRequest(BaseModel):
    text: str
    voice_id: str
    target: Literal["obs"] = "obs"

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Text must not be empty")
        return stripped


class ChatAnnouncementRequest(BaseModel):
    user: str
    message: str
    voice_id: str
    target: Literal["obs"] = "obs"

    @field_validator("user", "message")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field must not be empty")
        return stripped


class AnnouncementResponse(BaseModel):
    queued: bool
    target: str
    file_id: str
    audio_url: str
    voice_id: str
    text: str
    delivered_clients: int
