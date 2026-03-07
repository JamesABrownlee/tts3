# Discord Roaming TTS Bot

A production-usable Discord TTS bot for guild voice narration. The bot roams per guild: it waits idle, joins the voice channel of the first eligible active group that types in an eligible text channel, narrates that group while they remain in the same voice channel, and disconnects once the active voice channel has no non-bot users left.

## What It Does

- Monitors eligible text channels per guild.
- Starts a session when an eligible user who is currently in voice sends a message.
- Joins that user's current voice channel and binds to that group for the session.
- Narrates messages sequentially with a narrator voice plus per-user voices.
- Tracks intro behavior with `always`, `on_change`, and `first_only`.
- Announces semantic events like links, images, and files.
- Enforces a hard combined speech budget of 20 seconds per spoken event.
- Persists guild settings, user voice preferences, and runtime session state in SQLite.
- Exposes slash commands for voice and service administration.

## Architecture

Project layout:

- `app/`: bootstrap, config, logging
- `bot/`: Discord client, orchestration, commands, event handlers
- `tts/`: TTS abstraction, HTTP provider, voice catalog
- `audio/`: generated audio, queue, playback, voice connections
- `parsing/`: normalization, classification, message parsing
- `storage/`: SQLite connection, migrations, repositories
- `domain/`: typed domain models, runtime state, routing/session rules
- `tests/`: pytest coverage for storage, parsing, routing, time budget, spoken events, queues

## Voice Model

There are two voice classes:

- Narrator voice: one per guild, used for phrases like `Alice said`
- User voice: one per user, used for reading actual message text

The default catalog preserves the previous bot's IDs:

- `en_us_001`
- `en_us_002`
- `en_us_006`
- `en_us_007`
- `en_us_009`
- `en_us_010`
- `en_uk_001`
- `google_translate`

TikTok voices are primary. `google_translate` remains available as the safety fallback voice. User-selectable voice lists exclude the currently configured narrator voice whenever alternatives exist.

## Roaming Session Behavior

Per guild, the bot is either `IDLE` or `ACTIVE`.

When idle:

- It watches eligible text channels.
- If a non-bot user in voice sends an eligible message, the bot joins that user's voice channel.
- The bot records `active_voice_channel_id` and `active_text_channel_id`.

When active:

- The bot narrates only for users in the same active voice channel.
- It prefers the session's `active_text_channel_id`.
- It ignores users in other voice channels until the active session ends.
- It leaves after the active voice channel has no non-bot users left, using `idle_disconnect_seconds` as the grace period.

## Spoken Output Rules

Text narration:

- First message in session: `Alice said` then `hello everyone`
- Same speaker continues: no repeated intro
- Speaker changes: narrator says `Bob said` then the new message

Semantic narration:

- Link only: `Alice posted a link`
- Image only: `Bob posted an image`
- File only: `Charlie posted a file`

Long messages:

- The bot reserves time for the narrator segment when needed.
- It truncates the user-spoken text conservatively to fit the time budget.
- If content still cannot safely fit, it falls back to `Alice sent a long message`.

## TTS Provider

Default provider stack:

- Primary: TikTok TTS HTTP endpoint
- Fallback: Google Translate TTS HTTP endpoint

Endpoints:

- TikTok: `https://tiktok-tts.weilnet.workers.dev/api/generation`
- Google: `https://translate.google.com/translate_tts`
- Default `User-Agent`: `Mozilla/5.0`

Reliability behavior:

- Shared async `aiohttp` client session
- Timeout handling
- Retries with exponential backoff
- Provider circuit breaker behavior
- Per-voice failure and cooldown tracking
- Automatic fallback to `google_translate`
- Fallback to configured `FALLBACK_VOICE` when a voice is failing

Audio is generated as temporary MP3 files today. The provider boundary is structured so streaming can be added later.

## Database Schema

`users`

- `discord_id INTEGER PRIMARY KEY`
- `display_name TEXT NULL`
- `nickname TEXT NULL`
- `voice_id TEXT NULL`
- `created_at INTEGER NOT NULL`
- `updated_at INTEGER NOT NULL`

`guild_settings`

- `guild_id INTEGER PRIMARY KEY`
- `allowed_text_channel_ids TEXT NOT NULL DEFAULT '[]'`
- `narrator_voice_id TEXT NULL`
- `fallback_user_voice_id TEXT NULL`
- `narration_enabled INTEGER NOT NULL DEFAULT 1`
- `announce_links INTEGER NOT NULL DEFAULT 1`
- `announce_images INTEGER NOT NULL DEFAULT 1`
- `announce_files INTEGER NOT NULL DEFAULT 1`
- `same_vc_only INTEGER NOT NULL DEFAULT 1`
- `intro_mode TEXT NOT NULL DEFAULT 'on_change'`
- `max_combined_audio_seconds INTEGER NOT NULL DEFAULT 20`
- `idle_disconnect_seconds INTEGER NOT NULL DEFAULT 15`
- `created_at INTEGER NOT NULL`
- `updated_at INTEGER NOT NULL`

`guild_runtime_state`

- `guild_id INTEGER PRIMARY KEY`
- `active_voice_channel_id INTEGER NULL`
- `active_text_channel_id INTEGER NULL`
- `last_speaker_discord_id INTEGER NULL`
- `session_started_at INTEGER NULL`
- `updated_at INTEGER NOT NULL`

`schema_migrations`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `name TEXT NOT NULL UNIQUE`
- `applied_at INTEGER NOT NULL`

Migrations are applied automatically on startup.

## Slash Commands

User commands:

- `/voice list`
- `/voice set <voice_id>`
- `/voice clear`
- `/voice current`
- `/voice preview <voice_id>`

Admin commands:

- `/service show`
- `/service channels add <text_channel>`
- `/service channels remove <text_channel>`
- `/service channels clear`
- `/service narrator set <voice_id>`
- `/service narrator show`
- `/service fallback-user-voice set <voice_id>`
- `/service enable`
- `/service disable`
- `/service intro-mode set <always|on_change|first_only>`
- `/service same-vc-only set <true|false>`
- `/service idle-disconnect set <seconds>`
- `/service session end`

## Environment Variables

Required:

- `DISCORD_TOKEN`
- `SQLITE_PATH`
- `TTS_PROVIDER`

Optional:

- `LOG_LEVEL=INFO`
- `TEMP_AUDIO_DIR=./temp_audio`
- `FFMPEG_PATH=ffmpeg`
- `TTS_HTTP_TIMEOUT=20`
- `TIKTOK_TTS_URL=https://tiktok-tts.weilnet.workers.dev/api/generation`
- `GOOGLE_TTS_URL=https://translate.google.com/translate_tts`
- `USER_AGENT=Mozilla/5.0`
- `FALLBACK_VOICE=en_us_001`
- `MAX_AUDIO_SECONDS=20`
- `VOICE_FAILURE_THRESHOLD=3`
- `VOICE_COOLDOWN_DURATION=300`

See `.env.example`.

## Setup

1. Create and activate a Python 3.11+ virtual environment.
2. Install dependencies:

```bash
python -m pip install -e .[dev]
```

3. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN`.
4. Ensure `ffmpeg` is installed and available on `PATH`, or set `FFMPEG_PATH`.
5. Start the bot:

```bash
python -m app.main
```

## Docker

Build locally:

```bash
docker build -t tts3:local .
```

Run locally with Compose:

```bash
docker compose up --build -d
```

The container image includes `ffmpeg`, runs as a non-root user, and stores SQLite data and generated audio under mounted volumes:

- `/app/data`
- `/app/temp_audio`

To stop:

```bash
docker compose down
```

## GitHub Actions

The repository includes [docker.yml](c:\Users\James\Documents\tts\.github\workflows\docker.yml), which:

- runs the pytest suite on pushes, pull requests, and manual dispatch
- builds a multi-architecture image for `linux/amd64` and `linux/arm64`
- pushes images to `ghcr.io/<owner>/<repo>` on `main` and version tags

Expected published image path for your target repository:

- `ghcr.io/jamesabrownlee/tts3`

## Tests

Run:

```bash
pytest -q -p no:cacheprovider --basetemp=.pytest_tmp
```

## Examples

- Alice says `hello everyone` in an eligible text channel while connected to voice:
  The bot joins Alice's voice channel, says `Alice said`, then speaks `hello everyone`.
- Alice sends another message immediately after:
  The bot speaks only the new message text without repeating `Alice said` in `on_change` mode.
- Bob speaks next:
  The bot says `Bob said`, then speaks Bob's message in Bob's selected voice.
- Alice posts only `https://example.com`:
  The bot says `Alice posted a link`.
- Bob uploads `image.png` without text:
  The bot says `Bob posted an image`.
- The last human leaves the active voice channel:
  The bot disconnects and returns to idle.

## Limitations

- Voice preview currently validates the voice ID but does not play preview audio through the slash command response.
- Audio playback uses temporary MP3 files rather than full streaming synthesis.
- Discord voice reconnection is delegated primarily to `discord.py`; the current implementation avoids duplicate connections and reconnects on new session start, but does not yet include a custom voice health supervisor.


## Voices

{
  "voices": [
    {
      "id": "en_us_ghostface",
      "name": "Ghost Face"
    },
    {
      "id": "en_us_c3po",
      "name": "C3PO"
    },
    {
      "id": "en_us_stitch",
      "name": "Stitch"
    },
    {
      "id": "en_us_stormtrooper",
      "name": "Stormtrooper"
    },
    {
      "id": "en_us_rocket",
      "name": "Rocket"
    },
    {
      "id": "en_female_madam_leota",
      "name": "Madame Leota"
    },
    {
      "id": "en_male_ghosthost",
      "name": "Ghost Host"
    },
    {
      "id": "en_male_pirate",
      "name": "Pirate"
    },
    {
      "id": "en_us_001",
      "name": "English US (Default)"
    },
    {
      "id": "en_us_002",
      "name": "Jessie"
    },
    {
      "id": "en_us_006",
      "name": "Joey"
    },
    {
      "id": "en_us_007",
      "name": "Professor"
    },
    {
      "id": "en_us_009",
      "name": "Scientist"
    },
    {
      "id": "en_us_010",
      "name": "Confidence"
    },
    {
      "id": "en_male_jomboy",
      "name": "Game On"
    },
    {
      "id": "en_female_samc",
      "name": "Empathetic"
    },
    {
      "id": "en_male_cody",
      "name": "Serious"
    },
    {
      "id": "en_female_makeup",
      "name": "Beauty Guru"
    },
    {
      "id": "en_female_richgirl",
      "name": "Bestie"
    },
    {
      "id": "en_male_grinch",
      "name": "Trickster"
    },
    {
      "id": "en_male_narration",
      "name": "Story Teller"
    },
    {
      "id": "en_male_deadpool",
      "name": "Mr. GoodGuy"
    },
    {
      "id": "en_male_jarvis",
      "name": "Alfred"
    },
    {
      "id": "en_male_ashmagic",
      "name": "ashmagic"
    },
    {
      "id": "en_male_olantekkers",
      "name": "olantekkers"
    },
    {
      "id": "en_male_ukneighbor",
      "name": "Lord Cringe"
    },
    {
      "id": "en_male_ukbutler",
      "name": "Mr. Meticulous"
    },
    {
      "id": "en_female_shenna",
      "name": "Debutante"
    },
    {
      "id": "en_female_pansino",
      "name": "Varsity"
    },
    {
      "id": "en_male_trevor",
      "name": "Marty"
    },
    {
      "id": "en_female_betty",
      "name": "Bae"
    },
    {
      "id": "en_male_cupid",
      "name": "Cupid"
    },
    {
      "id": "en_female_grandma",
      "name": "Granny"
    },
    {
      "id": "en_male_wizard",
      "name": "Magician"
    },
    {
      "id": "en_uk_001",
      "name": "Narrator"
    },
    {
      "id": "en_uk_003",
      "name": "Male English UK"
    },
    {
      "id": "en_au_001",
      "name": "Metro"
    },
    {
      "id": "en_au_002",
      "name": "Smooth"
    },
    {
      "id": "es_mx_002",
      "name": "Warm"
    },
    {
      "id": "google_translate",
      "name": "Normal voice"
    }
  ]
}
