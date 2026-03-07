FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY api /app/api
COPY app /app/app
COPY audio /app/audio
COPY bot /app/bot
COPY domain /app/domain
COPY parsing /app/parsing
COPY storage /app/storage
COPY tts /app/tts

RUN pip install --no-cache-dir .

RUN useradd --create-home --shell /usr/sbin/nologin botuser \
    && mkdir -p /app/data /app/temp_audio /app/temp_audio/api \
    && chown -R botuser:botuser /app

USER botuser

ENV SQLITE_PATH=/app/data/bot.sqlite3 \
    TEMP_AUDIO_DIR=/app/temp_audio \
    API_AUDIO_DIR=/app/temp_audio/api \
    FFMPEG_PATH=/usr/bin/ffmpeg \
    TTS_PROVIDER=http \
    LOG_LEVEL=INFO \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    API_AUDIO_TTL_SECONDS=3600 \
    TTS_HTTP_TIMEOUT=20 \
    TIKTOK_TTS_URL=https://tiktok-tts.weilnet.workers.dev/api/generation \
    GOOGLE_TTS_URL=https://translate.google.com/translate_tts \
    USER_AGENT=Mozilla/5.0 \
    FALLBACK_VOICE=en_us_001 \
    MAX_AUDIO_SECONDS=20 \
    VOICE_FAILURE_THRESHOLD=3 \
    VOICE_COOLDOWN_DURATION=300

EXPOSE 8000

CMD ["python", "-m", "app.runner"]
