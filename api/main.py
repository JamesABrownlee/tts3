"""FastAPI application bootstrap."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from api.routes.announce import router as announce_router
from api.routes.obs import router as obs_router
from api.routes.settings import router as settings_router
from api.routes.synthesize import router as synthesize_router
from app.bootstrap import close_services, create_services
from app.config import load_settings
from app.services import ServiceContainer


def create_api_app(services: ServiceContainer, *, discord_bot=None) -> FastAPI:
    app = FastAPI(title="Discord TTS Bot API")
    app.state.services = services
    app.state.discord_bot = discord_bot

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        guild_entries: list[tuple[int, str]] = []
        bot = app.state.discord_bot
        if bot is not None and getattr(bot, "guilds", None):
            guild_entries = sorted([(guild.id, guild.name) for guild in bot.guilds], key=lambda item: item[1].lower())
        else:
            guild_entries = [(guild_id, f"Guild {guild_id}") for guild_id in await services.guild_settings_repository.list_guild_ids()]
        items = "\n".join(
            f'<li><a href="/settings/{guild_id}">{name}</a> <code>{guild_id}</code></li>'
            for guild_id, name in guild_entries
        ) or "<li>No guilds available yet. Start the combined runner and let the bot join guilds first.</li>"
        html = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>TTS Bot</title>
  <style>
    body {{ font-family: sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; }}
    ul {{ padding-left: 1.2rem; }}
    code {{ color: #666; }}
  </style>
</head>
<body>
  <h1>Discord TTS Bot</h1>
  <p>Select a guild to edit settings.</p>
  <ul>{items}</ul>
  <p><a href="/health">Health</a> | <a href="/api/voices">Voices API</a> | <a href="/obs/player">OBS Player</a></p>
</body>
</html>
"""
        return HTMLResponse(html)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(settings_router)
    app.include_router(synthesize_router)
    app.include_router(announce_router)
    app.include_router(obs_router)
    return app


@asynccontextmanager
async def _standalone_lifespan(app: FastAPI):
    settings = load_settings()
    services = await create_services(settings)
    app.state.services = services
    app.state.discord_bot = None
    try:
        yield
    finally:
        await close_services(services)


standalone_app = FastAPI(title="Discord TTS Bot API", lifespan=_standalone_lifespan)


@standalone_app.get("/", response_class=HTMLResponse)
async def standalone_index() -> HTMLResponse:
    services = standalone_app.state.services
    guild_ids = await services.guild_settings_repository.list_guild_ids()
    items = "\n".join(
        f'<li><a href="/settings/{guild_id}">Guild {guild_id}</a> <code>{guild_id}</code></li>'
        for guild_id in guild_ids
    ) or "<li>No guilds available yet. Start the combined runner and let the bot join guilds first.</li>"
    return HTMLResponse(
        f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>TTS Bot</title>
</head>
<body>
  <h1>Discord TTS Bot</h1>
  <p>Select a guild to edit settings.</p>
  <ul>{items}</ul>
  <p><a href="/health">Health</a> | <a href="/api/voices">Voices API</a> | <a href="/obs/player">OBS Player</a></p>
</body>
</html>
"""
    )
standalone_app.include_router(settings_router)
standalone_app.include_router(synthesize_router)
standalone_app.include_router(announce_router)
standalone_app.include_router(obs_router)


@standalone_app.get("/health")
async def standalone_health() -> dict[str, str]:
    return {"status": "ok"}
