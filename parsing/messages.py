"""High-level message parsing into TTS-friendly text."""

from __future__ import annotations

from parsing.classification import classify_message
from parsing.normalization import URL_RE, normalize_text, replace_mentions
from domain.types import ParsedMessage


def parse_message(
    content: str,
    *,
    attachments: list[object],
    attachment_filenames: list[str],
    user_lookup: callable[[int], str | None],
    channel_lookup: callable[[int], str | None],
    role_lookup: callable[[int], str | None],
) -> ParsedMessage:
    had_url = bool(URL_RE.search(content))
    with_mentions = replace_mentions(
        content,
        user_lookup=user_lookup,
        channel_lookup=channel_lookup,
        role_lookup=role_lookup,
    )
    spoken_text = normalize_text(with_mentions)
    kind = classify_message(
        spoken_text,
        had_url=had_url,
        attachments=attachments,
        attachment_filenames=attachment_filenames,
    )
    attachment_is_image = kind == "image_only"
    attachment_is_file = kind == "file_only"
    return ParsedMessage(
        kind=kind,
        spoken_text=spoken_text,
        has_attachment=bool(attachments),
        attachment_is_image=attachment_is_image,
        attachment_is_file=attachment_is_file,
    )
