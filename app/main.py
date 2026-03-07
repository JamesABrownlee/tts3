"""Application entrypoint."""

from __future__ import annotations

import asyncio

from app.config import load_settings
from app.logging import configure_logging
from bot.client import create_bot


async def _run() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    bot = await create_bot(settings)
    try:
        await bot.start(settings.discord_token)
    finally:
        if not bot.is_closed():
            await bot.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
