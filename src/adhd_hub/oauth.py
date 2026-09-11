"""MCP OAuth 2.1 discovery metadata and challenge helpers.

Authorize / token / register handlers land in later tasks; this module only
advertises endpoints and shapes the MCP 401 WWW-Authenticate challenge.
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from adhd_hub.config import Settings

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    return host.lower().strip("[]") in _LOOPBACK_HOSTS


def is_valid_issuer_url(url: str) -> bool:
    """HTTPS anywhere, or HTTP only for loopback issuers."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"https", "http"}:
        return False
    if not parsed.netloc or parsed.path not in {"", "/"}:
        return False
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if parsed.scheme == "https":
        return True
    return is_loopback_host(host)


def issuer_base(settings: Settings, request: Request) -> str | None:
    """Canonical OAuth issuer (no trailing slash).

    Prefer configured public URL when valid. Fall back to the request base URL
    only when the request Host is loopback (never trust remote Host spoofing).
    """
    configured = settings.resolve_public_url()
    if configured and is_valid_issuer_url(configured):
        return configured.rstrip("/")

    request_base = str(request.base_url).rstrip("/")
    if is_loopback_host(_hostname(request_base)) and is_valid_issuer_url(request_base):
        return request_base
    return None


def protected_resource_metadata(settings: Settings, request: Request) -> dict:
    issuer = issuer_base(settings, request)
    if not issuer:
        raise HTTPException(status_code=503, detail="Public URL not configured")
    return {
        "resource": f"{issuer}/mcp",
        "authorization_servers": [issuer],
    }


def authorization_server_metadata(settings: Settings, request: Request) -> dict:
    issuer = issuer_base(settings, request)
    if not issuer:
        raise HTTPException(status_code=503, detail="Public URL not configured")
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/api/oauth/authorize",
        "token_endpoint": f"{issuer}/api/oauth/token",
        "registration_endpoint": f"{issuer}/api/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }


def resource_metadata_url(settings: Settings, request: Request) -> str | None:
    issuer = issuer_base(settings, request)
    if not issuer:
        return None
    return f"{issuer}/.well-known/oauth-protected-resource"


def www_authenticate_challenge(settings: Settings, request: Request) -> str:
    """401 WWW-Authenticate value for gated MCP paths."""
    if not settings.oauth_enabled:
        return "Bearer"
    prm = resource_metadata_url(settings, request)
    if not prm:
        return "Bearer"
    return f'Bearer realm="mcp", resource_metadata="{prm}"'


def build_oauth_router(settings: Settings) -> APIRouter:
    """Well-known discovery routes (and future /api/oauth/* stubs)."""
    router = APIRouter(tags=["oauth"])

    if not settings.oauth_enabled:
        return router

    @router.get("/.well-known/oauth-protected-resource")
    def oauth_protected_resource(request: Request) -> JSONResponse:
        return JSONResponse(protected_resource_metadata(settings, request))

    @router.get("/.well-known/oauth-protected-resource/mcp")
    def oauth_protected_resource_mcp(request: Request) -> JSONResponse:
        return JSONResponse(protected_resource_metadata(settings, request))

    @router.get("/.well-known/oauth-authorization-server")
    def oauth_authorization_server(request: Request) -> JSONResponse:
        return JSONResponse(authorization_server_metadata(settings, request))

    return router
