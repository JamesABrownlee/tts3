"""Message classification rules for semantic announcements."""

from __future__ import annotations

from domain.types import MessageKind


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def classify_message(
    clean_text: str,
    *,
    had_url: bool,
    attachments: list[object],
    attachment_filenames: list[str],
) -> MessageKind:
    has_attachments = bool(attachments)
    has_text = bool(clean_text)
    if had_url and not has_text and not has_attachments:
        return "link_only"
    if has_text and has_attachments:
        return "mixed"
    if has_text:
        return "text_only"
    if not has_attachments:
        return "empty"
    if all(name.lower().endswith(tuple(IMAGE_EXTENSIONS)) for name in attachment_filenames):
        return "image_only"
    if any(name.lower().endswith(tuple(IMAGE_EXTENSIONS)) for name in attachment_filenames):
        return "mixed"
    return "file_only"
