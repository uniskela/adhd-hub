from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.events import (
    EVENT_SCHEMA_VERSION,
    FORGE_RECONCILE_FAILED,
    FORGE_RECONCILE_SUCCEEDED,
    THREAD_COMPLETED,
    THREAD_CREATED,
    THREAD_PROGRESS_UPDATED,
    EventBus,
    publish_activity_event,
    sanitize_event_metadata,
)
from adhd_hub.models import ProgressUpsert
from adhd_hub.service import HubService
from adhd_hub.thread_state import state_fingerprint


@pytest.fixture
def service(tmp_path: Path) -> HubService:
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="test-token",
        stale_days=3,
        digest_limit=5,
        overlap_limit=5,
    )
    return HubService(settings)


def test_sanitize_drops_secrets_paths_and_private_urls() -> None:
    cleaned = sanitize_event_metadata(
        {
            "status": "open",
            "token": "super-secret",
            "api_key": "x",
            "workspace_path": "/home/me/code",
            "transcript": "full chat dump",
            "error": "timeout talking to api.github.com",
            "hub_url": "https://127.0.0.1:8787",
            "fingerprint": "abc123",
            "nested_secret": {"password": "nope", "ok": True},
        }
    )
    assert cleaned["status"] == "open"
    assert cleaned["fingerprint"] == "abc123"
    assert cleaned["error"] == "timeout talking to api.github.com"
    assert "token" not in cleaned
    assert "api_key" not in cleaned
    assert "workspace_path" not in cleaned
    assert "transcript" not in cleaned
    assert "hub_url" not in cleaned


def test_publish_persists_and_idempotent(service: HubService) -> None:
    first = publish_activity_event(
        service.store,
        event_type=THREAD_PROGRESS_UPDATED,
        project_slug="demo",
        thread_id="t1",
        source="api",
        idempotency_key="thread.progress_updated:t1:fp1",
        metadata={"status": "open", "token": "leak"},
        bus=service.event_bus,
    )
    assert first is not None
    assert first.schema_version == EVENT_SCHEMA_VERSION
    assert "token" not in first.metadata

    second = publish_activity_event(
        service.store,
        event_type=THREAD_PROGRESS_UPDATED,
        project_slug="demo",
        thread_id="t1",
        source="api",
        idempotency_key="thread.progress_updated:t1:fp1",
        metadata={"status": "open"},
        bus=service.event_bus,
    )
    assert second is None
    rows = service.store.list_recent_activity_events(limit=10)
    assert len(rows) == 1
    assert rows[0].id == first.id


def test_upsert_progress_and_done_publish_events(service: HubService) -> None:
    out = service.upsert_progress(
        ProgressUpsert(
            project_slug="ledger-demo",
            title="Ship ledger",
            goal="Land B3.1",
            focus="events table",
            source_tool="cursor",
            create_thread_if_missing=True,
        )
    )
    assert out["thread_id"]
    created = [
        e
        for e in service.store.list_recent_activity_events(limit=20)
        if e.event_type == THREAD_CREATED
    ]
    assert created
    assert created[0].thread_id == out["thread_id"]
    assert created[0].metadata.get("fingerprint")

    thread = service.store.get_thread(out["thread_id"])
    assert thread is not None
    fp = state_fingerprint(thread)

    # Echo with same structured state should collapse via fingerprint key.
    service.upsert_progress(
        ProgressUpsert(
            project_slug="ledger-demo",
            thread_id=thread.id,
            title=thread.summary,
            goal=thread.goal,
            focus=thread.focus,
            next_steps=list(thread.next_steps or []),
            blocked_reason=thread.blocked_reason,
            resume_step=thread.resume_step,
            source_tool="cursor",
        )
    )
    progress_rows = [
        e
        for e in service.store.list_recent_activity_events(limit=50)
        if e.event_type == THREAD_PROGRESS_UPDATED and e.thread_id == thread.id
    ]
    # Same fingerprint → at most one progress_updated row for that key.
    keys = {e.idempotency_key for e in progress_rows}
    assert f"{THREAD_PROGRESS_UPDATED}:{thread.id}:{fp}" in keys or not progress_rows

    done = service.mark_done(thread.id, note="Shipped.")
    assert done and done.status.value == "done"
    completed = [
        e
        for e in service.store.list_recent_activity_events(limit=20)
        if e.event_type == THREAD_COMPLETED and e.thread_id == thread.id
    ]
    assert len(completed) == 1


def test_forge_reconcile_outcome_events(service: HubService) -> None:
    service._record_forge_reconcile_outcome(
        ok=True,
        project_slug=None,
        result={"reconcile": [{"applied": True}, {"applied": False, "reason": "fingerprint_match"}]},
    )
    service._record_forge_reconcile_outcome(
        ok=False,
        project_slug="demo",
        error="boom /tmp/secret/path leaked",
    )
    ok_rows = [
        e
        for e in service.store.list_recent_activity_events(limit=20)
        if e.event_type == FORGE_RECONCILE_SUCCEEDED
    ]
    fail_rows = [
        e
        for e in service.store.list_recent_activity_events(limit=20)
        if e.event_type == FORGE_RECONCILE_FAILED
    ]
    assert ok_rows
    assert fail_rows
    # Absolute path scrubbed from error string.
    assert "/tmp/" not in (fail_rows[0].metadata.get("error") or "")
    health = service.sync_health()
    assert health["forge"]["last_success"]
    assert health["forge"]["last_failure"]
    assert health["recent_changes"]


def test_sse_auth_and_sync_health_api(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="secret",
        host="127.0.0.1",
        port=8787,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        denied = client.get("/api/events/stream")
        assert denied.status_code == 401

        event = app.state.service.publish_hub_event(
            THREAD_PROGRESS_UPDATED,
            project_slug="sse",
            thread_id="t-sse",
            source="api",
            idempotency_key="sse-catchup-1",
            metadata={"status": "open", "token": "nope"},
        )
        assert event is not None
        assert "token" not in event.metadata

        # Catch-up substrate used by SSE Last-Event-ID replay.
        caught = app.state.service.store.list_activity_events(
            limit=10, after_id=event.id
        )
        assert caught == []
        unknown = app.state.service.store.list_activity_events(
            limit=10, after_id="00000000000000000000000000000000"
        )
        assert unknown == []
        # Known id still allows listing newer siblings once another event exists.
        newer = app.state.service.publish_hub_event(
            THREAD_PROGRESS_UPDATED,
            project_slug="sse",
            thread_id="t-sse-newer",
            source="api",
            idempotency_key="sse-catchup-2",
            metadata={"status": "open"},
        )
        assert newer is not None
        after_known = app.state.service.store.list_activity_events(
            limit=10, after_id=event.id
        )
        assert any(e.id == newer.id for e in after_known)

        # Live fan-out used by the SSE subscriber path.
        seen: list[str] = []
        unsub = app.state.service.event_bus.subscribe(lambda e: seen.append(e.id))
        live = app.state.service.publish_hub_event(
            THREAD_PROGRESS_UPDATED,
            project_slug="sse",
            thread_id="t-sse-2",
            source="api",
            idempotency_key="sse-live-1",
            metadata={"status": "open"},
        )
        unsub()
        assert live is not None
        assert live.id in seen

        health = client.get(
            "/api/sync-health", headers={"Authorization": "Bearer secret"}
        )
        assert health.status_code == 200
        body = health.json()
        assert "forge" in body
        assert "jobs" in body
        assert "recent_changes" in body
        assert body["live_ui"]["transport"] == "sse"
        assert any(item.get("thread_id") == "t-sse" for item in body["recent_changes"])

        listed = client.get(
            "/api/events?limit=5", headers={"Authorization": "Bearer secret"}
        )
        assert listed.status_code == 200
        assert listed.json()["events"]


def test_event_bus_fanout() -> None:
    bus = EventBus()
    seen: list[str] = []
    unsub = bus.subscribe(lambda e: seen.append(e.id))
    from adhd_hub.events import ActivityEvent

    event = ActivityEvent(
        id="e1",
        schema_version=1,
        event_type=THREAD_CREATED,
        created_at="2026-01-01T00:00:00+00:00",
    )
    bus.publish(event)
    assert seen == ["e1"]
    unsub()
    bus.publish(event)
    assert seen == ["e1"]
