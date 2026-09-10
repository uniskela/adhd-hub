"""Short-lived CLI connect grants and revocable CLI session tokens.

Single-owner Hub handshake (not a multi-tenant OAuth provider):

1. CLI starts a grant (device code + user code + PKCE).
2. Operator approves in the Hub UI (already signed in).
3. CLI exchanges once (localhost callback and/or poll) for a CLI session.

The server access token never leaves the Hub. Connect codes are single-use
and expire. CLI session tokens are hashed at rest and accepted as Bearer.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from adhd_hub.auth import COOKIE_NAME, LoginThrottle, require_browser_request
from adhd_hub.config import Settings
from adhd_hub.sessions import BrowserSessions

GRANT_SECONDS = 10 * 60
CLI_SESSION_SECONDS = 90 * 24 * 60 * 60
POLL_INTERVAL_SECONDS = 5
MAX_GRANTS = 64
MAX_CLI_SESSIONS = 64
CLI_TOKEN_PREFIX = "ahcli_"
_USER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_bearer = HTTPBearer(auto_error=False)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_pkce() -> tuple[str, str]:
    """Return (verifier, S256 challenge) suitable for the connect handshake."""
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def verify_pkce(verifier: str, challenge: str) -> bool:
    if not (43 <= len(verifier) <= 128):
        return False
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(expected, challenge)


def generate_user_code() -> str:
    raw = "".join(secrets.choice(_USER_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_user_code(value: str) -> str:
    cleaned = "".join(ch for ch in value.upper() if ch.isalnum())
    if len(cleaned) != 8:
        return ""
    if any(ch not in _USER_ALPHABET for ch in cleaned):
        return ""
    return f"{cleaned[:4]}-{cleaned[4:]}"


def canonical_loopback_callback(url: str) -> str:
    """Return a canonical http://loopback:{port}/callback URL or raise ValueError."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "http":
        raise ValueError("callback must be http://127.0.0.1 (CLI listens locally)")
    if parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise ValueError("callback must not include credentials, query, or fragment")
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("callback must be a loopback address")
    path = parsed.path or "/callback"
    if path != "/callback":
        raise ValueError("callback path must be /callback")
    port = parsed.port
    if port is None or not (1 <= port <= 65535):
        raise ValueError("callback must include an explicit port")
    if host == "::1":
        return f"http://[::1]:{port}/callback"
    return f"http://{host}:{port}/callback"


@dataclass
class GrantInfo:
    user_code: str
    status: str
    expires_at: float
    callback_url: str | None
    state: str | None
    exchange_code: str | None = None


class ConnectStore:
    """SQLite grants + CLI sessions. Tokens and codes are stored hashed."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else None
        if self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:
            conn = sqlite3.connect(
                "file:adhd_hub_connect?mode=memory&cache=shared",
                uri=True,
                timeout=30,
            )
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS connect_grants (
                    device_hash TEXT PRIMARY KEY,
                    user_hash TEXT NOT NULL UNIQUE,
                    challenge TEXT NOT NULL,
                    state TEXT,
                    callback_url TEXT,
                    status TEXT NOT NULL,
                    exchange_hash TEXT,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_connect_grants_expires "
                "ON connect_grants(expires_at)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cli_sessions (
                    id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    last_used_at REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cli_sessions_expires ON cli_sessions(expires_at)"
            )

    def _purge(self, conn: sqlite3.Connection) -> None:
        now = time.time()
        conn.execute("DELETE FROM connect_grants WHERE expires_at <= ?", (now,))
        conn.execute(
            "DELETE FROM connect_grants WHERE status = 'consumed' AND created_at <= ?",
            (now - GRANT_SECONDS,),
        )
        conn.execute("DELETE FROM cli_sessions WHERE expires_at <= ?", (now,))
        grant_count = int(conn.execute("SELECT COUNT(*) AS c FROM connect_grants").fetchone()["c"])
        if grant_count > MAX_GRANTS:
            overflow = grant_count - MAX_GRANTS
            conn.execute(
                """
                DELETE FROM connect_grants WHERE device_hash IN (
                    SELECT device_hash FROM connect_grants
                    ORDER BY created_at ASC
                    LIMIT ?
                )
                """,
                (overflow,),
            )
        session_count = int(conn.execute("SELECT COUNT(*) AS c FROM cli_sessions").fetchone()["c"])
        if session_count > MAX_CLI_SESSIONS:
            overflow = session_count - MAX_CLI_SESSIONS
            conn.execute(
                """
                DELETE FROM cli_sessions WHERE id IN (
                    SELECT id FROM cli_sessions
                    ORDER BY created_at ASC
                    LIMIT ?
                )
                """,
                (overflow,),
            )

    def start_grant(
        self,
        *,
        challenge: str,
        state: str | None,
        callback_url: str | None,
    ) -> dict[str, Any]:
        if not challenge or len(challenge) > 128:
            raise ValueError("invalid code_challenge")
        callback = canonical_loopback_callback(callback_url) if callback_url else None
        now = time.time()
        expires = now + GRANT_SECONDS
        device_code = secrets.token_urlsafe(32)
        for _ in range(8):
            user_code = generate_user_code()
            try:
                with self._connect() as conn:
                    self._purge(conn)
                    pending = int(
                        conn.execute(
                            "SELECT COUNT(*) AS c FROM connect_grants WHERE status = 'pending'"
                        ).fetchone()["c"]
                    )
                    if pending >= MAX_GRANTS:
                        raise RuntimeError("too many pending connect grants")
                    conn.execute(
                        """
                        INSERT INTO connect_grants (
                            device_hash, user_hash, challenge, state, callback_url,
                            status, exchange_hash, expires_at, created_at
                        ) VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?, ?)
                        """,
                        (
                            _sha256_hex(device_code),
                            _sha256_hex(user_code),
                            challenge,
                            state,
                            callback,
                            expires,
                            now,
                        ),
                    )
                return {
                    "device_code": device_code,
                    "user_code": user_code,
                    "expires_in": GRANT_SECONDS,
                    "interval": POLL_INTERVAL_SECONDS,
                }
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("could not allocate a connect code")

    def approve_user_code(self, user_code: str) -> GrantInfo:
        normalized = normalize_user_code(user_code)
        if not normalized:
            raise KeyError("unknown_code")
        exchange_code = secrets.token_urlsafe(32)
        now = time.time()
        with self._connect() as conn:
            self._purge(conn)
            row = conn.execute(
                "SELECT * FROM connect_grants WHERE user_hash = ?",
                (_sha256_hex(normalized),),
            ).fetchone()
            if row is None:
                raise KeyError("unknown_code")
            if float(row["expires_at"]) <= now:
                conn.execute(
                    "DELETE FROM connect_grants WHERE device_hash = ?",
                    (row["device_hash"],),
                )
                raise KeyError("expired_token")
            if row["status"] == "consumed":
                raise ValueError("already_used")
            if row["status"] == "approved" and row["exchange_hash"]:
                # Do not re-issue the plaintext exchange code.
                raise ValueError("already_approved")
            conn.execute(
                """
                UPDATE connect_grants
                SET status = 'approved', exchange_hash = ?
                WHERE device_hash = ?
                """,
                (_sha256_hex(exchange_code), row["device_hash"]),
            )
        return GrantInfo(
            user_code=normalized,
            status="approved",
            expires_at=float(row["expires_at"]),
            callback_url=row["callback_url"],
            state=row["state"],
            exchange_code=exchange_code,
        )

    def _issue_session(self, conn: sqlite3.Connection) -> tuple[str, int]:
        now = time.time()
        expires = now + CLI_SESSION_SECONDS
        token = CLI_TOKEN_PREFIX + secrets.token_urlsafe(32)
        session_id = secrets.token_urlsafe(12)
        conn.execute(
            """
            INSERT INTO cli_sessions (id, token_hash, created_at, expires_at, last_used_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, _sha256_hex(token), now, expires, now),
        )
        return token, CLI_SESSION_SECONDS

    def _consume_row(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        verifier: str,
        state: str | None,
    ) -> tuple[str, int]:
        now = time.time()
        if float(row["expires_at"]) <= now:
            conn.execute("DELETE FROM connect_grants WHERE device_hash = ?", (row["device_hash"],))
            raise KeyError("expired_token")
        if row["status"] == "pending":
            raise PermissionError("authorization_pending")
        if row["status"] != "approved":
            raise KeyError("invalid_grant")
        if not verify_pkce(verifier, row["challenge"]):
            raise PermissionError("invalid_grant")
        if row["state"] and state is not None and not secrets.compare_digest(row["state"], state):
            raise PermissionError("invalid_grant")
        token, expires_in = self._issue_session(conn)
        conn.execute(
            "UPDATE connect_grants SET status = 'consumed', exchange_hash = NULL WHERE device_hash = ?",
            (row["device_hash"],),
        )
        conn.execute("DELETE FROM connect_grants WHERE device_hash = ?", (row["device_hash"],))
        return token, expires_in

    def exchange(
        self,
        *,
        verifier: str,
        device_code: str | None = None,
        code: str | None = None,
        state: str | None = None,
    ) -> tuple[Literal["pending"], None, None] | tuple[Literal["ok"], str, int]:
        if not verifier:
            raise PermissionError("invalid_grant")
        with self._connect() as conn:
            self._purge(conn)
            row = None
            if device_code:
                row = conn.execute(
                    "SELECT * FROM connect_grants WHERE device_hash = ?",
                    (_sha256_hex(device_code),),
                ).fetchone()
            elif code:
                row = conn.execute(
                    "SELECT * FROM connect_grants WHERE exchange_hash = ?",
                    (_sha256_hex(code),),
                ).fetchone()
            else:
                raise PermissionError("invalid_grant")
            if row is None:
                raise KeyError("invalid_grant")
            try:
                token, expires_in = self._consume_row(conn, row, verifier, state)
            except PermissionError as exc:
                if str(exc) == "authorization_pending":
                    return "pending", None, None
                raise
            return "ok", token, expires_in

    def valid_session(self, token: str | None) -> bool:
        if not token or not token.startswith(CLI_TOKEN_PREFIX):
            return False
        now = time.time()
        token_hash = _sha256_hex(token)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, expires_at FROM cli_sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return False
            if float(row["expires_at"]) <= now:
                conn.execute("DELETE FROM cli_sessions WHERE id = ?", (row["id"],))
                return False
            conn.execute(
                "UPDATE cli_sessions SET last_used_at = ? WHERE id = ?",
                (now, row["id"]),
            )
            return True

    def list_sessions(self) -> list[dict[str, Any]]:
        now = time.time()
        with self._connect() as conn:
            self._purge(conn)
            rows = conn.execute(
                """
                SELECT id, created_at, expires_at, last_used_at
                FROM cli_sessions
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [
            {
                "id": row["id"],
                "created_at": int(row["created_at"]),
                "expires_at": int(row["expires_at"]),
                "last_used_at": int(row["last_used_at"]) if row["last_used_at"] else None,
                "expires_in": max(0, int(float(row["expires_at"]) - now)),
            }
            for row in rows
        ]

    def revoke_session(self, session_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM cli_sessions WHERE id = ?", (session_id,))
            return cur.rowcount > 0

    def revoke_token(self, token: str) -> bool:
        if not token:
            return False
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM cli_sessions WHERE token_hash = ?",
                (_sha256_hex(token),),
            )
            return cur.rowcount > 0

    def expire_grant_now(self, device_code: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE connect_grants SET expires_at = 0 WHERE device_hash = ?",
                (_sha256_hex(device_code),),
            )

    def expire_session_now(self, token: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE cli_sessions SET expires_at = 0 WHERE token_hash = ?",
                (_sha256_hex(token),),
            )

    def grant_count(self) -> int:
        with self._connect() as conn:
            self._purge(conn)
            return int(conn.execute("SELECT COUNT(*) AS c FROM connect_grants").fetchone()["c"])

    def session_count(self) -> int:
        with self._connect() as conn:
            self._purge(conn)
            return int(conn.execute("SELECT COUNT(*) AS c FROM cli_sessions").fetchone()["c"])


def bearer_authorized(settings: Settings, store: ConnectStore, value: str) -> bool:
    from adhd_hub.auth import token_matches

    return token_matches(settings, value) or store.valid_session(value)


class StartConnectRequest(BaseModel):
    code_challenge: str = Field(min_length=43, max_length=128)
    code_challenge_method: Literal["S256"] = "S256"
    state: str | None = Field(default=None, max_length=256)
    callback_url: str | None = Field(default=None, max_length=256)


class ApproveConnectRequest(BaseModel):
    user_code: str = Field(min_length=8, max_length=32)


class ExchangeConnectRequest(BaseModel):
    code_verifier: str = Field(min_length=43, max_length=128)
    device_code: str | None = Field(default=None, min_length=16, max_length=256)
    code: str | None = Field(default=None, min_length=16, max_length=256)
    state: str | None = Field(default=None, max_length=256)


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status, {"error": code})


def build_connect_router(
    settings: Settings,
    sessions: BrowserSessions,
    store: ConnectStore,
) -> APIRouter:
    router = APIRouter(prefix="/api/connect", tags=["CLI connect"])
    throttle = LoginThrottle()

    def client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def require_browser(request: Request) -> None:
        if not sessions.valid(request.cookies.get(COOKIE_NAME)):
            raise HTTPException(
                401,
                "Sign in to the Hub dashboard first",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            require_browser_request(request, settings)

    def verification_base(request: Request) -> str:
        return settings.resolve_public_url() or str(request.base_url).rstrip("/")

    @router.post("/start")
    async def start_connect(payload: StartConnectRequest, request: Request):
        throttle.check(client_key(request))
        try:
            grant = store.start_grant(
                challenge=payload.code_challenge,
                state=payload.state,
                callback_url=payload.callback_url,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(429, str(exc), headers={"Retry-After": "60"}) from exc
        base = verification_base(request)
        user_code = grant["user_code"]
        return {
            **grant,
            "verification_uri": f"{base}/ui/",
            "verification_uri_complete": f"{base}/ui/?connect={user_code}",
        }

    @router.post("/approve")
    async def approve_connect(payload: ApproveConnectRequest, request: Request):
        require_browser(request)
        throttle.check(client_key(request))
        try:
            info = store.approve_user_code(payload.user_code)
        except KeyError as exc:
            code = str(exc).strip("'")
            if code == "expired_token":
                raise HTTPException(400, "That code expired. Run the CLI command again.") from exc
            raise HTTPException(400, "That code was not recognized. Check the terminal.") from exc
        except ValueError as exc:
            if str(exc) == "already_used":
                raise HTTPException(409, "That code was already used.") from exc
            raise HTTPException(
                409, "That CLI is already waiting to finish. Check the terminal."
            ) from exc
        redirect = None
        if info.callback_url and info.exchange_code:
            redirect = f"{info.callback_url}?code={info.exchange_code}"
            if info.state:
                redirect += f"&state={info.state}"
        return {
            "ok": True,
            "user_code": info.user_code,
            "redirect": redirect,
            "expires_at": int(info.expires_at),
        }

    @router.post("/token")
    async def exchange_connect(payload: ExchangeConnectRequest):
        if (payload.device_code is None) == (payload.code is None):
            raise HTTPException(400, "Supply device_code or code")
        try:
            status, token, expires_in = store.exchange(
                verifier=payload.code_verifier,
                device_code=payload.device_code,
                code=payload.code,
                state=payload.state,
            )
        except KeyError as exc:
            raise _error(400, str(exc).strip("'")) from exc
        except PermissionError as exc:
            raise _error(400, str(exc)) from exc
        if status == "pending":
            raise _error(400, "authorization_pending")
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": expires_in,
        }

    @router.get("/sessions")
    async def list_cli_sessions(request: Request):
        require_browser(request)
        return {"sessions": store.list_sessions(), "grant_seconds": GRANT_SECONDS}

    @router.delete("/sessions/{session_id}", status_code=204)
    async def revoke_cli_session(session_id: str, request: Request):
        require_browser(request)
        require_browser_request(request, settings)
        if not store.revoke_session(session_id):
            raise HTTPException(404, "CLI session not found")

    @router.delete("/session", status_code=204)
    async def revoke_current_cli_session(
        credentials: HTTPAuthorizationCredentials | None = Security(_bearer),  # noqa: B008
    ):
        if credentials is None or not store.revoke_token(credentials.credentials):
            raise HTTPException(401, "Invalid or missing CLI session")

    return router
