"""Application services used by Discord event and command handlers."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from time import time
from uuid import uuid4

import discord

from audio.generated_audio import GeneratedAudio
from bot.service_container import ServiceContainer
from domain.routing import can_narrate_message
from domain.services import mark_speaker, reset_session, should_announce_speaker, start_session
from domain.types import GuildRuntimeState, GuildSettings, ParsedMessage, SpeechSegment, SpokenEvent
from parsing.messages import parse_message


logger = logging.getLogger(__name__)
WORDS_PER_SECOND = 2.6
CHARS_PER_SECOND = 14


def estimate_speech_seconds(text: str) -> float:
    words = max(1, len(text.split()))
    chars = max(1, len(text))
    return max(words / WORDS_PER_SECOND, chars / CHARS_PER_SECOND)


class SpeechOrchestrator:
    """Coordinates parsing, session routing, queueing, and playback."""

    def __init__(self, services: ServiceContainer) -> None:
        self.services = services

    async def handle_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        member = message.author if isinstance(message.author, discord.Member) else message.guild.get_member(message.author.id)
        if member is None:
            return
        settings = await self.services.guild_settings_repository.get(message.guild.id)
        runtime_state = self.services.runtime_states.get(message.guild.id)
        author_voice = member.voice.channel if member.voice else None
        if not can_narrate_message(
            settings,
            runtime_state,
            author_voice_channel_id=author_voice.id if author_voice else None,
            text_channel_id=message.channel.id,
        ):
            logger.info(
                "message_ignored",
                extra={"extra": {"guild_id": message.guild.id, "message_id": message.id, "author_id": message.author.id, "reason": "routing_or_settings"}},
            )
            return
        if author_voice is None or not self._has_non_bot_users(author_voice):
            logger.info(
                "message_ignored",
                extra={"extra": {"guild_id": message.guild.id, "message_id": message.id, "author_id": message.author.id, "reason": "author_not_in_eligible_vc"}},
            )
            return
        async with self.services.runtime_states.get_lock(message.guild.id):
            settings = await self.services.guild_settings_repository.get(message.guild.id)
            runtime_state = self.services.runtime_states.get(message.guild.id)
            if runtime_state.active_voice_channel_id is None:
                await self._start_session(message.guild, runtime_state, author_voice, message.channel.id)
            elif runtime_state.active_voice_channel_id != author_voice.id:
                logger.info(
                    "message_ignored",
                    extra={"extra": {"guild_id": message.guild.id, "message_id": message.id, "author_id": message.author.id, "reason": "different_active_vc"}},
                )
                return
            parsed = self._parse_discord_message(message)
            event = await self._build_event(message, member, settings, runtime_state, parsed, author_voice.id)
            if event is None:
                logger.info(
                    "message_ignored",
                    extra={"extra": {"guild_id": message.guild.id, "message_id": message.id, "author_id": message.author.id, "reason": "nothing_to_speak"}},
                )
                return
            await self.services.queue_manager.enqueue(event)
            logger.info(
                "event_enqueued",
                extra={"extra": {"guild_id": event.guild_id, "event_id": event.event_id, "message_id": event.message_id, "segment_count": len(event.segments)}},
            )

    async def _start_session(
        self,
        guild: discord.Guild,
        state: GuildRuntimeState,
        voice_channel: discord.VoiceChannel,
        text_channel_id: int,
    ) -> None:
        await self.services.voice_connections.ensure_connected(voice_channel)
        start_session(state, voice_channel_id=voice_channel.id, text_channel_id=text_channel_id)
        await self.services.guild_runtime_repository.save(state)
        logger.info(
            "session_started",
            extra={"extra": {"guild_id": guild.id, "voice_channel_id": voice_channel.id, "text_channel_id": text_channel_id}},
        )
        if state.queue_worker_task is None or state.queue_worker_task.done():
            state.queue_worker_task = asyncio.create_task(self._queue_worker(guild.id), name=f"guild-queue-{guild.id}")

    def _parse_discord_message(self, message: discord.Message) -> ParsedMessage:
        return parse_message(
            message.content,
            attachments=list(message.attachments),
            attachment_filenames=[attachment.filename for attachment in message.attachments],
            user_lookup=lambda discord_id: self._resolve_user_name(message.guild, discord_id),
            channel_lookup=lambda channel_id: self._resolve_channel_name(message.guild, channel_id),
            role_lookup=lambda role_id: self._resolve_role_name(message.guild, role_id),
        )

    async def _build_event(
        self,
        message: discord.Message,
        member: discord.Member,
        settings: GuildSettings,
        runtime_state: GuildRuntimeState,
        parsed: ParsedMessage,
        voice_channel_id: int,
    ) -> SpokenEvent | None:
        narrator_voice_id = self.services.voice_catalog.resolve_narrator_voice(settings.narrator_voice_id)
        existing_preference = await self.services.user_repository.get(member.id)
        user_preference = await self.services.user_repository.upsert(
            member.id,
            display_name=member.display_name,
            nickname=member.nick,
            voice_id=existing_preference.voice_id if existing_preference else None,
        )
        user_voice_id = self.services.voice_catalog.resolve_user_voice(user_preference.voice_id or settings.fallback_user_voice_id, narrator_voice_id)
        display_name = member.display_name
        semantic = self._semantic_text(settings, parsed, display_name)
        if semantic is not None:
            segments = [SpeechSegment(text=semantic, voice_id=narrator_voice_id, kind="narrator")]
            return SpokenEvent(
                guild_id=message.guild.id,
                speaker_discord_id=member.id,
                speaker_display_name=display_name,
                message_id=message.id,
                text_channel_id=message.channel.id,
                voice_channel_id=voice_channel_id,
                segments=segments,
                created_at=time(),
                attempt_count=0,
                event_id=uuid4().hex,
            )
        if not parsed.spoken_text:
            return None
        narrator_text = f"{display_name} said"
        narrator_seconds = estimate_speech_seconds(narrator_text) if should_announce_speaker(settings, runtime_state, member.id) else 0
        remaining_budget = max(1.0, settings.max_combined_audio_seconds - narrator_seconds)
        user_text = self._truncate_to_budget(parsed.spoken_text, remaining_budget)
        if not user_text:
            user_text = f"{display_name} sent a long message"
            segments = [SpeechSegment(text=user_text, voice_id=narrator_voice_id, kind="narrator")]
        else:
            segments: list[SpeechSegment] = []
            if narrator_seconds:
                segments.append(SpeechSegment(text=narrator_text, voice_id=narrator_voice_id, kind="narrator"))
            if estimate_speech_seconds(user_text) > remaining_budget:
                user_text = f"{display_name} sent a long message"
                segments = [SpeechSegment(text=user_text, voice_id=narrator_voice_id, kind="narrator")]
            else:
                segments.append(SpeechSegment(text=user_text, voice_id=user_voice_id, kind="user"))
        return SpokenEvent(
            guild_id=message.guild.id,
            speaker_discord_id=member.id,
            speaker_display_name=display_name,
            message_id=message.id,
            text_channel_id=message.channel.id,
            voice_channel_id=voice_channel_id,
            segments=segments,
            created_at=time(),
            attempt_count=0,
            event_id=uuid4().hex,
        )

    def _semantic_text(self, settings: GuildSettings, parsed: ParsedMessage, display_name: str) -> str | None:
        if parsed.kind == "link_only" and settings.announce_links:
            return f"{display_name} posted a link"
        if parsed.kind == "image_only" and settings.announce_images:
            return f"{display_name} posted an image"
        if parsed.kind == "file_only" and settings.announce_files:
            return f"{display_name} posted a file"
        if parsed.kind == "mixed" and not parsed.spoken_text and parsed.has_attachment:
            if parsed.attachment_is_image and settings.announce_images:
                return f"{display_name} posted an image"
            if parsed.attachment_is_file and settings.announce_files:
                return f"{display_name} posted a file"
        return None

    def _truncate_to_budget(self, text: str, max_seconds: float) -> str:
        if estimate_speech_seconds(text) <= max_seconds:
            return text
        words = text.split()
        result: list[str] = []
        for word in words:
            candidate = " ".join([*result, word])
            if estimate_speech_seconds(candidate) > max_seconds:
                break
            result.append(word)
        return " ".join(result).strip()

    async def _queue_worker(self, guild_id: int) -> None:
        queue = self.services.queue_manager.get_queue(guild_id)
        while True:
            event = await queue.get()
            try:
                await self._play_event(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("event_playback_failed", extra={"extra": {"guild_id": guild_id, "event_id": event.event_id, "error_type": type(exc).__name__}})
            finally:
                queue.task_done()

    async def _play_event(self, event: SpokenEvent) -> None:
        voice_client = self.services.voice_connections.get(event.guild_id)
        if voice_client is None or not voice_client.is_connected():
            logger.warning("event_skipped_no_voice_client", extra={"extra": {"guild_id": event.guild_id, "event_id": event.event_id}})
            return
        state = self.services.runtime_states.get(event.guild_id)
        for segment in event.segments:
            logger.info(
                "segment_synthesizing",
                extra={"extra": {"guild_id": event.guild_id, "event_id": event.event_id, "voice_id": segment.voice_id, "kind": segment.kind}},
            )
            audio = await self.services.tts_provider.synthesize(
                segment.text,
                segment.voice_id,
                max_seconds=20,
            )
            await self.services.audio_player.play(voice_client, audio)
            logger.info(
                "segment_played",
                extra={"extra": {"guild_id": event.guild_id, "event_id": event.event_id, "voice_id": segment.voice_id, "kind": segment.kind}},
            )
        if event.speaker_discord_id is not None:
            mark_speaker(state, event.speaker_discord_id)
            await self.services.guild_runtime_repository.save(state)

    async def schedule_disconnect_if_empty(self, guild: discord.Guild) -> None:
        state = self.services.runtime_states.get(guild.id)
        if state.active_voice_channel_id is None:
            return
        channel = guild.get_channel(state.active_voice_channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            await self.end_session(guild.id)
            return
        if self._has_non_bot_users(channel):
            if state.disconnect_task is not None:
                state.disconnect_task.cancel()
                state.disconnect_task = None
                logger.info(
                    "disconnect_cancelled",
                    extra={"extra": {"guild_id": guild.id, "voice_channel_id": getattr(channel, "id", state.active_voice_channel_id)}},
                )
            return
        settings = await self.services.guild_settings_repository.get(guild.id)
        if state.disconnect_task is None or state.disconnect_task.done():
            state.disconnect_task = asyncio.create_task(self._delayed_disconnect(guild.id, settings.idle_disconnect_seconds))
            logger.info(
                "disconnect_scheduled",
                extra={
                    "extra": {
                        "guild_id": guild.id,
                        "voice_channel_id": getattr(channel, "id", state.active_voice_channel_id),
                        "delay_seconds": settings.idle_disconnect_seconds,
                    }
                },
            )

    async def _delayed_disconnect(self, guild_id: int, seconds: int) -> None:
        try:
            await asyncio.sleep(max(0, seconds))
            await self.end_session(guild_id)
        except asyncio.CancelledError:
            raise

    async def end_session(self, guild_id: int) -> None:
        state = self.services.runtime_states.get(guild_id)
        if state.disconnect_task is not None:
            state.disconnect_task.cancel()
            state.disconnect_task = None
        await self.services.voice_connections.disconnect(guild_id)
        reset_session(state)
        await self.services.guild_runtime_repository.save(state)
        logger.info("session_ended", extra={"extra": {"guild_id": guild_id}})

    def _has_non_bot_users(self, channel: discord.VoiceChannel) -> bool:
        return any(not member.bot for member in channel.members)

    def _resolve_user_name(self, guild: discord.Guild | None, discord_id: int) -> str | None:
        if guild is None:
            return None
        member = guild.get_member(discord_id)
        return member.display_name if member else None

    def _resolve_channel_name(self, guild: discord.Guild | None, channel_id: int) -> str | None:
        if guild is None:
            return None
        channel = guild.get_channel(channel_id)
        return channel.name if isinstance(channel, discord.abc.GuildChannel) else None

    def _resolve_role_name(self, guild: discord.Guild | None, role_id: int) -> str | None:
        if guild is None:
            return None
        role = guild.get_role(role_id)
        return role.name if role else None
