"""Durable browser session store (survives process restart / multi-worker)."""

from __future__ import annotations

import secrets
import sqlite3
import time
from pathlib import Path

SESSION_SECONDS = 12 * 60 * 60
_DEFAULT_MAX = 1024


class BrowserSessions:
    """Opaque session tokens persisted in SQLite with absolute wall-clock expiry."""

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        max_sessions: int = _DEFAULT_MAX,
    ) -> None:
        # Shared in-memory DB when no path is given (unit tests).
        self.db_path = Path(db_path) if db_path else None
        self.max_sessions = max_sessions
        if self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:
            conn = sqlite3.connect(
                "file:adhd_hub_sessions?mode=memory&cache=shared",
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
                CREATE TABLE IF NOT EXISTS browser_sessions (
                    token TEXT PRIMARY KEY,
                    expires_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_browser_sessions_expires "
                "ON browser_sessions(expires_at)"
            )

    def _purge(self, conn: sqlite3.Connection) -> None:
        now = time.time()
        conn.execute("DELETE FROM browser_sessions WHERE expires_at <= ?", (now,))
        count = int(conn.execute("SELECT COUNT(*) AS c FROM browser_sessions").fetchone()["c"])
        if count <= self.max_sessions:
            return
        overflow = count - self.max_sessions
        conn.execute(
            """
            DELETE FROM browser_sessions WHERE token IN (
                SELECT token FROM browser_sessions
                ORDER BY expires_at ASC
                LIMIT ?
            )
            """,
            (overflow,),
        )

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        expires = time.time() + SESSION_SECONDS
        with self._connect() as conn:
            self._purge(conn)
            conn.execute(
                "INSERT INTO browser_sessions (token, expires_at) VALUES (?, ?)",
                (token, expires),
            )
        return token

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT expires_at FROM browser_sessions WHERE token = ?",
                (token,),
            ).fetchone()
            if row is None:
                return False
            if float(row["expires_at"]) <= time.time():
                conn.execute("DELETE FROM browser_sessions WHERE token = ?", (token,))
                return False
            return True

    def revoke(self, token: str | None) -> None:
        if not token:
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM browser_sessions WHERE token = ?", (token,))

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM browser_sessions")

    def expire_now(self, token: str) -> None:
        """Force-expire a token (tests)."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE browser_sessions SET expires_at = 0 WHERE token = ?",
                (token,),
            )

    def count(self) -> int:
        with self._connect() as conn:
            self._purge(conn)
            return int(conn.execute("SELECT COUNT(*) AS c FROM browser_sessions").fetchone()["c"])

    def __contains__(self, token: object) -> bool:
        return isinstance(token, str) and self.valid(token)
