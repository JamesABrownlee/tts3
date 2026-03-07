"""Provider abstraction for TTS synthesis."""

from __future__ import annotations

from typing import Protocol

from audio.generated_audio import GeneratedAudio
from domain.types import Voice


class TTSProvider(Protocol):
    async def list_voices(self) -> list[Voice]:
        ...

    async def synthesize(self, text: str, voice_id: str, *, max_seconds: int) -> GeneratedAudio:
        ...
