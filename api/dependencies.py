"""FastAPI dependencies."""

from __future__ import annotations

from fastapi import Header, HTTPException, Request, WebSocket, status
from starlette.requests import HTTPConnection

from app.services import ServiceContainer


def get_services(connection: HTTPConnection) -> ServiceContainer:
    return connection.app.state.services


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    settings = request.app.state.services.settings
    if not settings.api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="API key is not configured")
    if x_api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
