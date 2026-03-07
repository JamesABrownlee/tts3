"""Combined Discord bot and FastAPI runner."""

from __future__ import annotations

import asyncio

import uvicorn

from api.main import create_api_app
from app.bootstrap import close_services, create_services
from app.config import load_settings
from app.logging import configure_logging
from bot.client import create_bot


async def _run() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    services = await create_services(settings)
    bot = await create_bot(services)
    api_app = create_api_app(services, discord_bot=bot)
    server = uvicorn.Server(uvicorn.Config(api_app, host=settings.api_host, port=settings.api_port, log_level=settings.log_level.lower()))
    server_task = asyncio.create_task(server.serve(), name="fastapi-server")
    bot_task = asyncio.create_task(bot.start(settings.discord_token), name="discord-bot")
    try:
        await asyncio.gather(server_task, bot_task)
    finally:
        server.should_exit = True
        if not bot.is_closed():
            await bot.close()
        await close_services(services)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
