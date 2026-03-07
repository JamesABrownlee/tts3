"""Text normalization for readable TTS output."""

from __future__ import annotations

import re


URL_RE = re.compile(r"https?://\S+")
WHITESPACE_RE = re.compile(r"\s+")
MARKUP_RE = re.compile(r"[*_~`|>]")
CUSTOM_EMOJI_RE = re.compile(r"<a?:([a-zA-Z0-9_]+):\d+>")
USER_MENTION_RE = re.compile(r"<@!?(\d+)>")
CHANNEL_MENTION_RE = re.compile(r"<#(\d+)>")
ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")


def replace_mentions(
    text: str,
    *,
    user_lookup: callable[[int], str | None],
    channel_lookup: callable[[int], str | None],
    role_lookup: callable[[int], str | None],
) -> str:
    def _user(match: re.Match[str]) -> str:
        return user_lookup(int(match.group(1))) or "someone"

    def _channel(match: re.Match[str]) -> str:
        return f"#{channel_lookup(int(match.group(1))) or 'channel'}"

    def _role(match: re.Match[str]) -> str:
        return role_lookup(int(match.group(1))) or "role"

    text = USER_MENTION_RE.sub(_user, text)
    text = CHANNEL_MENTION_RE.sub(_channel, text)
    text = ROLE_MENTION_RE.sub(_role, text)
    return CUSTOM_EMOJI_RE.sub(r"\1", text)


def normalize_text(text: str) -> str:
    text = URL_RE.sub("", text)
    text = MARKUP_RE.sub("", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text
