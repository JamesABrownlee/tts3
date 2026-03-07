from __future__ import annotations

from tts.provider import prepare_text_for_synthesis


def test_prepare_text_for_synthesis_stabilizes_short_words():
    assert prepare_text_for_synthesis("no") == "no."
    assert prepare_text_for_synthesis("ok") == "ok."
    assert prepare_text_for_synthesis("hello") == "hello"
