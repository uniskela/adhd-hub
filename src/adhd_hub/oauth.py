"""MCP OAuth 2.1 discovery, store, and /api/oauth/* HTTP handlers.

Authorize / token / register sit under `/api/oauth/` so the Hub UI cookie
(`COOKIE_NAME`, path=/api) is sent. Access tokens authorize `/mcp` only.
"""

from __future__ import annotations

import hashlib
import html
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from adhd_hub.auth import COOKIE_NAME, LoginThrottle, require_browser_request
from adhd_hub.config import Settings
from adhd_hub.connect_auth import verify_pkce
from adhd_hub.sessions import BrowserSessions

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

AUTH_CODE_SECONDS = 10 * 60
ACCESS_TOKEN_SECONDS = 7 * 24 * 60 * 60
MAX_OAUTH_CLIENTS = 64
MAX_OAUTH_AUTH_CODES = 64
MAX_OAUTH_ACCESS_TOKENS = 64
OAUTH_TOKEN_PREFIX = "ahoauth_"
MAX_REDIRECT_URIS = 8
MAX_REDIRECT_URI_LEN = 512
MAX_CLIENT_NAME_LEN = 128
MAX_CODE_CHALLENGE_LEN = 128
MIN_CODE_CHALLENGE_LEN = 43

# Static public clients for common MCP desktop loopback callbacks (DCR still preferred).
SEED_CLIENTS: tuple[dict[str, Any], ...] = (
    {
        "client_id": "cursor-mcp",
        "client_name": "Cursor MCP",
        "redirect_uris": [
            "http://127.0.0.1:3334/callback",
            "http://localhost:3334/callback",
            "http://127.0.0.1:8787/callback",
            "http://localhost:8787/callback",
        ],
    },
)


def _sha256_hex(value: str) -> str:
    """SHA-256 hex digest for high-entropy opaque secrets (lookup keys, not a password KDF)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _access_token_digest(token: str) -> str | None:
    """Hash only the random secret after ``OAUTH_TOKEN_PREFIX`` (prefix is not secret material)."""
    if not token.startswith(OAUTH_TOKEN_PREFIX):
        return None
    secret = token[len(OAUTH_TOKEN_PREFIX) :]
    if not secret:
        return None
    return _sha256_hex(secret)


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


def is_allowed_redirect_uri(uri: str) -> bool:
    """Exact-match candidate policy: HTTPS any host, or HTTP loopback with port."""
    if not uri or not isinstance(uri, str) or len(uri) > MAX_REDIRECT_URI_LEN:
        return False
    if any(ch.isspace() for ch in uri) or "*" in uri:
        return False
    try:
        parsed = urlparse(uri.strip())
    except ValueError:
        return False
    if parsed.scheme not in {"https", "http"}:
        return False
    if parsed.username or parsed.password or parsed.fragment:
        return False
    if not parsed.netloc or not parsed.hostname:
        return False
    try:
        # Reject malformed ports (urlparse may leave port None or raise).
        _ = parsed.port
    except ValueError:
        return False
    host = parsed.hostname.lower().strip("[]")
    if parsed.scheme == "https":
        return True
    if not is_loopback_host(host):
        return False
    # HTTP loopback requires an explicit port (OAuth native clients).
    return parsed.port is not None and 1 <= parsed.port <= 65535


def is_safe_oauth_return_path(value: str | None) -> bool:
    """Allow only relative `/api/oauth/authorize?...` return paths (no open redirect)."""
    if not value or not isinstance(value, str):
        return False
    if len(value) > 2048 or "\\" in value or value.startswith("//"):
        return False
    # Resolve as a same-document relative URL against a throwaway origin so
    # scheme tricks (javascript:, vbscript:, etc.) cannot pass a bare path check.
    try:
        parsed = urlparse(value, scheme="https")
        if parsed.scheme and parsed.scheme.lower() not in {"", "https", "http"}:
            return False
        if parsed.netloc or parsed.username or parsed.password or parsed.fragment:
            return False
        if parsed.path != "/api/oauth/authorize":
            return False
        if ".." in parsed.path:
            return False
        return True
    except ValueError:
        return False


def append_query_params(uri: str, params: dict[str, str]) -> str:
    """Merge query params via URL parsing (never string-concat secrets carelessly)."""
    parsed = urlparse(uri)
    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    existing.update({k: v for k, v in params.items() if v is not None})
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(existing),
            "",  # never carry fragment into redirect
        )
    )


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


def _oauth_error(status: int, code: str) -> JSONResponse:
    return JSONResponse(
        {"error": code},
        status_code=status,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _consent_headers() -> dict[str, str]:
    return {
        "Content-Security-Policy": (
            "default-src 'none'; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; form-action 'self'; "
            "base-uri 'none'; frame-ancestors 'none'"
        ),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
    }


def _render_consent_page(
    *,
    client_name: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str,
    resource: str,
    response_type: str,
) -> HTMLResponse:
    safe_name = html.escape(client_name or "application", quote=True)
    fields = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "state": state or "",
        "resource": resource,
        "response_type": response_type,
    }
    hidden = "\n".join(
        f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v, quote=True)}">'
        for k, v in fields.items()
    )
    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Authorize MCP access — ADHD Hub</title>
<style>
  :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
  body {{ margin: 0; min-height: 100dvh; display: grid; place-items: center;
         background: #0f1419; color: #e8eef4; }}
  main {{ width: min(28rem, 92vw); padding: 1.75rem; border-radius: 16px;
         background: #1a222c; border: 1px solid #2c3846; }}
  h1 {{ font-size: 1.35rem; margin: 0 0 .75rem; font-weight: 600; }}
  p {{ color: #a8b3bf; line-height: 1.45; margin: 0 0 1.25rem; }}
  .actions {{ display: flex; gap: .75rem; flex-wrap: wrap; }}
  button {{ flex: 1; min-width: 7rem; padding: .7rem 1rem; border-radius: 10px;
           border: 0; font: inherit; font-weight: 600; cursor: pointer; }}
  .allow {{ background: #3d8bfd; color: #061018; }}
  .deny {{ background: transparent; color: #e8eef4; border: 1px solid #3a4654; }}
  .err {{ color: #ff8e8e; margin-top: 1rem; display: none; }}
</style>
</head>
<body>
<main>
  <h1>Allow MCP access?</h1>
  <p><strong>{safe_name}</strong> wants a Hub token for MCP tools on this server.
     Allow only if you started this from your coding agent.</p>
  <form id="consent" method="post" action="/api/oauth/authorize">
    {hidden}
    <div class="actions">
      <button type="submit" name="decision" value="allow" class="allow">Allow</button>
      <button type="submit" name="decision" value="deny" class="deny">Deny</button>
    </div>
    <p class="err" id="err" role="alert"></p>
  </form>
</main>
<script>
(function () {{
  var form = document.getElementById("consent");
  var err = document.getElementById("err");
  form.addEventListener("submit", function (ev) {{
    ev.preventDefault();
    var submitter = ev.submitter;
    var decision = (submitter && submitter.value) || "deny";
    var body = new URLSearchParams(new FormData(form));
    body.set("decision", decision);
    err.style.display = "none";
    fetch("/api/oauth/authorize", {{
      method: "POST",
      headers: {{
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Hub-Request": "1"
      }},
      body: body.toString(),
      redirect: "manual",
      credentials: "same-origin"
    }}).then(function (res) {{
      var loc = res.headers.get("Location");
      if (loc) {{ window.location = loc; return; }}
      if (res.status >= 300 && res.status < 400) {{
        err.textContent = "Redirect missing from response.";
        err.style.display = "block";
        return;
      }}
      return res.json().then(function (data) {{
        if (data && data.redirect) {{ window.location = data.redirect; return; }}
        err.textContent = (data && (data.error || data.detail)) || ("Request failed (" + res.status + ")");
        err.style.display = "block";
      }}).catch(function () {{
        err.textContent = "Request failed (" + res.status + ")";
        err.style.display = "block";
      }});
    }}).catch(function () {{
      err.textContent = "Could not reach the Hub.";
      err.style.display = "block";
    }});
  }});
}})();
</script>
</body>
</html>
"""
    return HTMLResponse(body, headers=_consent_headers())


class OAuthStore:
    """SQLite OAuth clients, auth codes, and access tokens (hashed at rest).

    Shares the ConnectStore database file (`connect.sqlite3`) with separate tables.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else None
        if self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self.ensure_seed_clients()

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

    def ensure_seed_clients(self) -> None:
        now = time.time()
        with self._connect() as conn:
            for seed in SEED_CLIENTS:
                uris = [u for u in seed["redirect_uris"] if is_allowed_redirect_uri(u)]
                if not uris:
                    continue
                row = conn.execute(
                    "SELECT client_id FROM oauth_clients WHERE client_id = ?",
                    (seed["client_id"],),
                ).fetchone()
                if row is None:
                    conn.execute(
                        """
                        INSERT INTO oauth_clients (client_id, client_name, redirect_uris, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (seed["client_id"], seed["client_name"], json.dumps(uris), now),
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
            seed_ids = tuple(seed["client_id"] for seed in SEED_CLIENTS)
            placeholders = ",".join("?" for _ in seed_ids) or "''"
            conn.execute(
                f"""
                DELETE FROM oauth_clients WHERE client_id IN (
                    SELECT client_id FROM oauth_clients
                    WHERE client_id NOT IN ({placeholders})
                    ORDER BY created_at ASC
                    LIMIT ?
                )
                """,
                (*seed_ids, overflow),
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
        client_id: str | None = None,
    ) -> dict[str, Any]:
        name = (client_name or "").strip() or "client"
        if len(name) > MAX_CLIENT_NAME_LEN:
            raise ValueError("client_name too long")
        uris = [u.strip() for u in redirect_uris if isinstance(u, str) and u.strip()]
        if not uris:
            raise ValueError("redirect_uris required")
        if len(uris) > MAX_REDIRECT_URIS:
            raise ValueError("too many redirect_uris")
        for uri in uris:
            if not is_allowed_redirect_uri(uri):
                raise ValueError("invalid_redirect_uri")
        cid = client_id or secrets.token_urlsafe(24)
        now = time.time()
        with self._connect() as conn:
            self._purge(conn)
            conn.execute(
                """
                INSERT INTO oauth_clients (client_id, client_name, redirect_uris, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (cid, name, json.dumps(uris), now),
            )
        return {
            "client_id": cid,
            "client_name": name,
            "redirect_uris": uris,
            "token_endpoint_auth_method": "none",
            "client_id_issued_at": int(now),
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
        secret = secrets.token_urlsafe(32)
        token = OAUTH_TOKEN_PREFIX + secret
        token_hash = _sha256_hex(secret)
        now = time.time()
        with self._connect() as conn:
            self._purge(conn)
            conn.execute(
                """
                INSERT INTO oauth_access_tokens (
                    token_hash, client_id, resource, created_at, expires_at, last_used_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (token_hash, client_id, resource, now, now + ACCESS_TOKEN_SECONDS, now),
            )
        return token

    def valid_access_token(self, token: str | None) -> bool:
        token_hash = _access_token_digest(token or "")
        if token_hash is None:
            return False
        now = time.time()
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
        token_hash = _access_token_digest(token)
        if token_hash is None:
            return
        with self._connect() as conn:
            conn.execute(
                "UPDATE oauth_access_tokens SET expires_at = 0 WHERE token_hash = ?",
                (token_hash,),
            )


def _parse_authorize_params(source: Any) -> dict[str, str]:
    def get(name: str) -> str:
        if hasattr(source, "getlist"):
            values = source.getlist(name)
            raw = values[0] if values else ""
        else:
            raw = source.get(name, "") if hasattr(source, "get") else ""
        return (raw or "").strip() if isinstance(raw, str) else ""

    return {
        "response_type": get("response_type"),
        "client_id": get("client_id"),
        "redirect_uri": get("redirect_uri"),
        "code_challenge": get("code_challenge"),
        "code_challenge_method": get("code_challenge_method") or "S256",
        "state": get("state"),
        "resource": get("resource"),
        "decision": get("decision"),
    }


def _validate_authorize_request(
    store: OAuthStore,
    settings: Settings,
    request: Request,
    params: dict[str, str],
) -> tuple[dict[str, Any], str] | JSONResponse | HTMLResponse:
    """Return (client, canonical_resource) or an error response (never unsafe redirect)."""
    issuer = issuer_base(settings, request)
    if not issuer:
        return JSONResponse({"error": "server_error", "error_description": "issuer unavailable"}, 503)

    client_id = params["client_id"]
    redirect_uri = params["redirect_uri"]
    response_type = params["response_type"]
    challenge = params["code_challenge"]
    method = params["code_challenge_method"]
    resource = params["resource"]

    client = store.get_client(client_id) if client_id else None
    redirect_ok = (
        client is not None
        and redirect_uri in client["redirect_uris"]
        and is_allowed_redirect_uri(redirect_uri)
    )

    def reject(code: str, status: int = 400) -> JSONResponse:
        return JSONResponse({"error": code}, status_code=status)

    if response_type != "code":
        return reject("unsupported_response_type")
    if not client:
        return reject("invalid_client")
    if not redirect_ok:
        # Never redirect to an unvalidated redirect_uri.
        return reject("invalid_redirect_uri")
    if method != "S256":
        return reject("invalid_request")
    if not (
        MIN_CODE_CHALLENGE_LEN <= len(challenge) <= MAX_CODE_CHALLENGE_LEN
        and challenge.replace("-", "").replace("_", "").isalnum()
    ):
        return reject("invalid_request")
    expected_resource = f"{issuer}/mcp"
    if resource != expected_resource:
        return reject("invalid_target")
    return client, expected_resource


def build_oauth_router(
    settings: Settings,
    sessions: BrowserSessions | None = None,
    oauth_store: OAuthStore | None = None,
) -> APIRouter:
    """Well-known discovery + /api/oauth/* authorize, token, register."""
    router = APIRouter(tags=["oauth"])

    if not settings.oauth_enabled:
        return router

    store = oauth_store or OAuthStore()
    throttle = LoginThrottle()

    def client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    @router.get("/.well-known/oauth-protected-resource")
    def oauth_protected_resource(request: Request) -> JSONResponse:
        return JSONResponse(protected_resource_metadata(settings, request))

    @router.get("/.well-known/oauth-protected-resource/mcp")
    def oauth_protected_resource_mcp(request: Request) -> JSONResponse:
        return JSONResponse(protected_resource_metadata(settings, request))

    @router.get("/.well-known/oauth-authorization-server")
    def oauth_authorization_server(request: Request) -> JSONResponse:
        return JSONResponse(authorization_server_metadata(settings, request))

    if sessions is None:
        return router

    @router.get("/api/oauth/authorize")
    async def authorize_get(request: Request) -> Response:
        params = _parse_authorize_params(request.query_params)
        validated = _validate_authorize_request(store, settings, request, params)
        if not isinstance(validated, tuple):
            return validated
        client, _resource = validated

        if not sessions.valid(request.cookies.get(COOKIE_NAME)):
            return_path = request.url.path
            if request.url.query:
                return_path = f"{return_path}?{request.url.query}"
            if not is_safe_oauth_return_path(return_path):
                return JSONResponse({"error": "invalid_request"}, status_code=400)
            login = f"/ui/?oauth_return={quote(return_path, safe='')}"
            return RedirectResponse(url=login, status_code=302)

        return _render_consent_page(
            client_name=str(client.get("client_name") or "application"),
            client_id=params["client_id"],
            redirect_uri=params["redirect_uri"],
            code_challenge=params["code_challenge"],
            code_challenge_method=params["code_challenge_method"],
            state=params["state"],
            resource=params["resource"],
            response_type=params["response_type"],
        )

    @router.post("/api/oauth/authorize")
    async def authorize_post(request: Request) -> Response:
        require_browser_request(request, settings)
        if not sessions.valid(request.cookies.get(COOKIE_NAME)):
            raise HTTPException(401, "Sign in to the Hub dashboard first")
        throttle.check(client_key(request))

        form = await request.form()
        params = _parse_authorize_params(form)
        validated = _validate_authorize_request(store, settings, request, params)
        if not isinstance(validated, tuple):
            return validated
        client, resource = validated
        redirect_uri = params["redirect_uri"]
        state = params["state"]
        decision = (params["decision"] or "").lower()

        if decision == "deny":
            target = append_query_params(
                redirect_uri,
                {"error": "access_denied", **({"state": state} if state else {})},
            )
            return RedirectResponse(url=target, status_code=302)

        if decision != "allow":
            return JSONResponse({"error": "invalid_request"}, status_code=400)

        try:
            code = store.create_auth_code(
                client_id=client["client_id"],
                redirect_uri=redirect_uri,
                resource=resource,
                code_challenge=params["code_challenge"],
                code_challenge_method="S256",
            )
        except (KeyError, PermissionError, ValueError):
            return JSONResponse({"error": "invalid_request"}, status_code=400)

        target = append_query_params(
            redirect_uri,
            {"code": code, **({"state": state} if state else {})},
        )
        return RedirectResponse(url=target, status_code=302)

    @router.post("/api/oauth/token")
    async def token_post(request: Request) -> Response:
        throttle.check(client_key(request))
        content_type = (request.headers.get("content-type") or "").lower()
        if "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            data = {k: str(v) for k, v in form.items()}
        elif "application/json" in content_type:
            try:
                payload = await request.json()
            except Exception:
                return _oauth_error(400, "invalid_request")
            if not isinstance(payload, dict):
                return _oauth_error(400, "invalid_request")
            data = {str(k): str(v) for k, v in payload.items() if v is not None}
        else:
            # Spec requires form-urlencoded; reject other types.
            return _oauth_error(400, "invalid_request")

        grant_type = (data.get("grant_type") or "").strip()
        if grant_type != "authorization_code":
            return _oauth_error(400, "unsupported_grant_type")

        code = (data.get("code") or "").strip()
        redirect_uri = (data.get("redirect_uri") or "").strip()
        client_id = (data.get("client_id") or "").strip()
        verifier = (data.get("code_verifier") or "").strip()
        resource = (data.get("resource") or "").strip()
        issuer = issuer_base(settings, request)
        if not issuer:
            return _oauth_error(503, "server_error")
        expected_resource = f"{issuer}/mcp"
        if not resource:
            resource = expected_resource
        if resource != expected_resource:
            return _oauth_error(400, "invalid_target")
        if store.get_client(client_id) is None:
            return _oauth_error(401, "invalid_client")

        consumed = store.consume_auth_code(
            code=code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            resource=resource,
            code_verifier=verifier,
        )
        if consumed is None:
            return _oauth_error(400, "invalid_grant")

        try:
            access = store.issue_access_token(client_id=client_id, resource=resource)
        except (KeyError, ValueError):
            return _oauth_error(400, "invalid_grant")

        return JSONResponse(
            {
                "access_token": access,
                "token_type": "Bearer",
                "expires_in": ACCESS_TOKEN_SECONDS,
            },
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    @router.post("/api/oauth/register")
    async def register_post(request: Request) -> Response:
        throttle.check(client_key(request))
        try:
            payload = await request.json()
        except Exception:
            return _oauth_error(400, "invalid_client_metadata")
        if not isinstance(payload, dict):
            return _oauth_error(400, "invalid_client_metadata")

        # Bound metadata size lightly.
        raw = json.dumps(payload)
        if len(raw) > 8192:
            return _oauth_error(400, "invalid_client_metadata")

        auth_method = (payload.get("token_endpoint_auth_method") or "none").strip()
        if auth_method != "none":
            return _oauth_error(400, "invalid_client_metadata")

        client_name = payload.get("client_name") or "client"
        if not isinstance(client_name, str) or len(client_name) > MAX_CLIENT_NAME_LEN:
            return _oauth_error(400, "invalid_client_metadata")

        redirect_uris = payload.get("redirect_uris")
        if not isinstance(redirect_uris, list) or not redirect_uris:
            return _oauth_error(400, "invalid_redirect_uri")
        if len(redirect_uris) > MAX_REDIRECT_URIS:
            return _oauth_error(400, "invalid_redirect_uri")
        if not all(isinstance(u, str) and is_allowed_redirect_uri(u) for u in redirect_uris):
            return _oauth_error(400, "invalid_redirect_uri")

        try:
            created = store.register_client(
                client_name=client_name,
                redirect_uris=list(redirect_uris),
            )
        except ValueError as exc:
            code = str(exc)
            if code == "invalid_redirect_uri":
                return _oauth_error(400, "invalid_redirect_uri")
            return _oauth_error(400, "invalid_client_metadata")

        body = {
            "client_id": created["client_id"],
            "client_id_issued_at": created["client_id_issued_at"],
            "client_name": created["client_name"],
            "redirect_uris": created["redirect_uris"],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
        }
        return JSONResponse(body, status_code=201)

    return router
