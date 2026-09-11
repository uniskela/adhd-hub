"""MCP OAuth 2.1 discovery metadata, store, and challenge helpers.

Authorize / token / register HTTP handlers land in a later task; this module
advertises endpoints, shapes the MCP 401 WWW-Authenticate challenge, and
persists OAuth clients / auth codes / access tokens (hashed) in connect.sqlite3.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from adhd_hub.config import Settings
from adhd_hub.connect_auth import verify_pkce

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

AUTH_CODE_SECONDS = 10 * 60
ACCESS_TOKEN_SECONDS = 7 * 24 * 60 * 60
MAX_OAUTH_CLIENTS = 64
MAX_OAUTH_AUTH_CODES = 64
MAX_OAUTH_ACCESS_TOKENS = 64
OAUTH_TOKEN_PREFIX = "ahoauth_"


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


class OAuthStore:
    """SQLite OAuth clients, auth codes, and access tokens (hashed at rest).

    Shares the ConnectStore database file (`connect.sqlite3`) with separate tables.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else None
        if self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:
            conn = sqlite3.connect(
                "file:adhd_hub_oauth?mode=memory&cache=shared",
                uri=True,
                timeout=30,
            )
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_clients (
                    client_id TEXT PRIMARY KEY,
                    client_name TEXT NOT NULL,
                    redirect_uris TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_auth_codes (
                    code_hash TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    code_challenge TEXT NOT NULL,
                    code_challenge_method TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    used_at REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_oauth_auth_codes_expires "
                "ON oauth_auth_codes(expires_at)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_access_tokens (
                    token_hash TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    last_used_at REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_oauth_access_tokens_expires "
                "ON oauth_access_tokens(expires_at)"
            )

    def _purge(self, conn: sqlite3.Connection) -> None:
        now = time.time()
        conn.execute("DELETE FROM oauth_auth_codes WHERE expires_at <= ?", (now,))
        conn.execute(
            "DELETE FROM oauth_auth_codes WHERE used_at IS NOT NULL AND used_at <= ?",
            (now - AUTH_CODE_SECONDS,),
        )
        conn.execute("DELETE FROM oauth_access_tokens WHERE expires_at <= ?", (now,))

        client_count = int(conn.execute("SELECT COUNT(*) AS c FROM oauth_clients").fetchone()["c"])
        if client_count > MAX_OAUTH_CLIENTS:
            overflow = client_count - MAX_OAUTH_CLIENTS
            conn.execute(
                """
                DELETE FROM oauth_clients WHERE client_id IN (
                    SELECT client_id FROM oauth_clients
                    ORDER BY created_at ASC
                    LIMIT ?
                )
                """,
                (overflow,),
            )

        code_count = int(conn.execute("SELECT COUNT(*) AS c FROM oauth_auth_codes").fetchone()["c"])
        if code_count > MAX_OAUTH_AUTH_CODES:
            overflow = code_count - MAX_OAUTH_AUTH_CODES
            conn.execute(
                """
                DELETE FROM oauth_auth_codes WHERE code_hash IN (
                    SELECT code_hash FROM oauth_auth_codes
                    ORDER BY created_at ASC
                    LIMIT ?
                )
                """,
                (overflow,),
            )

        token_count = int(
            conn.execute("SELECT COUNT(*) AS c FROM oauth_access_tokens").fetchone()["c"]
        )
        if token_count > MAX_OAUTH_ACCESS_TOKENS:
            overflow = token_count - MAX_OAUTH_ACCESS_TOKENS
            conn.execute(
                """
                DELETE FROM oauth_access_tokens WHERE token_hash IN (
                    SELECT token_hash FROM oauth_access_tokens
                    ORDER BY created_at ASC
                    LIMIT ?
                )
                """,
                (overflow,),
            )

    def register_client(
        self,
        *,
        client_name: str,
        redirect_uris: list[str],
    ) -> dict[str, Any]:
        name = (client_name or "").strip() or "client"
        uris = [u.strip() for u in redirect_uris if isinstance(u, str) and u.strip()]
        if not uris:
            raise ValueError("redirect_uris required")
        client_id = secrets.token_urlsafe(24)
        now = time.time()
        with self._connect() as conn:
            self._purge(conn)
            conn.execute(
                """
                INSERT INTO oauth_clients (client_id, client_name, redirect_uris, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (client_id, name, json.dumps(uris), now),
            )
        return {
            "client_id": client_id,
            "client_name": name,
            "redirect_uris": uris,
            "token_endpoint_auth_method": "none",
        }

    def get_client(self, client_id: str) -> dict[str, Any] | None:
        if not client_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT client_id, client_name, redirect_uris, created_at "
                "FROM oauth_clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "client_id": row["client_id"],
                "client_name": row["client_name"],
                "redirect_uris": json.loads(row["redirect_uris"]),
                "created_at": float(row["created_at"]),
            }

    def create_auth_code(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        resource: str,
        code_challenge: str,
        code_challenge_method: str = "S256",
    ) -> str:
        if code_challenge_method != "S256":
            raise ValueError("only S256 PKCE is supported")
        client = self.get_client(client_id)
        if client is None:
            raise KeyError("invalid_client")
        if redirect_uri not in client["redirect_uris"]:
            raise PermissionError("invalid_redirect_uri")
        if not resource or not code_challenge:
            raise ValueError("resource and code_challenge required")

        raw_code = secrets.token_urlsafe(32)
        now = time.time()
        with self._connect() as conn:
            self._purge(conn)
            conn.execute(
                """
                INSERT INTO oauth_auth_codes (
                    code_hash, client_id, redirect_uri, resource,
                    code_challenge, code_challenge_method,
                    expires_at, created_at, used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    _sha256_hex(raw_code),
                    client_id,
                    redirect_uri,
                    resource,
                    code_challenge,
                    code_challenge_method,
                    now + AUTH_CODE_SECONDS,
                    now,
                ),
            )
        return raw_code

    def consume_auth_code(
        self,
        *,
        code: str,
        client_id: str,
        redirect_uri: str,
        resource: str,
        code_verifier: str,
    ) -> dict[str, Any] | None:
        if not code or not client_id or not redirect_uri or not resource or not code_verifier:
            return None
        code_hash = _sha256_hex(code)
        now = time.time()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            self._purge(conn)
            row = conn.execute(
                "SELECT * FROM oauth_auth_codes WHERE code_hash = ?",
                (code_hash,),
            ).fetchone()
            if row is None:
                conn.rollback()
                return None
            if row["used_at"] is not None:
                conn.rollback()
                return None
            if float(row["expires_at"]) <= now:
                conn.execute("DELETE FROM oauth_auth_codes WHERE code_hash = ?", (code_hash,))
                conn.commit()
                return None
            if (
                row["client_id"] != client_id
                or row["redirect_uri"] != redirect_uri
                or row["resource"] != resource
            ):
                conn.rollback()
                return None
            if row["code_challenge_method"] != "S256":
                conn.rollback()
                return None
            if not verify_pkce(code_verifier, row["code_challenge"]):
                conn.rollback()
                return None
            cur = conn.execute(
                """
                UPDATE oauth_auth_codes
                SET used_at = ?
                WHERE code_hash = ? AND used_at IS NULL
                """,
                (now, code_hash),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return None
            conn.commit()
            return {
                "client_id": row["client_id"],
                "redirect_uri": row["redirect_uri"],
                "resource": row["resource"],
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def issue_access_token(self, *, client_id: str, resource: str) -> str:
        if not client_id or not resource:
            raise ValueError("client_id and resource required")
        if self.get_client(client_id) is None:
            raise KeyError("invalid_client")
        token = OAUTH_TOKEN_PREFIX + secrets.token_urlsafe(32)
        now = time.time()
        with self._connect() as conn:
            self._purge(conn)
            conn.execute(
                """
                INSERT INTO oauth_access_tokens (
                    token_hash, client_id, resource, created_at, expires_at, last_used_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (_sha256_hex(token), client_id, resource, now, now + ACCESS_TOKEN_SECONDS, now),
            )
        return token

    def valid_access_token(self, token: str | None) -> bool:
        if not token or not token.startswith(OAUTH_TOKEN_PREFIX):
            return False
        now = time.time()
        token_hash = _sha256_hex(token)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT token_hash, resource, expires_at FROM oauth_access_tokens "
                "WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return False
            if float(row["expires_at"]) <= now:
                conn.execute(
                    "DELETE FROM oauth_access_tokens WHERE token_hash = ?",
                    (token_hash,),
                )
                return False
            resource = str(row["resource"] or "")
            if not resource.endswith("/mcp"):
                return False
            conn.execute(
                "UPDATE oauth_access_tokens SET last_used_at = ? WHERE token_hash = ?",
                (now, token_hash),
            )
            return True

    def expire_access_token_now(self, token: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE oauth_access_tokens SET expires_at = 0 WHERE token_hash = ?",
                (_sha256_hex(token),),
            )


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
