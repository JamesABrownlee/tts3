from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot.services import estimate_speech_seconds
from domain.services import mark_speaker


@pytest.mark.asyncio
async def test_time_limit_enforcement_and_truncation(orchestrator):
    text = "word " * 200
    truncated = orchestrator._truncate_to_budget(text, 3)
    assert truncated
    assert estimate_speech_seconds(truncated) <= 3


@pytest.mark.asyncio
async def test_spoken_event_creation(orchestrator, services):
    guild_id = 501
    settings = await services.guild_settings_repository.get(guild_id)
    state = services.runtime_states.get(guild_id)
    message = SimpleNamespace(
        guild=SimpleNamespace(id=guild_id),
        id=1001,
        channel=SimpleNamespace(id=2002),
    )
    member = SimpleNamespace(id=42, display_name="Alice", nick=None)
    parsed = SimpleNamespace(kind="text_only", spoken_text="hello there", has_attachment=False, attachment_is_image=False, attachment_is_file=False)
    event = await orchestrator._build_event(message, member, settings, state, parsed, 3003)
    assert event is not None
    assert event.guild_id == guild_id
    assert event.segments[0].text == "Alice said"
    assert event.segments[-1].text == "hello there"


@pytest.mark.asyncio
async def test_queue_ordering_behavior(services):
    queue = services.queue_manager.get_queue(77)
    first = SimpleNamespace(guild_id=77, event_id="1")
    second = SimpleNamespace(guild_id=77, event_id="2")
    await queue.put(first)
    await queue.put(second)
    assert (await queue.get()).event_id == "1"
    assert (await queue.get()).event_id == "2"
