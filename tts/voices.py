"""Static voice catalog and per-guild selection logic."""

from __future__ import annotations

from dataclasses import dataclass

from domain.types import Voice


DEFAULT_VOICES: list[Voice] = [
    Voice("en_us_ghostface", "Ghost Face", "tiktok", True, True),
    Voice("en_us_c3po", "C3PO", "tiktok", True, True),
    Voice("en_us_stitch", "Stitch", "tiktok", True, True),
    Voice("en_us_stormtrooper", "Stormtrooper", "tiktok", True, True),
    Voice("en_us_rocket", "Rocket", "tiktok", True, True),
    Voice("en_female_madam_leota", "Madame Leota", "tiktok", True, True),
    Voice("en_male_ghosthost", "Ghost Host", "tiktok", True, True),
    Voice("en_male_pirate", "Pirate", "tiktok", True, True),
    Voice("en_us_001", "English US (Default)", "tiktok", True, True),
    Voice("en_us_002", "Jessie", "tiktok", True, True),
    Voice("en_us_006", "Joey", "tiktok", True, True),
    Voice("en_us_007", "Professor", "tiktok", True, True),
    Voice("en_us_009", "Scientist", "tiktok", True, True),
    Voice("en_us_010", "Confidence", "tiktok", True, True),
    Voice("en_male_jomboy", "Game On", "tiktok", True, True),
    Voice("en_female_samc", "Empathetic", "tiktok", True, True),
    Voice("en_male_cody", "Serious", "tiktok", True, True),
    Voice("en_female_makeup", "Beauty Guru", "tiktok", True, True),
    Voice("en_female_richgirl", "Bestie", "tiktok", True, True),
    Voice("en_male_grinch", "Trickster", "tiktok", True, True),
    Voice("en_male_narration", "Story Teller", "tiktok", True, True),
    Voice("en_male_deadpool", "Mr. GoodGuy", "tiktok", True, True),
    Voice("en_male_jarvis", "Alfred", "tiktok", True, True),
    Voice("en_male_ashmagic", "ashmagic", "tiktok", True, True),
    Voice("en_male_olantekkers", "olantekkers", "tiktok", True, True),
    Voice("en_male_ukneighbor", "Lord Cringe", "tiktok", True, True),
    Voice("en_male_ukbutler", "Mr. Meticulous", "tiktok", True, True),
    Voice("en_female_shenna", "Debutante", "tiktok", True, True),
    Voice("en_female_pansino", "Varsity", "tiktok", True, True),
    Voice("en_male_trevor", "Marty", "tiktok", True, True),
    Voice("en_female_betty", "Bae", "tiktok", True, True),
    Voice("en_male_cupid", "Cupid", "tiktok", True, True),
    Voice("en_female_grandma", "Granny", "tiktok", True, True),
    Voice("en_male_wizard", "Magician", "tiktok", True, True),
    Voice("en_uk_001", "Narrator", "tiktok", True, True),
    Voice("en_uk_003", "Male English UK", "tiktok", True, True),
    Voice("en_au_001", "Metro", "tiktok", True, True),
    Voice("en_au_002", "Smooth", "tiktok", True, True),
    Voice("es_mx_002", "Warm", "tiktok", True, True),
    Voice("google_translate", "Normal voice", "google", True, True),
]


@dataclass(slots=True)
class VoiceCatalog:
    voices: list[Voice]
    fallback_voice_id: str

    def list_all(self) -> list[Voice]:
        return list(self.voices)

    def list_narrator_eligible(self) -> list[Voice]:
        return [voice for voice in self.voices if voice.selectable_for_narrator]

    def list_user_selectable(self, narrator_voice_id: str | None = None) -> list[Voice]:
        voices = [voice for voice in self.voices if voice.selectable_for_users]
        if narrator_voice_id:
            filtered = [voice for voice in voices if voice.voice_id != narrator_voice_id]
            if filtered:
                return filtered
        return voices

    def get(self, voice_id: str) -> Voice | None:
        for voice in self.voices:
            if voice.voice_id == voice_id:
                return voice
        return None

    def is_valid(self, voice_id: str) -> bool:
        return self.get(voice_id) is not None

    def resolve_user_voice(self, requested_voice_id: str | None, narrator_voice_id: str | None) -> str:
        if requested_voice_id and self.is_valid(requested_voice_id) and requested_voice_id != narrator_voice_id:
            return requested_voice_id
        selectable = self.list_user_selectable(narrator_voice_id)
        if selectable:
            if self.get(self.fallback_voice_id) and self.fallback_voice_id != narrator_voice_id:
                return self.fallback_voice_id
            return selectable[0].voice_id
        narrator_fallback = self.get(narrator_voice_id) if narrator_voice_id else None
        if narrator_fallback is not None:
            return narrator_fallback.voice_id
        return self.fallback_voice_id

    def resolve_narrator_voice(self, configured_voice_id: str | None) -> str:
        if configured_voice_id and self.is_valid(configured_voice_id):
            return configured_voice_id
        eligible = self.list_narrator_eligible()
        if eligible:
            return eligible[0].voice_id
        return self.fallback_voice_id
