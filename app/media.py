"""Temporary audio storage for API and OBS consumers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import time
from uuid import uuid4

from audio.generated_audio import GeneratedAudio


@dataclass(slots=True, frozen=True)
class StoredAudio:
    file_id: str
    path: Path
    content_type: str
    created_at: float
    voice_id: str
    text: str


class TempAudioStore:
    def __init__(self, root: Path, *, ttl_seconds: int) -> None:
        self.root = root
        self.ttl_seconds = ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)
        self._files: dict[str, StoredAudio] = {}

    async def store_generated(self, generated: GeneratedAudio) -> StoredAudio:
        self.cleanup_expired()
        file_id = uuid4().hex
        destination = self.root / f"{file_id}{generated.path.suffix or '.mp3'}"
        generated.path.replace(destination)
        stored = StoredAudio(
            file_id=file_id,
            path=destination,
            content_type=generated.content_type,
            created_at=time(),
            voice_id=generated.voice_id,
            text=generated.text,
        )
        self._files[file_id] = stored
        return stored

    def get(self, file_id: str) -> StoredAudio | None:
        self.cleanup_expired()
        stored = self._files.get(file_id)
        if stored is None or not stored.path.exists():
            self._files.pop(file_id, None)
            return None
        return stored

    def cleanup_expired(self) -> None:
        now = time()
        expired = [file_id for file_id, stored in self._files.items() if now - stored.created_at > self.ttl_seconds or not stored.path.exists()]
        for file_id in expired:
            stored = self._files.pop(file_id, None)
            if stored is not None:
                stored.path.unlink(missing_ok=True)
