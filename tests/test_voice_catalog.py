from __future__ import annotations

from tts.voices import DEFAULT_VOICES, VoiceCatalog


def test_narrator_voice_exclusion_from_user_selectable():
    voices = VoiceCatalog(DEFAULT_VOICES, "en_us_001").list_user_selectable("en_us_001")
    assert all(voice.voice_id != "en_us_001" for voice in voices)
    assert any(voice.voice_id == "google_translate" for voice in voices)
