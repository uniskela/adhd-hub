"""Durable Hub activity events (Foundation B3).

Publish boundary
----------------
Call :func:`publish_activity_event` only **after** the underlying mutation is
durably committed (SQLite commit / confirmed remote write). Prefer the shared
helpers on :class:`adhd_hub.service.HubService` so REST, MCP, scheduler, and UI
paths share one redaction + idempotency + fan-out boundary.

Do not put transcripts, secrets, private Hub URLs, or absolute machine paths in
``metadata``. Live UI subscribers receive lightweight invalidation hints only;
refetch remains the displayed truth.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

log = logging.getLogger(__name__)

EVENT_SCHEMA_VERSION = 1

# High-value families for the first B3 cut (extend carefully).
THREAD_CREATED = "thread.created"
THREAD_PROGRESS_UPDATED = "thread.progress_updated"
THREAD_COMPLETED = "thread.completed"
THREAD_PAUSED = "thread.paused"
THREAD_TRIAGE_CONFIRMED = "thread.triage_confirmed"
THREAD_TRIAGE_SNOOZED = "thread.triage_snoozed"
FORGE_RECONCILE_SUCCEEDED = "forge.reconcile_succeeded"
FORGE_RECONCILE_FAILED = "forge.reconcile_failed"

SAFE_ACTOR_SOURCES = frozenset(
    {
        "api",
        "mcp",
        "ui",
        "scheduler",
        "forge",
        "system",
        "cursor",
        "codex",
        "claude",
        "openclaw",
        "cli",
        "unknown",
    }
)

_SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|bearer|cookie|"
    r"credential|private[_-]?key|ssh)",
    re.IGNORECASE,
)
_UNSAFE_KEY_RE = re.compile(
    r"(transcript|chat_ref|transcript_ref|workspace_path|absolute_path|"
    r"private_url|hub_url|public_url|raw_body|prompt)",
    re.IGNORECASE,
)
_ABS_PATH_RE = re.compile(r"(^|[\s\"'=])(/[^\s\"']+|\\\\[^\s\"']+|[A-Za-z]:\\[^\s\"']+)")
_URL_RE = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)
_LOCALHOST_HOST_RE = re.compile(
    r"(^|://)(localhost|127\.0\.0\.1|0\.0\.0\.0|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|"
    r"172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+|100\.\d+\.\d+\.\d+)(:|/|$)",
    re.IGNORECASE,
)

# Keys allowed in persisted metadata (allowlist after redaction).
_ALLOWED_META_KEYS = frozenset(
    {
        "status",
        "previous_status",
        "reason",
        "error",
        "skipped",
        "applied",
        "created_thread",
        "fingerprint",
        "external_fingerprint",
        "reconcile_count",
        "applied_count",
        "failed_count",
        "project_slug",
        "scope",
        "fields_changed",
        "hint",
        "ok",
    }
)


@dataclass(frozen=True)
class ActivityEvent:
    id: str
    schema_version: int
    event_type: str
    created_at: str
    project_slug: str | None = None
    work_id: str | None = None
    thread_id: str | None = None
    actor: str | None = None
    source: str | None = None
    idempotency_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)

    def invalidation_hint(self) -> dict[str, Any]:
        """Lightweight SSE payload — never full private thread state."""
        return {
            "id": self.id,
            "type": self.event_type,
            "created_at": self.created_at,
            "project_slug": self.project_slug,
            "thread_id": self.thread_id,
            "work_id": self.work_id,
        }


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def safe_actor(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()[:64]
    if not text:
        return None
    if text in SAFE_ACTOR_SOURCES:
        return text
    # Keep short opaque tool names without path/url characters.
    if re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", text) and "/" not in text:
        return text
    return "unknown"


def _looks_like_private_url(value: str) -> bool:
    if not _URL_RE.search(value):
        return False
    return bool(_LOCALHOST_HOST_RE.search(value)) or "tailscale" in value.casefold()


def _scrub_string(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    if _looks_like_private_url(text):
        return None
    if _ABS_PATH_RE.search(text):
        return None
    if len(text) > 500:
        text = text[:500]
    return text


def sanitize_event_metadata(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Drop secrets, transcripts, private URLs, and machine paths from metadata."""
    if not raw:
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        key_s = str(key)
        if _SECRET_KEY_RE.search(key_s) or _UNSAFE_KEY_RE.search(key_s):
            continue
        if key_s not in _ALLOWED_META_KEYS:
            continue
        cleaned = _sanitize_value(value)
        if cleaned is None:
            continue
        out[key_s] = cleaned
    return out


def _sanitize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _scrub_string(value)
    if isinstance(value, list):
        items = []
        for item in value[:20]:
            cleaned = _sanitize_value(item)
            if cleaned is not None:
                items.append(cleaned)
        return items
    if isinstance(value, dict):
        # Nested objects only retain allowlisted keys via a shallow pass.
        nested: dict[str, Any] = {}
        for key, nested_val in list(value.items())[:20]:
            key_s = str(key)
            if _SECRET_KEY_RE.search(key_s) or _UNSAFE_KEY_RE.search(key_s):
                continue
            if key_s not in _ALLOWED_META_KEYS:
                continue
            cleaned = _sanitize_value(nested_val)
            if cleaned is not None:
                nested[key_s] = cleaned
        return nested
    return None


class EventBus:
    """In-process fan-out for SSE invalidation (no Redis)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[ActivityEvent], None]] = []

    def subscribe(self, callback: Callable[[ActivityEvent], None]) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(callback)

        def _unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers.remove(callback)
                except ValueError:
                    pass

        return _unsubscribe

    def publish(self, event: ActivityEvent) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                log.exception("activity event subscriber failed")


def publish_activity_event(
    store: Any,
    *,
    event_type: str,
    project_slug: str | None = None,
    work_id: str | None = None,
    thread_id: str | None = None,
    actor: str | None = None,
    source: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
    bus: EventBus | None = None,
    created_at: str | None = None,
) -> ActivityEvent | None:
    """Persist a sanitized activity event after a durable commit; fan out if new.

    Returns the stored event, or ``None`` when an idempotency key already exists
    (sync echo / duplicate).
    """
    event = ActivityEvent(
        id=uuid4().hex,
        schema_version=EVENT_SCHEMA_VERSION,
        event_type=str(event_type).strip(),
        created_at=created_at or utcnow_iso(),
        project_slug=(project_slug or None),
        work_id=work_id or thread_id,
        thread_id=thread_id,
        actor=safe_actor(actor),
        source=safe_actor(source),
        idempotency_key=(str(idempotency_key).strip()[:200] if idempotency_key else None),
        metadata=sanitize_event_metadata(metadata),
    )
    if not event.event_type:
        raise ValueError("event_type required")
    stored = store.append_activity_event(event)
    if stored is None:
        return None
    if bus is not None:
        bus.publish(stored)
    return stored


def events_to_json_line(event: ActivityEvent) -> str:
    return json.dumps(event.invalidation_hint(), separators=(",", ":"), ensure_ascii=False)
