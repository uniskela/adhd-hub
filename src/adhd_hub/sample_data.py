"""Generic sample pack for Settings / ADHD_HUB_SEED_DEMO (never overwrites real data)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from adhd_hub.service import HubService

# Marker on sample threads created by this pack.
DEMO_SOURCE_TOOL = "demo"

# Stable slugs — Load refuses if these exist without pack ownership meta.
SAMPLE_PROJECT_SLUGS: tuple[str, ...] = (
    "sample-demo-site",
    "sample-home-admin",
    "sample-learning",
)

PACK_META_KEY = "sample_pack_v1"


def sample_payload() -> dict[str, Any]:
    """Generic Demo website / Home admin / Learning notes pack (README gallery style)."""
    projects = [
        {
            "slug": "sample-demo-site",
            "title": "Demo website",
            "tags": ["Creative", "Sample"],
        },
        {
            "slug": "sample-home-admin",
            "title": "Home admin",
            "tags": ["Personal", "Sample"],
        },
        {
            "slug": "sample-learning",
            "title": "Learning notes",
            "tags": ["Learning", "Sample"],
        },
    ]
    threads = [
        {
            "summary": "Polish the landing page",
            "project_slug": "sample-demo-site",
            "status": "open",
            "focus": "Tighten the hero copy",
            "goal": "Ship a calmer first viewport for the demo site.",
            "next_steps": ["Draft one clearer headline"],
            "resume_step": "Draft one clearer headline",
            "source_tool": DEMO_SOURCE_TOOL,
        },
        {
            "summary": "Book a dentist visit",
            "project_slug": "sample-home-admin",
            "status": "open",
            "focus": "Find a nearby clinic",
            "goal": "Schedule routine care without overthinking it.",
            "next_steps": ["Check opening hours"],
            "resume_step": "Check opening hours",
            "source_tool": DEMO_SOURCE_TOOL,
        },
        {
            "summary": "Review design notes",
            "project_slug": "sample-learning",
            "status": "open",
            "focus": "Skim last week's notes",
            "goal": "Keep learning notes scannable for the next session.",
            "next_steps": ["Write one takeaway"],
            "resume_step": "Write one takeaway",
            "source_tool": DEMO_SOURCE_TOOL,
        },
        {
            "summary": "Collect homepage ideas",
            "project_slug": "sample-demo-site",
            "status": "done",
            "focus": "Choose a direction",
            "goal": "Archive finished exploration.",
            "next_steps": ["Save three examples"],
            "resume_step": "Save three examples",
            "source_tool": DEMO_SOURCE_TOOL,
        },
    ]
    return {
        "projects": projects,
        "threads": threads,
        "stale_summary": "Book a dentist visit",
        "progress_note": {
            "project_slug": "sample-demo-site",
            "title": "Polish the landing page",
            "goal": "Ship a calmer first viewport for the demo site.",
            "focus": "Tighten the hero copy",
            "next_steps": ["Draft one clearer headline"],
            "resume_step": "Draft one clearer headline",
            "content": (
                "Sample note: keep the hero quiet — brand, one line, one CTA."
            ),
            "source_tool": DEMO_SOURCE_TOOL,
            "create_thread_if_missing": False,
        },
    }


def _read_pack_meta(service: HubService) -> dict[str, Any] | None:
    raw = service.store.get_meta(PACK_META_KEY)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def sample_data_status(service: HubService) -> dict[str, Any]:
    meta = _read_pack_meta(service)
    owned_slugs = [
        s for s in (meta or {}).get("project_slugs", []) if isinstance(s, str)
    ]
    present = [slug for slug in owned_slugs if service.store.get_project(slug)]
    thread_ids = [
        tid for tid in (meta or {}).get("thread_ids", []) if isinstance(tid, str)
    ]
    loaded = bool(meta) and set(present) == set(SAMPLE_PROJECT_SLUGS)
    return {
        "loaded": loaded,
        "sample_projects_present": present,
        "demo_thread_count": len(thread_ids) if meta else 0,
        "owned": bool(meta),
    }


def load_sample_data(service: HubService) -> dict[str, Any]:
    """Insert generic sample pack alongside existing work. No-op if pack owned."""
    from adhd_hub.models import ProgressUpsert, ProjectUpsert, ThreadUpsert

    status = sample_data_status(service)
    if status["loaded"]:
        return {
            "ok": True,
            "loaded": True,
            "already_loaded": True,
            "message": "Sample data already loaded",
        }
    occupied = [
        slug for slug in SAMPLE_PROJECT_SLUGS if service.store.get_project(slug)
    ]
    if occupied:
        return {
            "ok": False,
            "loaded": False,
            "already_loaded": False,
            "message": (
                "Sample project slugs are already in use by other data; "
                "rename or remove them before loading the sample pack."
            ),
            "occupied_slugs": occupied,
        }
    data = sample_payload()
    for project in data["projects"]:
        service.upsert_project(ProjectUpsert(**project))
    thread_ids: list[str] = []
    stale_thread_id: str | None = None
    first_open_id: str | None = None
    for thread in data["threads"]:
        row = service.store.upsert_thread(ThreadUpsert(**thread))
        thread_ids.append(row.id)
        if first_open_id is None and thread.get("status") == "open":
            first_open_id = row.id
        if thread.get("summary") == data["stale_summary"]:
            stale_thread_id = row.id
    note = dict(data["progress_note"])
    if first_open_id:
        note["thread_id"] = first_open_id
    service.upsert_progress(ProgressUpsert(**note))
    if stale_thread_id:
        stale_at = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        service.store.backdate_thread(stale_thread_id, stale_at)
    service.store.set_meta(
        PACK_META_KEY,
        {
            "project_slugs": list(SAMPLE_PROJECT_SLUGS),
            "thread_ids": thread_ids,
        },
    )
    return {
        "ok": True,
        "loaded": True,
        "already_loaded": False,
        "message": "Sample data loaded",
        "projects": len(data["projects"]),
        "threads": len(thread_ids),
        "source_tool": DEMO_SOURCE_TOOL,
    }


def remove_sample_data(service: HubService) -> dict[str, Any]:
    """Remove only pack-owned sample projects/threads (meta-tracked)."""
    from adhd_hub.models import ThreadStatus

    meta = _read_pack_meta(service)
    if not meta:
        return {
            "ok": True,
            "loaded": False,
            "message": "No sample pack to remove",
            "threads_deleted": 0,
            "progress_notes_deleted": 0,
            "projects_deleted": [],
        }
    thread_ids = [t for t in meta.get("thread_ids", []) if isinstance(t, str)]
    slugs = [
        s
        for s in meta.get("project_slugs", [])
        if isinstance(s, str) and s in SAMPLE_PROJECT_SLUGS
    ]
    threads_deleted = service.store.delete_threads_by_ids(thread_ids)
    notes_deleted = service.store.delete_progress_notes_for_slugs(slugs)
    projects_deleted: list[str] = []
    for slug in slugs:
        if not service.store.get_project(slug):
            continue
        try:
            service.delete_project(slug, delete_progress=True, delete_remote=False)
            projects_deleted.append(slug)
        except KeyError:
            continue
    service.store.delete_meta(PACK_META_KEY)
    service.wiki.rebuild_index(
        service.store.list_threads(status=ThreadStatus.open, limit=500)
    )
    return {
        "ok": True,
        "loaded": False,
        "message": "Sample data removed",
        "threads_deleted": threads_deleted,
        "progress_notes_deleted": notes_deleted,
        "projects_deleted": projects_deleted,
    }
