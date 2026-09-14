"""In-process serial queue for forge sync / import jobs.

Self-hosted Hub instances get stackable jobs with visible status without Redis.
Spam-clicks enqueue instead of stomping an in-flight sync.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

JobStatus = str  # queued | running | done | failed
JobKind = str  # sync | project_sync | import | inbox_import

_MAX_HISTORY = 40


@dataclass
class ForgeJob:
    id: str
    kind: JobKind
    status: JobStatus
    target_key: str
    label: str
    message: str
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_public(self, *, queue_position: int | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {
            "job_id": self.id,
            "kind": self.kind,
            "status": self.status,
            "target_key": self.target_key,
            "label": self.label,
            "message": self.message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "payload": {
                k: v
                for k, v in self.payload.items()
                if k in {"project_slug", "overwrite_local", "limit", "close_imported", "slugs"}
            },
        }
        if queue_position is not None and self.status == "queued":
            out["queue_position"] = queue_position
        if self.status == "done" and self.result is not None:
            out["result"] = self.result
        return out


class ForgeJobQueue:
    """FIFO worker: one forge job at a time per Hub process."""

    def __init__(
        self,
        runner: Callable[[ForgeJob], dict[str, Any]],
        *,
        max_history: int = _MAX_HISTORY,
    ) -> None:
        self._runner = runner
        self._max_history = max(10, max_history)
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._pending: list[str] = []
        self._jobs: dict[str, ForgeJob] = {}
        self._order: list[str] = []
        self._stop = False
        self._worker = threading.Thread(
            target=self._loop, name="forge-job-queue", daemon=True
        )
        self._worker.start()

    def enqueue(
        self,
        kind: JobKind,
        *,
        project_slug: str | None = None,
        payload: dict[str, Any] | None = None,
        label: str | None = None,
    ) -> dict[str, Any]:
        body = dict(payload or {})
        slug = (project_slug or body.get("project_slug") or "").strip() or None
        if slug:
            body["project_slug"] = slug
        target_key = _target_key(kind, slug)
        job_label = label or _default_label(kind, slug)
        job = ForgeJob(
            id=uuid.uuid4().hex[:12],
            kind=kind,
            status="queued",
            target_key=target_key,
            label=job_label,
            message=f"Queued: {job_label}",
            created_at=time.time(),
            payload=body,
        )
        with self._wake:
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._pending.append(job.id)
            self._trim_locked()
            position = self._pending.index(job.id) + 1
            self._wake.notify()
        log.info("forge job enqueued id=%s kind=%s target=%s", job.id, kind, target_key)
        return job.to_public(queue_position=position)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            pos = None
            if job.status == "queued" and job_id in self._pending:
                pos = self._pending.index(job_id) + 1
            return job.to_public(queue_position=pos)

    def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with self._lock:
            ids = list(reversed(self._order))[:limit]
            pending_index = {jid: i + 1 for i, jid in enumerate(self._pending)}
            out: list[dict[str, Any]] = []
            for jid in ids:
                job = self._jobs.get(jid)
                if job is None:
                    continue
                out.append(job.to_public(queue_position=pending_index.get(jid)))
            return out

    def wait(self, job_id: str, *, timeout: float | None = 600.0) -> dict[str, Any]:
        """Block until job finishes (used by scheduler). Raises TimeoutError."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            public = self.get(job_id)
            if public is None:
                raise KeyError(job_id)
            if public["status"] in {"done", "failed"}:
                return public
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"forge job {job_id} timed out")
            time.sleep(0.05)

    def shutdown(self, *, wait: bool = False) -> None:
        with self._wake:
            self._stop = True
            self._wake.notify_all()
        if wait:
            self._worker.join(timeout=5)

    def _trim_locked(self) -> None:
        while len(self._order) > self._max_history:
            oldest = self._order[0]
            job = self._jobs.get(oldest)
            if job and job.status in {"queued", "running"}:
                break
            self._order.pop(0)
            self._jobs.pop(oldest, None)

    def _loop(self) -> None:
        while True:
            with self._wake:
                while not self._pending and not self._stop:
                    self._wake.wait(timeout=1.0)
                if self._stop and not self._pending:
                    return
                if not self._pending:
                    continue
                job_id = self._pending.pop(0)
                job = self._jobs.get(job_id)
                if job is None:
                    continue
                job.status = "running"
                job.started_at = time.time()
                job.message = f"Running: {job.label}"

            try:
                result = self._runner(job)
            except Exception as exc:
                log.exception("forge job failed id=%s kind=%s", job.id, job.kind)
                with self._lock:
                    job.status = "failed"
                    job.finished_at = time.time()
                    job.error = str(exc)
                    job.message = f"Failed: {job.label} — {exc}"
                continue

            with self._lock:
                job.status = "done"
                job.finished_at = time.time()
                job.result = result if isinstance(result, dict) else {"ok": True}
                job.message = _done_message(job, job.result)


def _target_key(kind: JobKind, project_slug: str | None) -> str:
    if kind == "project_sync" and project_slug:
        return f"project:{project_slug}"
    if kind == "sync":
        return "global-sync"
    if kind == "import":
        return "wiki-import"
    if kind == "inbox_import":
        return "inbox-import"
    return kind


def _default_label(kind: JobKind, project_slug: str | None) -> str:
    if kind == "project_sync" and project_slug:
        return f"Sync forge ({project_slug})"
    if kind == "sync":
        return "Sync forge"
    if kind == "import":
        return "Import from forge"
    if kind == "inbox_import":
        return "Import issue inbox"
    return kind


def _done_message(job: ForgeJob, result: dict[str, Any]) -> str:
    if job.kind in {"sync", "project_sync"}:
        warnings = result.get("warnings") or []
        uploaded = 0
        wiki = result.get("wiki")
        if isinstance(wiki, dict):
            uploaded = len(wiki.get("uploaded") or [])
        base = f"Done: {job.label}"
        if uploaded:
            base += f" ({uploaded} wiki file{'s' if uploaded != 1 else ''})"
        if warnings:
            base += f" — {len(warnings)} warning{'s' if len(warnings) != 1 else ''}"
        return base
    if job.kind == "import":
        n = len(result.get("imported") or [])
        return f"Done: imported {n} project{'s' if n != 1 else ''}"
    if job.kind == "inbox_import":
        if result.get("skipped"):
            return f"Done: inbox import skipped ({result.get('reason') or 'skipped'})"
        if result.get("error"):
            return f"Failed: inbox import — {result['error']}"
        n = int(result.get("count") or 0)
        return f"Done: imported {n} issue{'s' if n != 1 else ''}"
    return f"Done: {job.label}"
