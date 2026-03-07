"""Voice connection orchestration."""

from __future__ import annotations

import asyncio
import logging

import discord


logger = logging.getLogger(__name__)


class VoiceConnectionManager:
    """Owns Discord voice clients by guild."""

    def __init__(self) -> None:
        self._clients: dict[int, discord.VoiceClient] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, guild_id: int) -> asyncio.Lock:
        lock = self._locks.get(guild_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[guild_id] = lock
        return lock

    def get(self, guild_id: int) -> discord.VoiceClient | None:
        return self._clients.get(guild_id)

    async def ensure_connected(self, channel: discord.VoiceChannel) -> discord.VoiceClient:
        async with self._lock(channel.guild.id):
            current = self._clients.get(channel.guild.id)
            if current and current.is_connected():
                if current.channel and current.channel.id != channel.id:
                    await current.move_to(channel)
                return current
            voice_client = channel.guild.voice_client
            if voice_client and voice_client.is_connected():
                self._clients[channel.guild.id] = voice_client
                if voice_client.channel and voice_client.channel.id != channel.id:
                    await voice_client.move_to(channel)
                return voice_client
            connected = await channel.connect(reconnect=True)
            self._clients[channel.guild.id] = connected
            return connected

    async def disconnect(self, guild_id: int) -> None:
        async with self._lock(guild_id):
            client = self._clients.pop(guild_id, None)
            if client and client.is_connected():
                await client.disconnect(force=False)
                logger.info("voice_disconnected", extra={"extra": {"guild_id": guild_id}})
