"""HTTP TTS provider using TikTok TTS with Google fallback."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from uuid import uuid4

import aiohttp

from app.config import Settings
from audio.generated_audio import GeneratedAudio
from domain.types import Voice
from tts.voices import DEFAULT_VOICES


logger = logging.getLogger(__name__)
SHORT_WORD_RE = re.compile(r"^[A-Za-z]{1,3}$")


class TTSProviderError(RuntimeError):
    """Raised when synthesis cannot be completed."""


@dataclass(slots=True)
class VoiceFailureState:
    failures: int = 0
    cooldown_until: float = 0.0


@dataclass(slots=True)
class CircuitBreaker:
    failures: int = 0
    opened_until: float = 0.0

    def is_open(self) -> bool:
        return monotonic() < self.opened_until

    def record_failure(self, cooldown_seconds: int) -> None:
        self.failures += 1
        self.opened_until = monotonic() + cooldown_seconds

    def reset(self) -> None:
        self.failures = 0
        self.opened_until = 0.0


class HttpTTSProvider:
    """Synthesizes MP3 audio with a TikTok-first, Google-fallback flow."""

    def __init__(self, settings: Settings, session: aiohttp.ClientSession) -> None:
        self.settings = settings
        self.session = session
        self._voice_failures: dict[str, VoiceFailureState] = {}
        self._tiktok_breaker = CircuitBreaker()

    async def list_voices(self) -> list[Voice]:
        return list(DEFAULT_VOICES)

    async def synthesize(self, text: str, voice_id: str, *, max_seconds: int) -> GeneratedAudio:
        prepared_text = prepare_text_for_synthesis(text)
        resolved_voice = self._resolve_voice_for_attempt(voice_id)
        try:
            if resolved_voice == "google_translate":
                return await self._synthesize_google(prepared_text, resolved_voice, original_text=text)
            return await self._synthesize_with_fallback(prepared_text, resolved_voice, max_seconds=max_seconds, original_text=text)
        except Exception:
            self._mark_voice_failure(resolved_voice)
            fallback_voice = self.settings.fallback_voice_id
            if fallback_voice != resolved_voice:
                return (
                    await self._synthesize_google(prepared_text, "google_translate", original_text=text)
                    if fallback_voice == "google_translate"
                    else await self._synthesize_with_fallback(prepared_text, fallback_voice, max_seconds=max_seconds, original_text=text)
                )
            raise

    def reset_voice_state(self, voice_id: str | None = None) -> None:
        if voice_id is None:
            self._voice_failures.clear()
            self._tiktok_breaker.reset()
            return
        self._voice_failures.pop(voice_id, None)

    def _resolve_voice_for_attempt(self, voice_id: str) -> str:
        state = self._voice_failures.get(voice_id)
        if state and state.cooldown_until > monotonic():
            return self.settings.fallback_voice_id
        return voice_id

    def _mark_voice_failure(self, voice_id: str) -> None:
        state = self._voice_failures.setdefault(voice_id, VoiceFailureState())
        state.failures += 1
        if state.failures >= self.settings.voice_failure_threshold:
            state.cooldown_until = monotonic() + self.settings.voice_cooldown_duration
            state.failures = 0

    async def _synthesize_with_fallback(self, text: str, voice_id: str, *, max_seconds: int, original_text: str) -> GeneratedAudio:
        if self._tiktok_breaker.is_open():
            return await self._synthesize_google(text, "google_translate", original_text=original_text)
        for attempt in range(3):
            try:
                return await self._synthesize_tiktok(text, voice_id, original_text=original_text)
            except Exception as exc:
                await asyncio.sleep(0.5 * (2**attempt))
                logger.warning("tiktok_synthesis_failed", extra={"extra": {"voice_id": voice_id, "attempt": attempt + 1, "error_type": type(exc).__name__}})
        self._tiktok_breaker.record_failure(self.settings.voice_cooldown_duration)
        return await self._synthesize_google(text, "google_translate", original_text=original_text)

    async def _synthesize_tiktok(self, text: str, voice_id: str, *, original_text: str) -> GeneratedAudio:
        async with self.session.post(
            self.settings.tiktok_tts_url,
            json={"text": text, "voice": voice_id},
            headers={"User-Agent": self.settings.user_agent},
            timeout=aiohttp.ClientTimeout(total=self.settings.tts_http_timeout),
        ) as response:
            response.raise_for_status()
            payload = await response.json()
        data = payload.get("data")
        if not data:
            raise TTSProviderError("TikTok provider returned no audio data")
        raw_audio = base64.b64decode(data)
        path = await self._write_temp_audio(raw_audio, suffix=".mp3")
        self._tiktok_breaker.reset()
        return GeneratedAudio(path=path, content_type="audio/mpeg", voice_id=voice_id, text=original_text)

    async def _synthesize_google(self, text: str, voice_id: str, *, original_text: str) -> GeneratedAudio:
        params = {"ie": "UTF-8", "client": "tw-ob", "tl": "en", "q": text}
        async with self.session.get(
            self.settings.google_tts_url,
            params=params,
            headers={"User-Agent": self.settings.user_agent},
            timeout=aiohttp.ClientTimeout(total=self.settings.tts_http_timeout),
        ) as response:
            response.raise_for_status()
            raw_audio = await response.read()
        path = await self._write_temp_audio(raw_audio, suffix=".mp3")
        return GeneratedAudio(path=path, content_type="audio/mpeg", voice_id=voice_id, text=original_text)

    async def _write_temp_audio(self, data: bytes, *, suffix: str) -> Path:
        self.settings.temp_audio_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.temp_audio_dir / f"{uuid4().hex}{suffix}"
        path.write_bytes(data)
        return path


def prepare_text_for_synthesis(text: str) -> str:
    stripped = text.strip()
    if SHORT_WORD_RE.fullmatch(stripped) and stripped[-1].isalnum():
        return f"{stripped}."
    return stripped
