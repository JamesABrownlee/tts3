"""Sequential Discord playback helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import discord

from app.config import Settings
from audio.generated_audio import GeneratedAudio


class AudioPlaybackError(RuntimeError):
    """Raised when Discord playback fails."""


class AudioPlayer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def play(self, voice_client: discord.VoiceClient, audio: GeneratedAudio) -> None:
        loop = asyncio.get_running_loop()
        finished = loop.create_future()

        def _after(error: Exception | None) -> None:
            if error is not None:
                loop.call_soon_threadsafe(finished.set_exception, AudioPlaybackError(str(error)))
                return
            loop.call_soon_threadsafe(finished.set_result, None)

        source = discord.FFmpegPCMAudio(
            str(audio.path),
            executable=self.settings.ffmpeg_path,
        )
        voice_client.play(source, after=_after)
        try:
            await finished
        finally:
            self._cleanup(audio.path)

    def _cleanup(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
