"""Application services used by Discord event and command handlers."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime
from time import time
from uuid import uuid4

import discord

from audio.generated_audio import GeneratedAudio
from bot.service_container import ServiceContainer
from domain.announcements import build_farewell_text, build_welcome_text
from domain.routing import can_narrate_message
from domain.services import mark_speaker, reset_session, should_announce_speaker, start_session
from domain.types import GuildRuntimeState, GuildSettings, ParsedMessage, SpeechSegment, SpokenEvent
from parsing.messages import parse_message


logger = logging.getLogger(__name__)
WORDS_PER_SECOND = 2.6
CHARS_PER_SECOND = 14
NO_TTS_PREFIX = "notts"
FORCED_TTS_PREFIX = "tts"


def estimate_speech_seconds(text: str) -> float:
    words = max(1, len(text.split()))
    chars = max(1, len(text))
    return max(words / WORDS_PER_SECOND, chars / CHARS_PER_SECOND)


@dataclass(slots=True, frozen=True)
class MessageDirectives:
    suppress_tts: bool
    force_tts: bool
    cleaned_content: str


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
        directives = self._extract_directives(message.content)
        if directives.suppress_tts:
            logger.info(
                "message_ignored",
                extra={"extra": {"guild_id": message.guild.id, "message_id": message.id, "author_id": message.author.id, "reason": "notts_prefix"}},
            )
            return
        settings = await self.services.guild_settings_repository.get(message.guild.id)
        runtime_state = self.services.runtime_states.get(message.guild.id)
        author_voice = member.voice.channel if member.voice else None
        active_voice_channel_id = runtime_state.active_voice_channel_id
        forced_voice_channel_id = active_voice_channel_id if directives.force_tts and active_voice_channel_id is not None else None
        allowed_by_routing = can_narrate_message(
            settings,
            runtime_state,
            author_voice_channel_id=author_voice.id if author_voice else None,
            text_channel_id=message.channel.id,
        )
        if not allowed_by_routing and not forced_voice_channel_id:
            logger.info(
                "message_ignored",
                extra={"extra": {"guild_id": message.guild.id, "message_id": message.id, "author_id": message.author.id, "reason": "routing_or_settings"}},
            )
            return
        if forced_voice_channel_id is None and (author_voice is None or not self._has_non_bot_users(author_voice)):
            logger.info(
                "message_ignored",
                extra={"extra": {"guild_id": message.guild.id, "message_id": message.id, "author_id": message.author.id, "reason": "author_not_in_eligible_vc"}},
            )
            return
        async with self.services.runtime_states.get_lock(message.guild.id):
            settings = await self.services.guild_settings_repository.get(message.guild.id)
            runtime_state = self.services.runtime_states.get(message.guild.id)
            started_session = False
            if forced_voice_channel_id is not None:
                if runtime_state.active_voice_channel_id is None:
                    logger.info(
                        "message_ignored",
                        extra={"extra": {"guild_id": message.guild.id, "message_id": message.id, "author_id": message.author.id, "reason": "forced_tts_without_active_session"}},
                    )
                    return
                target_voice_channel_id = runtime_state.active_voice_channel_id
            else:
                if author_voice is None:
                    return
                target_voice_channel_id = author_voice.id
            if runtime_state.active_voice_channel_id is None:
                if author_voice is None:
                    logger.info(
                        "message_ignored",
                        extra={"extra": {"guild_id": message.guild.id, "message_id": message.id, "author_id": message.author.id, "reason": "cannot_start_session_without_vc"}},
                    )
                    return
                started = await self._start_session(message.guild, runtime_state, author_voice, message.channel.id)
                if not started:
                    return
                started_session = True
                target_voice_channel_id = author_voice.id
            elif forced_voice_channel_id is None and runtime_state.active_voice_channel_id != author_voice.id:
                logger.info(
                    "message_ignored",
                    extra={"extra": {"guild_id": message.guild.id, "message_id": message.id, "author_id": message.author.id, "reason": "different_active_vc"}},
                )
                return
            voice_client = await self.ensure_live_voice_client(message.guild, target_voice_channel_id)
            if voice_client is None:
                reason = "session_start_failed_no_voice_client" if started_session else "live_voice_client_unavailable"
                logger.warning(
                    reason,
                    extra={
                        "extra": {
                            "guild_id": message.guild.id,
                            "message_id": message.id,
                            "author_id": message.author.id,
                            "voice_channel_id": target_voice_channel_id,
                        }
                    },
                )
                await self._clear_stale_session(message.guild.id, reason=reason, voice_channel_id=target_voice_channel_id)
                return
            parsed = self._parse_discord_message(message, directives.cleaned_content)
            event = await self._build_event(message, member, settings, runtime_state, parsed, target_voice_channel_id)
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

    async def handle_voice_transition(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot or member.guild is None:
            return
        guild = member.guild
        state = self.services.runtime_states.get(guild.id)
        active_channel_id = self._get_active_session_channel_id(guild, state)
        if active_channel_id is None:
            await self.schedule_disconnect_if_empty(guild)
            return
        before_channel_id = before.channel.id if before.channel else None
        after_channel_id = after.channel.id if after.channel else None
        joined_active = before_channel_id != active_channel_id and after_channel_id == active_channel_id
        left_active = before_channel_id == active_channel_id and after_channel_id != active_channel_id
        if not joined_active and not left_active:
            await self.schedule_disconnect_if_empty(guild)
            return
        settings = await self.services.guild_settings_repository.get(guild.id)
        if joined_active and settings.welcome_enabled:
            await self._enqueue_narrator_announcement(guild, active_channel_id, member, build_welcome_text(self._resolve_member_name(member), datetime.now()))
        elif left_active and settings.farewell_enabled:
            await self._enqueue_narrator_announcement(guild, active_channel_id, member, build_farewell_text(self._resolve_member_name(member)))
        await self.schedule_disconnect_if_empty(guild)

    async def _start_session(
        self,
        guild: discord.Guild,
        state: GuildRuntimeState,
        voice_channel: discord.VoiceChannel,
        text_channel_id: int,
    ) -> bool:
        logger.info(
            "session_start_attempt",
            extra={"extra": {"guild_id": guild.id, "voice_channel_id": voice_channel.id, "text_channel_id": text_channel_id}},
        )
        try:
            await self.services.voice_connections.ensure_connected(voice_channel)
        except Exception as exc:
            logger.warning(
                "session_start_failed",
                extra={
                    "extra": {
                        "guild_id": guild.id,
                        "voice_channel_id": voice_channel.id,
                        "text_channel_id": text_channel_id,
                        "error_type": type(exc).__name__,
                    }
                },
            )
            return False
        start_session(state, voice_channel_id=voice_channel.id, text_channel_id=text_channel_id)
        await self.services.guild_runtime_repository.save(state)
        logger.info(
            "session_start_connected",
            extra={"extra": {"guild_id": guild.id, "voice_channel_id": voice_channel.id, "text_channel_id": text_channel_id}},
        )
        logger.info(
            "session_started",
            extra={"extra": {"guild_id": guild.id, "voice_channel_id": voice_channel.id, "text_channel_id": text_channel_id}},
        )
        if state.queue_worker_task is None or state.queue_worker_task.done():
            state.queue_worker_task = asyncio.create_task(self._queue_worker(guild.id), name=f"guild-queue-{guild.id}")
        return True

    def _parse_discord_message(self, message: discord.Message, content: str) -> ParsedMessage:
        return parse_message(
            content,
            attachments=list(message.attachments),
            attachment_filenames=[attachment.filename for attachment in message.attachments],
            user_lookup=lambda discord_id: self._resolve_user_name(message.guild, discord_id),
            channel_lookup=lambda channel_id: self._resolve_channel_name(message.guild, channel_id),
            role_lookup=lambda role_id: self._resolve_role_name(message.guild, role_id),
        )

    def _extract_directives(self, content: str) -> MessageDirectives:
        stripped = content.lstrip()
        lowered = stripped.lower()
        if lowered.startswith(NO_TTS_PREFIX) and (len(stripped) == len(NO_TTS_PREFIX) or stripped[len(NO_TTS_PREFIX)].isspace()):
            return MessageDirectives(suppress_tts=True, force_tts=False, cleaned_content=stripped[len(NO_TTS_PREFIX):].lstrip())
        if lowered.startswith(FORCED_TTS_PREFIX) and len(stripped) > len(FORCED_TTS_PREFIX) and stripped[len(FORCED_TTS_PREFIX)].isspace():
            return MessageDirectives(suppress_tts=False, force_tts=True, cleaned_content=stripped[len(FORCED_TTS_PREFIX):].lstrip())
        return MessageDirectives(suppress_tts=False, force_tts=False, cleaned_content=content)

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
        narrator_changed = runtime_state.last_narrator_voice_id is not None and runtime_state.last_narrator_voice_id != narrator_voice_id
        narrator_intro_needed = narrator_changed or should_announce_speaker(settings, runtime_state, member.id)
        narrator_seconds = estimate_speech_seconds(narrator_text) if narrator_intro_needed else 0
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
        guild = voice_client.guild if voice_client is not None else self.services.voice_connections.get_guild(event.guild_id)
        if guild is not None:
            voice_client = await self.ensure_live_voice_client(guild, event.voice_channel_id)
        if voice_client is None or not voice_client.is_connected():
            logger.warning(
                "event_skipped_no_voice_client",
                extra={
                    "extra": {
                        "guild_id": event.guild_id,
                        "event_id": event.event_id,
                        "voice_channel_id": event.voice_channel_id,
                        "reconnect_attempted": guild is not None,
                    }
                },
            )
            await self._clear_stale_session(event.guild_id, reason="live_voice_client_unavailable", voice_channel_id=event.voice_channel_id)
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
            if segment.kind == "narrator":
                state.last_narrator_voice_id = segment.voice_id
        if event.speaker_discord_id is not None:
            mark_speaker(state, event.speaker_discord_id)
            await self.services.guild_runtime_repository.save(state)
        elif any(segment.kind == "narrator" for segment in event.segments):
            await self.services.guild_runtime_repository.save(state)

    async def _enqueue_narrator_announcement(
        self,
        guild: discord.Guild,
        voice_channel_id: int,
        member: discord.Member,
        text: str,
    ) -> None:
        state = self.services.runtime_states.get(guild.id)
        if state.active_voice_channel_id is None:
            logger.info(
                "narrator_announcement_skipped_no_live_session",
                extra={"extra": {"guild_id": guild.id, "voice_channel_id": voice_channel_id}},
            )
            return
        voice_client = await self.ensure_live_voice_client(guild, voice_channel_id)
        if voice_client is None:
            logger.info(
                "narrator_announcement_skipped_no_live_session",
                extra={"extra": {"guild_id": guild.id, "voice_channel_id": voice_channel_id, "reason": "no_voice_client"}},
            )
            await self._clear_stale_session(guild.id, reason="live_voice_client_unavailable", voice_channel_id=voice_channel_id)
            return
        settings = await self.services.guild_settings_repository.get(guild.id)
        narrator_voice_id = self.services.voice_catalog.resolve_narrator_voice(settings.narrator_voice_id)
        event = SpokenEvent(
            guild_id=guild.id,
            speaker_discord_id=None,
            speaker_display_name=self._resolve_member_name(member),
            message_id=None,
            text_channel_id=state.active_text_channel_id,
            voice_channel_id=voice_channel_id,
            segments=[SpeechSegment(text=text, voice_id=narrator_voice_id, kind="narrator")],
            created_at=time(),
            attempt_count=0,
            event_id=uuid4().hex,
        )
        await self.services.queue_manager.enqueue(event)
        logger.info(
            "event_enqueued",
            extra={"extra": {"guild_id": event.guild_id, "event_id": event.event_id, "message_id": None, "segment_count": len(event.segments), "reason": "voice_transition"}},
        )

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

    def _resolve_member_name(self, member: discord.Member) -> str:
        return member.nick or member.display_name or member.name

    def _get_active_session_channel_id(self, guild: discord.Guild, state: GuildRuntimeState) -> int | None:
        if state.active_voice_channel_id is not None and state.currently_connected:
            return state.active_voice_channel_id
        voice_client = getattr(guild, "voice_client", None)
        if voice_client is None or not voice_client.is_connected() or voice_client.channel is None:
            return None
        active_channel_id = state.active_voice_channel_id or voice_client.channel.id
        state.active_voice_channel_id = active_channel_id
        state.currently_connected = True
        return active_channel_id

    async def ensure_live_voice_client(
        self,
        guild: discord.Guild,
        target_voice_channel_id: int | None,
    ) -> discord.VoiceClient | None:
        voice_client = self.services.voice_connections.get(guild.id)
        if voice_client is not None and voice_client.is_connected():
            logger.info(
                "live_voice_client_recovered_from_registry",
                extra={"extra": {"guild_id": guild.id, "voice_channel_id": getattr(voice_client.channel, "id", None)}},
            )
            return voice_client
        guild_voice_client = getattr(guild, "voice_client", None)
        if guild_voice_client is not None and guild_voice_client.is_connected():
            self.services.voice_connections.register(guild, guild_voice_client)
            logger.info(
                "live_voice_client_recovered_from_guild",
                extra={"extra": {"guild_id": guild.id, "voice_channel_id": getattr(guild_voice_client.channel, "id", None)}},
            )
            return guild_voice_client
        if target_voice_channel_id is not None:
            channel = guild.get_channel(target_voice_channel_id)
            if isinstance(channel, discord.VoiceChannel):
                try:
                    voice_client = await self.services.voice_connections.ensure_connected(channel)
                except Exception as exc:
                    logger.warning(
                        "live_voice_client_unavailable",
                        extra={
                            "extra": {
                                "guild_id": guild.id,
                                "voice_channel_id": target_voice_channel_id,
                                "error_type": type(exc).__name__,
                            }
                        },
                    )
                    return None
                if voice_client is not None and voice_client.is_connected():
                    logger.info(
                        "live_voice_client_reconnected",
                        extra={"extra": {"guild_id": guild.id, "voice_channel_id": target_voice_channel_id}},
                    )
                    return voice_client
        logger.warning(
            "live_voice_client_unavailable",
            extra={"extra": {"guild_id": guild.id, "voice_channel_id": target_voice_channel_id}},
        )
        return None

    async def _clear_stale_session(self, guild_id: int, *, reason: str, voice_channel_id: int | None) -> None:
        state = self.services.runtime_states.get(guild_id)
        if state.active_voice_channel_id is None and not state.currently_connected:
            return
        self.services.runtime_states.clear_session(guild_id)
        await self.services.guild_runtime_repository.save(state)
        logger.warning(
            "stale_session_cleared",
            extra={"extra": {"guild_id": guild_id, "voice_channel_id": voice_channel_id, "reason": reason}},
        )
