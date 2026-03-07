from __future__ import annotations

from parsing.messages import parse_message


def test_message_parsing_and_normalization():
    parsed = parse_message(
        "Hello   <@123> https://example.com **there**",
        attachments=[],
        attachment_filenames=[],
        user_lookup=lambda _: "Alice",
        channel_lookup=lambda _: "general",
        role_lookup=lambda _: "admin",
    )
    assert parsed.spoken_text == "Hello Alice there"
    assert parsed.kind == "text_only"


def test_semantic_announcements_link_image_file():
    link = parse_message(
        "https://example.com",
        attachments=[],
        attachment_filenames=[],
        user_lookup=lambda _: None,
        channel_lookup=lambda _: None,
        role_lookup=lambda _: None,
    )
    image = parse_message(
        "",
        attachments=[object()],
        attachment_filenames=["picture.png"],
        user_lookup=lambda _: None,
        channel_lookup=lambda _: None,
        role_lookup=lambda _: None,
    )
    file = parse_message(
        "",
        attachments=[object()],
        attachment_filenames=["document.pdf"],
        user_lookup=lambda _: None,
        channel_lookup=lambda _: None,
        role_lookup=lambda _: None,
    )
    assert link.kind == "link_only"
    assert image.kind == "image_only"
    assert file.kind == "file_only"
