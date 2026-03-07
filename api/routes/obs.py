"""OBS/browser player routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from api.dependencies import get_services
from app.services import ServiceContainer


router = APIRouter()


@router.get("/obs/player", response_class=HTMLResponse)
async def obs_player_page() -> HTMLResponse:
    html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>OBS TTS Player</title>
  <style>
    body { font-family: sans-serif; margin: 0; padding: 1rem; background: #111; color: #eee; }
    #status { font-size: 1rem; }
    #details { margin-top: 0.5rem; color: #aaa; }
  </style>
</head>
<body>
  <div id="status">Waiting for announcements...</div>
  <div id="details">Add this page as an OBS Browser Source. Browser autoplay settings may require interaction in some environments.</div>
  <audio id="player" autoplay></audio>
  <script>
    const status = document.getElementById('status');
    const player = document.getElementById('player');
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const socket = new WebSocket(`${scheme}://${window.location.host}/ws/obs`);
    socket.onopen = () => { status.textContent = 'Connected. Waiting for announcements...'; };
    socket.onclose = () => { status.textContent = 'Disconnected from announcement server.'; };
    socket.onmessage = async (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type !== 'announcement') {
        return;
      }
      status.textContent = `Playing: ${payload.text}`;
      player.src = payload.audio_url;
      try {
        await player.play();
      } catch (error) {
        status.textContent = `Autoplay blocked: ${error}`;
      }
    };
  </script>
</body>
</html>
"""
    return HTMLResponse(html)


@router.websocket("/ws/obs")
async def obs_socket(websocket: WebSocket, services: ServiceContainer = Depends(get_services)) -> None:
    await services.obs_broker.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await services.obs_broker.disconnect(websocket)
