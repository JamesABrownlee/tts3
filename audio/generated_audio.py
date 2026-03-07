"""Generated audio payloads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class GeneratedAudio:
    path: Path
    content_type: str
    voice_id: str
    text: str

