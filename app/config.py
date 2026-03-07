"""Environment-driven application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


def _parse_int(name: str, default: int | None = None, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None:
        if default is None:
            raise ConfigError(f"Missing required integer environment variable: {name}")
        value = default
    else:
        try:
            value = int(raw)
        except ValueError as exc:
            raise ConfigError(f"Environment variable {name} must be an integer") from exc
    if minimum is not None and value < minimum:
        raise ConfigError(f"Environment variable {name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"Environment variable {name} must be <= {maximum}")
    return value


def _parse_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


@dataclass(slots=True, frozen=True)
class Settings:
    discord_token: str
    sqlite_path: Path
    tts_provider: str
    log_level: str
    temp_audio_dir: Path
    ffmpeg_path: str
    tts_http_timeout: int
    tiktok_tts_url: str
    google_tts_url: str
    user_agent: str
    fallback_voice_id: str
    max_audio_seconds: int
    voice_failure_threshold: int
    voice_cooldown_duration: int


def load_settings() -> Settings:
    """Load and validate environment variables."""

    load_dotenv()
    sqlite_path = Path(_parse_required("SQLITE_PATH")).expanduser()
    temp_audio_dir = Path(os.getenv("TEMP_AUDIO_DIR", "./temp_audio")).expanduser()
    return Settings(
        discord_token=_parse_required("DISCORD_TOKEN"),
        sqlite_path=sqlite_path,
        tts_provider=os.getenv("TTS_PROVIDER", "http"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        temp_audio_dir=temp_audio_dir,
        ffmpeg_path=os.getenv("FFMPEG_PATH", "ffmpeg"),
        tts_http_timeout=_parse_int("TTS_HTTP_TIMEOUT", 20, minimum=1, maximum=120),
        tiktok_tts_url=os.getenv("TIKTOK_TTS_URL", "https://tiktok-tts.weilnet.workers.dev/api/generation"),
        google_tts_url=os.getenv("GOOGLE_TTS_URL", "https://translate.google.com/translate_tts"),
        user_agent=os.getenv("USER_AGENT", "Mozilla/5.0"),
        fallback_voice_id=os.getenv("FALLBACK_VOICE", "en_us_001"),
        max_audio_seconds=_parse_int("MAX_AUDIO_SECONDS", 20, minimum=1, maximum=20),
        voice_failure_threshold=_parse_int("VOICE_FAILURE_THRESHOLD", 3, minimum=1, maximum=100),
        voice_cooldown_duration=_parse_int("VOICE_COOLDOWN_DURATION", 300, minimum=1, maximum=86400),
    )
