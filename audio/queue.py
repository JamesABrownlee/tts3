"""Per-guild event queues."""

from __future__ import annotations

import asyncio

from domain.types import SpokenEvent


class GuildQueueManager:
    def __init__(self) -> None:
        self._queues: dict[int, asyncio.Queue[SpokenEvent]] = {}

    def get_queue(self, guild_id: int) -> asyncio.Queue[SpokenEvent]:
        queue = self._queues.get(guild_id)
        if queue is None:
            queue = asyncio.Queue()
            self._queues[guild_id] = queue
        return queue

    async def enqueue(self, event: SpokenEvent) -> None:
        await self.get_queue(event.guild_id).put(event)
