from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import create_api_app
from domain.services import start_session
from audio.generated_audio import GeneratedAudio


def _client(services):
    return TestClient(create_api_app(services))


def test_settings_get_update_works(services):
    client = _client(services)

    response = client.get("/api/settings/42")
    assert response.status_code == 200
    assert response.json()["guild_id"] == 42

    update = client.put(
        "/api/settings/42",
        headers={"X-API-Key": services.settings.api_key},
        json={"narrator_voice_id": "en_us_002", "same_vc_only": False},
    )
    assert update.status_code == 200
    payload = update.json()
    assert payload["narrator_voice_id"] == "en_us_002"
    assert payload["same_vc_only"] is False


def test_index_page_lists_known_guilds(services):
    client = _client(services)
    client.get("/api/settings/42")
    client.get("/api/settings/99")
    response = client.get("/")
    assert response.status_code == 200
    assert "/settings/42" in response.text
    assert "/settings/99" in response.text


def test_api_key_auth_required_for_mutation(services):
    client = _client(services)
    response = client.put("/api/settings/42", json={"same_vc_only": False})
    assert response.status_code == 401


def test_synthesize_endpoint_returns_audio_metadata(services, monkeypatch):
    async def fake_synthesize(text: str, voice_id: str, *, max_seconds: int):
        path = services.settings.temp_audio_dir / "sample.mp3"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-mp3")
        return GeneratedAudio(path=path, content_type="audio/mpeg", voice_id=voice_id, text=text)

    monkeypatch.setattr(services.tts_provider, "synthesize", fake_synthesize)
    client = _client(services)
    response = client.post(
        "/api/synthesize",
        headers={"X-API-Key": services.settings.api_key},
        json={"text": "Hello from API", "voice_id": "en_us_001", "max_seconds": 20, "download": False},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["voice_id"] == "en_us_001"
    assert payload["audio_url"].endswith(f"/audio/{payload['file_id']}")

    audio_response = client.get(f"/audio/{payload['file_id']}")
    assert audio_response.status_code == 200
    assert audio_response.content == b"fake-mp3"


def test_obs_websocket_broadcast_works(services, monkeypatch):
    async def fake_synthesize(text: str, voice_id: str, *, max_seconds: int):
        path = services.settings.temp_audio_dir / "announce.mp3"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"announce")
        return GeneratedAudio(path=path, content_type="audio/mpeg", voice_id=voice_id, text=text)

    monkeypatch.setattr(services.tts_provider, "synthesize", fake_synthesize)
    client = _client(services)

    with client.websocket_connect("/ws/obs") as websocket:
        response = client.post(
            "/api/announce",
            headers={"X-API-Key": services.settings.api_key},
            json={"text": "Stream starting", "voice_id": "en_us_001", "target": "obs"},
        )
        assert response.status_code == 200
        event = websocket.receive_json()
        assert event["type"] == "announcement"
        assert event["text"] == "Stream starting"
        assert event["audio_url"].startswith("/audio/")


def test_disabling_narration_ends_active_session_immediately(services):
    client = _client(services)
    state = services.runtime_states.get(55)
    start_session(state, voice_channel_id=777, text_channel_id=888)
    state.currently_connected = True

    response = client.put(
        "/api/settings/55",
        headers={"X-API-Key": services.settings.api_key},
        json={"narration_enabled": False},
    )

    assert response.status_code == 200
    assert services.runtime_states.get(55).active_voice_channel_id is None
    assert services.runtime_states.get(55).currently_connected is False
