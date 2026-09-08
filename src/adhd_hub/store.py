from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from adhd_hub.models import (
    EnergyLevel,
    PendingAction,
    PendingActionKind,
    PendingActionStatus,
    Project,
    ProjectUpsert,
    Reminder,
    ReminderCreate,
    ReminderKind,
    Thread,
    ThreadStatus,
    ThreadUpsert,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:64] or "untitled"


def normalize_workspace_path(path: str | None) -> str | None:
    if not path or not str(path).strip():
        return None
    p = str(path).strip().replace("\\", "/")
    # Drop trailing slash except drive roots like C:/
    if len(p) > 3:
        p = p.rstrip("/")
    return p.casefold()


def workspace_basename(path: str | None) -> str | None:
    norm = normalize_workspace_path(path)
    if not norm:
        return None
    parts = [x for x in norm.split("/") if x and not (len(x) == 2 and x[1] == ":")]
    return parts[-1] if parts else None


def item_id(summary: str, key: str = "") -> str:
    raw = f"{summary.strip().lower()}::{key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS threads (
                    id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL,
                    energy TEXT NOT NULL,
                    source_tool TEXT,
                    workspace_path TEXT,
                    project_slug TEXT,
                    chat_ref TEXT,
                    transcript_ref TEXT,
                    origin TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_reminded_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_threads_status ON threads(status);
                CREATE INDEX IF NOT EXISTS idx_threads_slug ON threads(project_slug);

                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    message TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    due_at TEXT,
                    created_at TEXT NOT NULL,
                    handled INTEGER NOT NULL DEFAULT 0,
                    last_fired_at TEXT
                );

                CREATE TABLE IF NOT EXISTS progress_notes (
                    id TEXT PRIMARY KEY,
                    project_slug TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_progress_slug ON progress_notes(project_slug);

                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS projects (
                    slug TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    workspace_paths TEXT NOT NULL DEFAULT '[]',
                    default_energy TEXT NOT NULL DEFAULT 'unknown',
                    forge_owner TEXT,
                    forge_repo TEXT,
                    forge_wiki_path TEXT,
                    forge_project_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at);

                CREATE TABLE IF NOT EXISTS pending_actions (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    payload TEXT NOT NULL DEFAULT '{}',
                    reason TEXT,
                    source_tool TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_actions(status);
                """
            )
            cols = {
                r[1]
                for r in conn.execute("PRAGMA table_info(projects)").fetchall()
            }
            if "forge_project_id" not in cols:
                conn.execute("ALTER TABLE projects ADD COLUMN forge_project_id TEXT")

    def _row_thread(self, row: sqlite3.Row) -> Thread:
        return Thread(
            id=row["id"],
            summary=row["summary"],
            status=ThreadStatus(row["status"]),
            energy=EnergyLevel(row["energy"]),
            source_tool=row["source_tool"],
            workspace_path=row["workspace_path"],
            project_slug=row["project_slug"],
            chat_ref=row["chat_ref"],
            transcript_ref=row["transcript_ref"],
            origin=row["origin"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            last_reminded_at=(
                datetime.fromisoformat(row["last_reminded_at"])
                if row["last_reminded_at"]
                else None
            ),
        )

    def upsert_thread(self, payload: ThreadUpsert) -> Thread:
        now = utcnow()
        tid = payload.id or item_id(
            payload.summary,
            payload.transcript_ref or payload.workspace_path or payload.project_slug or "",
        )
        slug = payload.project_slug or slugify(payload.summary)
        with self._conn() as conn:
            existing = conn.execute("SELECT * FROM threads WHERE id = ?", (tid,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE threads SET
                        summary = ?, status = ?, energy = ?,
                        source_tool = COALESCE(?, source_tool),
                        workspace_path = COALESCE(?, workspace_path),
                        project_slug = COALESCE(?, project_slug),
                        chat_ref = COALESCE(?, chat_ref),
                        transcript_ref = COALESCE(?, transcript_ref),
                        origin = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        payload.summary,
                        payload.status.value,
                        payload.energy.value,
                        payload.source_tool,
                        payload.workspace_path,
                        slug,
                        payload.chat_ref,
                        payload.transcript_ref,
                        payload.origin,
                        now.isoformat(),
                        tid,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO threads (
                        id, summary, status, energy, source_tool, workspace_path,
                        project_slug, chat_ref, transcript_ref, origin,
                        created_at, updated_at, last_reminded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        tid,
                        payload.summary,
                        payload.status.value,
                        payload.energy.value,
                        payload.source_tool,
                        payload.workspace_path,
                        slug,
                        payload.chat_ref,
                        payload.transcript_ref,
                        payload.origin,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
            row = conn.execute("SELECT * FROM threads WHERE id = ?", (tid,)).fetchone()
        assert row is not None
        return self._row_thread(row)

    def get_thread(self, thread_id: str) -> Thread | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
        return self._row_thread(row) if row else None

    def list_threads(
        self,
        *,
        status: ThreadStatus | None = ThreadStatus.open,
        project_slug: str | None = None,
        energy: EnergyLevel | None = None,
        limit: int = 100,
    ) -> list[Thread]:
        clauses: list[str] = []
        args: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            args.append(status.value)
        if project_slug:
            clauses.append("project_slug = ?")
            args.append(project_slug)
        if energy:
            clauses.append("energy = ?")
            args.append(energy.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM threads {where} ORDER BY updated_at DESC LIMIT ?"
        args.append(limit)
        with self._conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._row_thread(r) for r in rows]

    def mark_status(
        self, thread_id: str, status: ThreadStatus, note: str | None = None
    ) -> Thread | None:
        now = utcnow()
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE threads SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, now.isoformat(), thread_id),
            )
            if note:
                conn.execute(
                    "INSERT INTO progress_notes (id, project_slug, content, created_at) VALUES (?, ?, ?, ?)",
                    (
                        str(uuid4()),
                        row["project_slug"] or slugify(row["summary"]),
                        f"[status→{status.value}] {note}",
                        now.isoformat(),
                    ),
                )
            row = conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
        assert row is not None
        return self._row_thread(row)

    def touch_reminded(self, thread_ids: list[str]) -> None:
        if not thread_ids:
            return
        now = utcnow().isoformat()
        with self._conn() as conn:
            for tid in thread_ids:
                conn.execute(
                    "UPDATE threads SET last_reminded_at = ? WHERE id = ?",
                    (now, tid),
                )

    def add_progress_note(self, project_slug: str, content: str) -> str:
        nid = str(uuid4())
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO progress_notes (id, project_slug, content, created_at) VALUES (?, ?, ?, ?)",
                (nid, project_slug, content, utcnow().isoformat()),
            )
        return nid

    def list_progress_notes(self, project_slug: str, limit: int = 50) -> list[dict[str, str]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, project_slug, content, created_at FROM progress_notes
                WHERE project_slug = ? ORDER BY created_at DESC LIMIT ?
                """,
                (project_slug, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def create_reminder(self, payload: ReminderCreate) -> Reminder:
        rid = str(uuid4())
        now = utcnow()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO reminders (id, message, kind, due_at, created_at, handled, last_fired_at)
                VALUES (?, ?, ?, ?, ?, 0, NULL)
                """,
                (
                    rid,
                    payload.message,
                    payload.kind.value,
                    payload.due_at.isoformat() if payload.due_at else None,
                    now.isoformat(),
                ),
            )
        return Reminder(
            id=rid,
            message=payload.message,
            kind=payload.kind,
            due_at=payload.due_at,
            created_at=now,
            handled=False,
        )

    def _row_reminder(self, row: sqlite3.Row) -> Reminder:
        return Reminder(
            id=row["id"],
            message=row["message"],
            kind=ReminderKind(row["kind"]),
            due_at=datetime.fromisoformat(row["due_at"]) if row["due_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            handled=bool(row["handled"]),
            last_fired_at=(
                datetime.fromisoformat(row["last_fired_at"]) if row["last_fired_at"] else None
            ),
        )

    def list_reminders(self, *, include_handled: bool = False) -> list[Reminder]:
        with self._conn() as conn:
            if include_handled:
                rows = conn.execute(
                    "SELECT * FROM reminders ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM reminders WHERE handled = 0 ORDER BY created_at DESC"
                ).fetchall()
        return [self._row_reminder(r) for r in rows]

    def due_reminders(self, now: datetime | None = None) -> list[Reminder]:
        now = now or utcnow()
        out: list[Reminder] = []
        for rem in self.list_reminders(include_handled=False):
            if rem.kind == ReminderKind.once:
                if rem.due_at and rem.due_at <= now:
                    out.append(rem)
            elif rem.kind == ReminderKind.session:
                out.append(rem)
            elif rem.kind == ReminderKind.daily:
                # Fire once per calendar day
                if rem.last_fired_at is None or rem.last_fired_at.date() < now.date():
                    out.append(rem)
            elif rem.kind == ReminderKind.random:
                # Surfaced by digest with low probability at API layer; still list here
                out.append(rem)
        return out

    def mark_reminder_fired(self, reminder_id: str, *, handle_once: bool = True) -> None:
        now = utcnow().isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT kind FROM reminders WHERE id = ?", (reminder_id,)
            ).fetchone()
            if not row:
                return
            handled = 1 if handle_once and row["kind"] == ReminderKind.once.value else 0
            conn.execute(
                "UPDATE reminders SET last_fired_at = ?, handled = ? WHERE id = ?",
                (now, handled, reminder_id),
            )

    def get_meta(self, key: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str | dict[str, Any]) -> None:
        if not isinstance(value, str):
            value = json.dumps(value)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def _row_pending(self, row: sqlite3.Row) -> PendingAction:
        try:
            payload = json.loads(row["payload"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return PendingAction(
            id=row["id"],
            kind=PendingActionKind(row["kind"]),
            status=PendingActionStatus(row["status"]),
            payload=payload,
            reason=row["reason"],
            source_tool=row["source_tool"],
            created_at=datetime.fromisoformat(row["created_at"]),
            resolved_at=(
                datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None
            ),
        )

    def create_pending_action(
        self,
        *,
        kind: PendingActionKind,
        payload: dict[str, Any],
        reason: str | None = None,
        source_tool: str | None = None,
    ) -> PendingAction:
        now = utcnow()
        aid = item_id(kind.value, json.dumps(payload, sort_keys=True) + now.isoformat())
        with self._conn() as conn:
            # Deduplicate identical pending actions
            rows = conn.execute(
                "SELECT * FROM pending_actions WHERE status = 'pending' AND kind = ?",
                (kind.value,),
            ).fetchall()
            for row in rows:
                existing = self._row_pending(row)
                if existing.payload == payload:
                    return existing
            conn.execute(
                """
                INSERT INTO pending_actions (
                    id, kind, status, payload, reason, source_tool, created_at, resolved_at
                ) VALUES (?, ?, 'pending', ?, ?, ?, ?, NULL)
                """,
                (
                    aid,
                    kind.value,
                    json.dumps(payload),
                    reason,
                    source_tool,
                    now.isoformat(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM pending_actions WHERE id = ?", (aid,)
            ).fetchone()
        assert row is not None
        return self._row_pending(row)

    def list_pending_actions(
        self, *, status: PendingActionStatus | None = PendingActionStatus.pending
    ) -> list[PendingAction]:
        with self._conn() as conn:
            if status is None:
                rows = conn.execute(
                    "SELECT * FROM pending_actions ORDER BY created_at DESC LIMIT 100"
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM pending_actions WHERE status = ?
                    ORDER BY created_at DESC LIMIT 100
                    """,
                    (status.value,),
                ).fetchall()
        return [self._row_pending(r) for r in rows]

    def get_pending_action(self, action_id: str) -> PendingAction | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM pending_actions WHERE id = ?", (action_id,)
            ).fetchone()
        return self._row_pending(row) if row else None

    def resolve_pending_action(
        self, action_id: str, status: PendingActionStatus
    ) -> PendingAction | None:
        if status not in (PendingActionStatus.approved, PendingActionStatus.rejected):
            raise ValueError("invalid_status")
        now = utcnow().isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM pending_actions WHERE id = ?", (action_id,)
            ).fetchone()
            if not row:
                return None
            if row["status"] != PendingActionStatus.pending.value:
                return self._row_pending(row)
            conn.execute(
                """
                UPDATE pending_actions SET status = ?, resolved_at = ? WHERE id = ?
                """,
                (status.value, now, action_id),
            )
            out = conn.execute(
                "SELECT * FROM pending_actions WHERE id = ?", (action_id,)
            ).fetchone()
        return self._row_pending(out) if out else None

    def count_open(self) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM threads WHERE status = ?",
                (ThreadStatus.open.value,),
            ).fetchone()
        return int(row["c"]) if row else 0

    def count_status(self, status: ThreadStatus) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM threads WHERE status = ?",
                (status.value,),
            ).fetchone()
        return int(row["c"]) if row else 0

    def _row_project(self, row: sqlite3.Row) -> Project:
        raw_paths = row["workspace_paths"] or "[]"
        try:
            paths = json.loads(raw_paths)
        except json.JSONDecodeError:
            paths = []
        if not isinstance(paths, list):
            paths = []
        return Project(
            slug=row["slug"],
            title=row["title"],
            description=row["description"],
            workspace_paths=[str(p) for p in paths],
            default_energy=EnergyLevel(row["default_energy"] or "unknown"),
            forge_owner=row["forge_owner"],
            forge_repo=row["forge_repo"],
            forge_wiki_path=row["forge_wiki_path"],
            forge_project_id=row["forge_project_id"] if "forge_project_id" in row.keys() else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def upsert_project(self, payload: ProjectUpsert) -> Project:
        now = utcnow()
        slug = slugify(payload.slug or payload.title)
        paths = []
        for p in payload.workspace_paths:
            n = normalize_workspace_path(p)
            if n and n not in paths:
                paths.append(n)
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM projects WHERE slug = ?", (slug,)
            ).fetchone()
            if existing:
                # Merge paths
                try:
                    old = json.loads(existing["workspace_paths"] or "[]")
                except json.JSONDecodeError:
                    old = []
                merged = list(dict.fromkeys([*(str(x) for x in old), *paths]))
                conn.execute(
                    """
                    UPDATE projects SET
                        title = ?, description = COALESCE(?, description),
                        workspace_paths = ?, default_energy = ?,
                        forge_owner = COALESCE(?, forge_owner),
                        forge_repo = COALESCE(?, forge_repo),
                        forge_wiki_path = COALESCE(?, forge_wiki_path),
                        forge_project_id = COALESCE(?, forge_project_id),
                        updated_at = ?
                    WHERE slug = ?
                    """,
                    (
                        payload.title,
                        payload.description,
                        json.dumps(merged),
                        payload.default_energy.value,
                        payload.forge_owner,
                        payload.forge_repo,
                        payload.forge_wiki_path,
                        payload.forge_project_id,
                        now.isoformat(),
                        slug,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO projects (
                        slug, title, description, workspace_paths, default_energy,
                        forge_owner, forge_repo, forge_wiki_path, forge_project_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        slug,
                        payload.title,
                        payload.description,
                        json.dumps(paths),
                        payload.default_energy.value,
                        payload.forge_owner,
                        payload.forge_repo,
                        payload.forge_wiki_path,
                        payload.forge_project_id,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
            row = conn.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone()
        assert row is not None
        return self._row_project(row)

    def get_project(self, slug: str) -> Project | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE slug = ?", (slugify(slug),)
            ).fetchone()
        return self._row_project(row) if row else None

    def list_projects(self, limit: int = 200) -> list[Project]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY title COLLATE NOCASE ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_project(r) for r in rows]

    def resolve_project_by_workspace(self, workspace_path: str | None) -> Project | None:
        norm = normalize_workspace_path(workspace_path)
        if not norm:
            return None
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM projects").fetchall()
        best: Project | None = None
        best_len = -1
        for row in rows:
            proj = self._row_project(row)
            for p in proj.workspace_paths:
                np = normalize_workspace_path(p)
                if not np:
                    continue
                if (
                    (norm == np or norm.startswith(np + "/") or np.startswith(norm + "/"))
                    and len(np) > best_len
                ):
                    best = proj
                    best_len = len(np)
        if best:
            return best
        # Fallback: match basename to slug
        base = workspace_basename(workspace_path)
        if base:
            return self.get_project(slugify(base))
        return None

    def ensure_project_for_slug(
        self,
        slug: str,
        *,
        title: str | None = None,
        workspace_path: str | None = None,
    ) -> Project:
        existing = self.get_project(slug)
        paths = [workspace_path] if workspace_path else []
        if existing:
            if workspace_path:
                return self.upsert_project(
                    ProjectUpsert(
                        slug=existing.slug,
                        title=existing.title,
                        description=existing.description,
                        workspace_paths=paths,
                        default_energy=existing.default_energy,
                        forge_owner=existing.forge_owner,
                        forge_repo=existing.forge_repo,
                        forge_wiki_path=existing.forge_wiki_path,
                        forge_project_id=existing.forge_project_id,
                    )
                )
            return existing
        display = title or slug.replace("-", " ").title()
        return self.upsert_project(
            ProjectUpsert(slug=slug, title=display, workspace_paths=paths)
        )

    def rename_project(
        self,
        old_slug: str,
        new_slug: str,
        *,
        title: str | None = None,
    ) -> Project:
        old = slugify(old_slug)
        new = slugify(new_slug)
        if not new:
            raise ValueError("invalid_slug")
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM projects WHERE slug = ?", (old,)).fetchone()
            if not row:
                raise KeyError("not_found")
            if old != new:
                clash = conn.execute(
                    "SELECT 1 FROM projects WHERE slug = ?", (new,)
                ).fetchone()
                if clash:
                    raise ValueError("conflict")
            now = utcnow().isoformat()
            new_title = title or row["title"]
            if old == new:
                conn.execute(
                    "UPDATE projects SET title = ?, updated_at = ? WHERE slug = ?",
                    (new_title, now, old),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO projects (
                        slug, title, description, workspace_paths, default_energy,
                        forge_owner, forge_repo, forge_wiki_path, forge_project_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new,
                        new_title,
                        row["description"],
                        row["workspace_paths"],
                        row["default_energy"],
                        row["forge_owner"],
                        row["forge_repo"],
                        row["forge_wiki_path"],
                        row["forge_project_id"]
                        if "forge_project_id" in row.keys()
                        else None,
                        row["created_at"],
                        now,
                    ),
                )
                conn.execute(
                    "UPDATE threads SET project_slug = ? WHERE project_slug = ?",
                    (new, old),
                )
                conn.execute(
                    "UPDATE progress_notes SET project_slug = ? WHERE project_slug = ?",
                    (new, old),
                )
                conn.execute("DELETE FROM projects WHERE slug = ?", (old,))
            out = conn.execute("SELECT * FROM projects WHERE slug = ?", (new,)).fetchone()
        assert out is not None
        return self._row_project(out)

    def delete_project(self, slug: str) -> dict[str, Any]:
        """Remove project registry row; clear thread/progress slug refs. Does not wipe wiki."""
        safe = slugify(slug)
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM projects WHERE slug = ?", (safe,)).fetchone()
            if not row:
                raise KeyError("not_found")
            thread_count = conn.execute(
                "SELECT COUNT(*) AS c FROM threads WHERE project_slug = ?",
                (safe,),
            ).fetchone()
            open_count = conn.execute(
                "SELECT COUNT(*) AS c FROM threads WHERE project_slug = ? AND status = 'open'",
                (safe,),
            ).fetchone()
            conn.execute(
                "UPDATE threads SET project_slug = NULL WHERE project_slug = ?",
                (safe,),
            )
            conn.execute(
                "UPDATE progress_notes SET project_slug = ? WHERE project_slug = ?",
                (f"deleted:{safe}", safe),
            )
            conn.execute("DELETE FROM projects WHERE slug = ?", (safe,))
        return {
            "deleted": safe,
            "threads_cleared": int(thread_count["c"]) if thread_count else 0,
            "open_threads_cleared": int(open_count["c"]) if open_count else 0,
        }

    def thread_counts_by_project(self) -> dict[str, dict[str, int]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT COALESCE(project_slug, '') AS slug, status, COUNT(*) AS c
                FROM threads GROUP BY COALESCE(project_slug, ''), status
                """
            ).fetchall()
        out: dict[str, dict[str, int]] = {}
        for row in rows:
            slug = row["slug"] or "unclassified"
            bucket = out.setdefault(slug, {"open": 0, "blocked": 0, "done": 0, "dismissed": 0})
            status = row["status"]
            if status in bucket:
                bucket[status] = int(row["c"])
        return out

    def analytics_added_done(self, days: int = 14) -> list[dict[str, Any]]:
        """Per-day counts of threads created vs marked done (approx via updated_at when done)."""
        from datetime import timedelta

        now = utcnow()
        start = (now - timedelta(days=days - 1)).date()
        days_map: dict[str, dict[str, int]] = {}
        for i in range(days):
            d = (start + timedelta(days=i)).isoformat()
            days_map[d] = {"date": d, "added": 0, "finished": 0}
        with self._conn() as conn:
            created = conn.execute("SELECT created_at FROM threads").fetchall()
            for row in created:
                try:
                    created_day = datetime.fromisoformat(row["created_at"]).date().isoformat()
                except ValueError:
                    continue
                if created_day in days_map:
                    days_map[created_day]["added"] += 1
            done_rows = conn.execute(
                "SELECT updated_at FROM threads WHERE status = ?",
                (ThreadStatus.done.value,),
            ).fetchall()
            for row in done_rows:
                try:
                    day = datetime.fromisoformat(row["updated_at"]).date().isoformat()
                except ValueError:
                    continue
                if day in days_map:
                    days_map[day]["finished"] += 1
        return [days_map[k] for k in sorted(days_map.keys())]

    def done_counts(self) -> dict[str, int]:
        from datetime import timedelta

        now = utcnow()
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        done_today = 0
        done_week = 0
        streak_days: set = set()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT updated_at FROM threads WHERE status = ?",
                (ThreadStatus.done.value,),
            ).fetchall()
        for row in rows:
            try:
                d = datetime.fromisoformat(row["updated_at"]).date()
            except ValueError:
                continue
            if d == today:
                done_today += 1
            if d >= week_start:
                done_week += 1
            streak_days.add(d)
        streak = 0
        cursor = today
        while cursor in streak_days:
            streak += 1
            cursor = cursor - timedelta(days=1)
        return {"done_today": done_today, "done_week": done_week, "day_streak": streak}
