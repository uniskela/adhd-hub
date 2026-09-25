"""Wave 7 stale-thread triage: soft confirm / snooze, never auto-dismiss."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.models import ThreadStatus, ThreadUpsert
from adhd_hub.service import HubService


def _service(tmp_path: Path) -> HubService:
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="test-token",
        stale_days=3,
        remind_cooldown_days=3,
        digest_max_nudge=2,
    )
    return HubService(settings)


def _make_stale(service: HubService, *, summary: str = "Stale draft") -> str:
    thread = service.upsert_thread(
        ThreadUpsert(summary=summary, status=ThreadStatus.open, project_slug="demo")
    )
    old = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    with service.store._conn() as conn:
        conn.execute(
            "UPDATE threads SET updated_at = ?, last_reminded_at = NULL, "
            "triage_snooze_until = NULL WHERE id = ?",
            (old, thread.id),
        )
    return thread.id


def test_confirm_relevant_quiets_without_dismiss(tmp_path: Path) -> None:
    service = _service(tmp_path)
    tid = _make_stale(service)
    assert any(t.id == tid for t in service.list_stale_threads())
    pub = service.thread_public_dict(service.store.get_thread(tid))
    assert pub["needs_triage"] is True

    confirmed = service.confirm_thread_relevant(tid)
    assert confirmed.status == ThreadStatus.open
    assert confirmed.last_reminded_at is not None
    assert confirmed.triage_snooze_until is None
    assert tid not in {t.id for t in service.list_stale_threads()}
    assert service.thread_public_dict(confirmed)["needs_triage"] is False


def test_snooze_triage_keeps_open_and_excludes_from_stale(tmp_path: Path) -> None:
    service = _service(tmp_path)
    tid = _make_stale(service, summary="Parked idea")
    snoozed = service.snooze_thread_triage(tid, days=7)
    assert snoozed.status == ThreadStatus.open
    assert snoozed.triage_snooze_until is not None
    assert snoozed.triage_snooze_until > datetime.now(UTC)
    assert tid not in {t.id for t in service.list_stale_threads()}
    assert service.thread_public_dict(snoozed)["needs_triage"] is False


def test_triage_never_auto_dismisses(tmp_path: Path) -> None:
    service = _service(tmp_path)
    tid = _make_stale(service)
    service.confirm_thread_relevant(tid)
    tid2 = _make_stale(service, summary="Another")
    service.snooze_thread_triage(tid2, days=3)
    for thread_id in (tid, tid2):
        thread = service.store.get_thread(thread_id)
        assert thread is not None
        assert thread.status == ThreadStatus.open
        assert thread.status != ThreadStatus.dismissed


def test_overview_includes_triage_candidates(tmp_path: Path) -> None:
    service = _service(tmp_path)
    tid = _make_stale(service)
    overview = service.overview()
    ids = {t["id"] for t in overview["triage_candidates"]}
    assert tid in ids
    assert all(t.get("needs_triage") for t in overview["triage_candidates"])


def test_repeat_triage_publishes_distinct_activity_events(tmp_path: Path) -> None:
    """Repeat confirm/snooze after cooldown must not collapse via idempotency."""
    from adhd_hub.events import THREAD_TRIAGE_CONFIRMED, THREAD_TRIAGE_SNOOZED

    service = _service(tmp_path)
    tid = _make_stale(service, summary="Repeatable triage")

    service.confirm_thread_relevant(tid)
    # Simulate cooldown expiry so a second confirm is meaningful.
    old = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    with service.store._conn() as conn:
        conn.execute(
            "UPDATE threads SET updated_at = ?, last_reminded_at = ?, "
            "triage_snooze_until = NULL WHERE id = ?",
            (old, old, tid),
        )
    service.confirm_thread_relevant(tid)

    confirms = [
        e
        for e in service.store.list_activity_events(limit=50)
        if e.event_type == THREAD_TRIAGE_CONFIRMED and e.thread_id == tid
    ]
    assert len(confirms) == 2
    assert confirms[0].idempotency_key != confirms[1].idempotency_key

    tid2 = _make_stale(service, summary="Repeatable snooze")
    service.snooze_thread_triage(tid2, days=7)
    with service.store._conn() as conn:
        conn.execute(
            "UPDATE threads SET updated_at = ?, triage_snooze_until = ? WHERE id = ?",
            (old, old, tid2),
        )
    service.snooze_thread_triage(tid2, days=7)
    snoozes = [
        e
        for e in service.store.list_activity_events(limit=50)
        if e.event_type == THREAD_TRIAGE_SNOOZED and e.thread_id == tid2
    ]
    assert len(snoozes) == 2
    assert snoozes[0].idempotency_key != snoozes[1].idempotency_key


def test_triage_api_endpoints(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="test-token",
        stale_days=3,
        remind_cooldown_days=3,
    )
    app = create_app(settings)
    service = app.state.service
    tid = _make_stale(service)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer test-token"}

        confirm = client.post(f"/api/threads/{tid}/triage/confirm", headers=headers)
        assert confirm.status_code == 200
        body = confirm.json()
        assert body["status"] == "open"
        assert body["needs_triage"] is False

        tid2 = _make_stale(service, summary="Snooze me")
        snooze = client.post(
            f"/api/threads/{tid2}/triage/snooze",
            headers=headers,
            json={"days": 5},
        )
        assert snooze.status_code == 200
        snoozed = snooze.json()
        assert snoozed["status"] == "open"
        assert snoozed["triage_snooze_until"]
        assert snoozed["needs_triage"] is False
