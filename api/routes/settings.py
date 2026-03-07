"""Settings API and web GUI routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from api.dependencies import get_services, require_api_key
from api.models import GuildSettingsResponse, GuildSettingsUpdateRequest, VoiceResponse
from app.guild_settings import update_guild_settings
from app.services import ServiceContainer


router = APIRouter()


def _settings_to_response(settings) -> GuildSettingsResponse:
    return GuildSettingsResponse(
        guild_id=settings.guild_id,
        allowed_text_channel_ids=settings.allowed_text_channel_ids,
        narrator_voice_id=settings.narrator_voice_id,
        fallback_user_voice_id=settings.fallback_user_voice_id,
        narration_enabled=settings.narration_enabled,
        welcome_enabled=settings.welcome_enabled,
        farewell_enabled=settings.farewell_enabled,
        announce_links=settings.announce_links,
        announce_images=settings.announce_images,
        announce_files=settings.announce_files,
        same_vc_only=settings.same_vc_only,
        intro_mode=settings.intro_mode,
        max_combined_audio_seconds=settings.max_combined_audio_seconds,
        idle_disconnect_seconds=settings.idle_disconnect_seconds,
    )


@router.get("/api/voices", response_model=list[VoiceResponse])
async def get_voices(services: ServiceContainer = Depends(get_services)) -> list[VoiceResponse]:
    voices = await services.tts_provider.list_voices()
    return [
        VoiceResponse(
            voice_id=voice.voice_id,
            display_name=voice.display_name,
            provider_name=voice.provider_name,
            selectable_for_users=voice.selectable_for_users,
            selectable_for_narrator=voice.selectable_for_narrator,
        )
        for voice in voices
    ]


@router.get("/api/settings/{guild_id}", response_model=GuildSettingsResponse)
async def get_settings(guild_id: int, services: ServiceContainer = Depends(get_services)) -> GuildSettingsResponse:
    settings = await services.guild_settings_repository.get(guild_id)
    return _settings_to_response(settings)


@router.put("/api/settings/{guild_id}", response_model=GuildSettingsResponse, dependencies=[Depends(require_api_key)])
async def update_settings(
    guild_id: int,
    payload: GuildSettingsUpdateRequest,
    services: ServiceContainer = Depends(get_services),
) -> GuildSettingsResponse:
    updates = payload.model_dump(exclude_unset=True)
    if "narrator_voice_id" in updates and updates["narrator_voice_id"] and not services.voice_catalog.is_valid(updates["narrator_voice_id"]):
        raise HTTPException(status_code=400, detail="Unknown narrator voice")
    if "fallback_user_voice_id" in updates and updates["fallback_user_voice_id"] and not services.voice_catalog.is_valid(updates["fallback_user_voice_id"]):
        raise HTTPException(status_code=400, detail="Unknown fallback user voice")
    updated = await update_guild_settings(services, guild_id, **updates)
    return _settings_to_response(updated)


@router.get("/settings/{guild_id}", response_class=HTMLResponse)
async def settings_page(guild_id: int, services: ServiceContainer = Depends(get_services)) -> HTMLResponse:
    voices = await services.tts_provider.list_voices()
    options = "\n".join(f'<option value="{voice.voice_id}">{voice.display_name} ({voice.voice_id})</option>' for voice in voices)
    html = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>TTS Settings</title>
  <style>
    body {{ font-family: sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }}
    label {{ display: block; margin: 0.75rem 0 0.25rem; }}
    input, select, textarea {{ width: 100%; padding: 0.5rem; box-sizing: border-box; }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
    .checks label {{ display: flex; gap: 0.5rem; align-items: center; }}
    #status {{ margin-top: 1rem; white-space: pre-wrap; }}
  </style>
</head>
<body>
  <h1>Guild {guild_id} Settings</h1>
  <label>API Key</label>
  <input id="apiKey" type="password" placeholder="Required to save changes" />
  <label>Narrator voice</label>
  <select id="narratorVoice"><option value="">Default</option>{options}</select>
  <label>Fallback user voice</label>
  <select id="fallbackVoice"><option value="">Default</option>{options}</select>
  <label>Allowed text channel IDs (comma separated)</label>
  <input id="channels" type="text" />
  <div class="row">
    <div>
      <label>Intro mode</label>
      <select id="introMode">
        <option value="always">always</option>
        <option value="on_change">on_change</option>
        <option value="first_only">first_only</option>
      </select>
    </div>
    <div>
      <label>Idle disconnect seconds</label>
      <input id="idleDisconnect" type="number" min="0" max="300" />
    </div>
  </div>
  <div class="row">
    <div>
      <label>Max combined audio seconds</label>
      <input id="maxSeconds" type="number" min="1" max="20" />
    </div>
  </div>
  <div class="checks">
    <label><input id="narrationEnabled" type="checkbox" /> Narration enabled</label>
    <label><input id="welcomeEnabled" type="checkbox" /> Welcome announcements</label>
    <label><input id="farewellEnabled" type="checkbox" /> Farewell announcements</label>
    <label><input id="announceLinks" type="checkbox" /> Announce links</label>
    <label><input id="announceImages" type="checkbox" /> Announce images</label>
    <label><input id="announceFiles" type="checkbox" /> Announce files</label>
    <label><input id="sameVcOnly" type="checkbox" /> Same VC only</label>
  </div>
  <button id="saveButton">Save</button>
  <div id="status"></div>
  <script>
    const guildId = window.location.pathname.split('/').filter(Boolean).pop();
    const status = document.getElementById('status');
    async function loadSettings() {{
      const response = await fetch(`/api/settings/${{guildId}}`);
      const data = await response.json();
      document.getElementById('narratorVoice').value = data.narrator_voice_id || '';
      document.getElementById('fallbackVoice').value = data.fallback_user_voice_id || '';
      document.getElementById('channels').value = data.allowed_text_channel_ids.join(', ');
      document.getElementById('introMode').value = data.intro_mode;
      document.getElementById('idleDisconnect').value = data.idle_disconnect_seconds;
      document.getElementById('maxSeconds').value = data.max_combined_audio_seconds;
      document.getElementById('narrationEnabled').checked = data.narration_enabled;
      document.getElementById('welcomeEnabled').checked = data.welcome_enabled;
      document.getElementById('farewellEnabled').checked = data.farewell_enabled;
      document.getElementById('announceLinks').checked = data.announce_links;
      document.getElementById('announceImages').checked = data.announce_images;
      document.getElementById('announceFiles').checked = data.announce_files;
      document.getElementById('sameVcOnly').checked = data.same_vc_only;
    }}
    document.getElementById('saveButton').addEventListener('click', async () => {{
      status.textContent = 'Saving...';
      const payload = {{
        narrator_voice_id: document.getElementById('narratorVoice').value || null,
        fallback_user_voice_id: document.getElementById('fallbackVoice').value || null,
        allowed_text_channel_ids: document.getElementById('channels').value.trim()
          ? document.getElementById('channels').value.split(',').map(v => Number(v.trim())).filter(Boolean)
          : [],
        intro_mode: document.getElementById('introMode').value,
        idle_disconnect_seconds: Number(document.getElementById('idleDisconnect').value),
        max_combined_audio_seconds: Number(document.getElementById('maxSeconds').value),
        narration_enabled: document.getElementById('narrationEnabled').checked,
        welcome_enabled: document.getElementById('welcomeEnabled').checked,
        farewell_enabled: document.getElementById('farewellEnabled').checked,
        announce_links: document.getElementById('announceLinks').checked,
        announce_images: document.getElementById('announceImages').checked,
        announce_files: document.getElementById('announceFiles').checked,
        same_vc_only: document.getElementById('sameVcOnly').checked
      }};
      const response = await fetch(`/api/settings/${{guildId}}`, {{
        method: 'PUT',
        headers: {{
          'Content-Type': 'application/json',
          'X-API-Key': document.getElementById('apiKey').value
        }},
        body: JSON.stringify(payload)
      }});
      const data = await response.json();
      status.textContent = response.ok ? 'Saved successfully.' : `Error: ${{data.detail || JSON.stringify(data)}}`;
    }});
    loadSettings().catch((error) => {{
      status.textContent = `Failed to load settings: ${{error}}`;
    }});
  </script>
</body>
</html>
"""
    return HTMLResponse(html)
