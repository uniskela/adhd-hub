from __future__ import annotations

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from adhd_hub.config import Settings

_bearer = HTTPBearer(auto_error=False)


def require_auth(
    settings: Settings,
    credentials: HTTPAuthorizationCredentials | None,
) -> None:
    expected = settings.auth_token
    # Dev-friendly: allow unauthenticated access only while token is still default.
    if (not expected or expected == "change-me") and credentials is None:
        return
    if credentials is None or credentials.credentials != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def auth_dependency(settings: Settings):
    async def _dep(
        credentials: HTTPAuthorizationCredentials | None = Security(_bearer),  # noqa: B008
    ) -> None:
        require_auth(settings, credentials)

    return _dep
