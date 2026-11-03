"""Activity insights Slice A — ledger aggregation (#72 / #343)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.events import (
    FORGE_RECONCILE_SUCCEEDED,
    THREAD_COMPLETED,
    THREAD_CREATED,
    THREAD_PROGRESS_UPDATED,
    publish_activity_event,
)
from adhd_hub.insights import aggregate_insight_rows
from adhd_hub.service import HubService


def test_aggregate_ignores_forge_reconcile_and_buckets_periods() -> None:
    zone = ZoneInfo("UTC")
    today = datetime.now(zone).date()
    mid = datetime(today.year, today.month, today.day, 12, 0, tzinfo=UTC)
    older = mid - timedelta(days=10)
    rows = [
        {"event_type": THREAD_CREATED, "created_at": mid.isoformat(), "project_slug": "alpha"},
        {"event_type": THREAD_COMPLETED, "created_at": mid.isoformat(), "project_slug": "alpha"},
        {
            "event_type": THREAD_PROGRESS_UPDATED,
            "created_at": mid.isoformat(),
            "project_slug": "beta",
        },
        {
            "event_type": FORGE_RECONCILE_SUCCEEDED,
            "created_at": mid.isoformat(),
            "project_slug": "alpha",
        },
        {
            "event_type": THREAD_COMPLETED,
            "created_at": older.isoformat(),
            "project_slug": "gamma",
        },
    ]
    out = aggregate_insight_rows(rows, timezone="UTC", chart_days=14)
    assert out["source"] == "activity_events"
    assert out["periods"]["today"]["created"] == 1
    assert out["periods"]["today"]["completed"] == 1
    assert out["periods"]["today"]["progress"] == 1
    assert out["periods"]["today"]["projects_touched"] == 2
    assert out["periods"]["last_30"]["completed"] == 2
    assert out["periods"]["last_30"]["projects_touched"] == 3
    # Forge reconcile must not inflate chart finished counts.
    finished_today = next(
        d for d in out["added_vs_finished"] if d["date"] == today.isoformat()
    )
    assert finished_today["finished"] == 1
    assert finished_today["added"] == 1


def test_list_insight_event_rows_accepts_local_since_boundary(tmp_path: Path) -> None:
    """Local +02:00 midnight must not drop UTC rows from the prior UTC calendar day."""
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="secret"))
    bus = service.event_bus
    # Local 2026-10-21 00:30+02:00 == 2026-10-20 22:30Z
    event_at = datetime(2026, 10, 20, 22, 30, tzinfo=UTC)
    publish_activity_event(
        service.store,
        event_type=THREAD_CREATED,
        project_slug="tz",
        thread_id="t-tz",
        source="api",
        idempotency_key="tz:created",
        bus=bus,
    )
    with service.store._conn() as conn:
        conn.execute(
            "UPDATE activity_events SET created_at = ? WHERE thread_id = ?",
            (event_at.isoformat(), "t-tz"),
        )
    local_since = "2026-10-21T00:00:00+02:00"
    # Lexicographic compare against UTC would exclude this row; UTC normalize must keep it.
    rows = service.store.list_insight_event_rows(
        since_iso=local_since,
        event_types=[THREAD_CREATED],
    )
    assert len(rows) == 1
    assert rows[0]["created_at"] == event_at.isoformat()


def test_insights_include_all_events_in_busy_periods(tmp_path: Path, monkeypatch) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="secret"))
    now = datetime(2026, 11, 2, 12, tzinfo=UTC)
    monkeypatch.setattr("adhd_hub.store.utcnow", lambda: now)
    with service.store._conn() as conn:
        conn.executemany(
            "INSERT INTO activity_events "
            "(id, schema_version, event_type, created_at, project_slug, source) "
            "VALUES (?, 1, ?, ?, ?, ?)",
            ((str(i), THREAD_COMPLETED, now.isoformat(), "busy", "api" if i % 2 else "forge")
             for i in range(20_001)),
        )
    insights = service.activity_insights()
    assert insights["periods"]["today"]["completed"] == 20_001
    assert insights["completion_days"][-1]["completed"] == 20_001
    assert sum(day["finished"] for day in insights["added_vs_finished"]) == 20_001


def test_completion_calendar_covers_twelve_local_weeks(tmp_path: Path, monkeypatch) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="secret"))
    from adhd_hub.prefs import HubPrefs

    service.save_prefs(HubPrefs(timezone="Europe/Helsinki"))
    now = datetime(2026, 11, 1, 22, 30, tzinfo=UTC)  # Monday locally.
    monkeypatch.setattr("adhd_hub.store.utcnow", lambda: now)
    with service.store._conn() as conn:
        conn.executemany(
            "INSERT INTO activity_events (id, schema_version, event_type, created_at) "
            "VALUES (?, 1, ?, ?)",
            [
                ("first", THREAD_COMPLETED, "2026-08-16T21:30:00+00:00"),
                ("before", THREAD_COMPLETED, "2026-08-16T20:30:00+00:00"),
                ("today", THREAD_COMPLETED, now.isoformat()),
                ("echo", FORGE_RECONCILE_SUCCEEDED, now.isoformat()),
            ],
        )
    overview = service.overview()
    days = overview["insights"]["completion_days"]
    assert len(days) == 78  # Eleven full weeks, plus the current Monday.
    assert days[0] == {"date": "2026-08-17", "completed": 1}
    assert days[1] == {"date": "2026-08-18", "completed": 0}
    assert days[-1] == {"date": "2026-11-02", "completed": 1}
    assert sum(day["completed"] for day in days) == 2
    assert len(overview["added_vs_finished"]) == 14


def test_completion_calendar_handles_dst_and_midnight() -> None:
    from datetime import date

    rows = [
        {"event_type": THREAD_COMPLETED, "created_at": stamp}
        for stamp in (
            "2026-11-01T05:30:00+00:00",  # First 01:30 in New York.
            "2026-11-01T06:30:00+00:00",  # Repeated 01:30 after DST ends.
            "2026-11-02T04:59:00+00:00",  # Still Sunday locally.
            "2026-11-02T05:00:00+00:00",  # Monday midnight.
        )
    ]
    out = aggregate_insight_rows(rows, timezone="America/New_York", as_of=date(2026, 11, 2))
    assert out["completion_days"][-2:] == [
        {"date": "2026-11-01", "completed": 3},
        {"date": "2026-11-02", "completed": 1},
    ]


def test_overview_insights_from_persisted_events(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="secret"))
    bus = service.event_bus
    publish_activity_event(
        service.store,
        event_type=THREAD_CREATED,
        project_slug="demo",
        thread_id="t-new",
        source="api",
        idempotency_key="insight:created:t-new",
        bus=bus,
    )
    publish_activity_event(
        service.store,
        event_type=THREAD_COMPLETED,
        project_slug="demo",
        thread_id="t-done",
        source="api",
        idempotency_key="insight:completed:t-done",
        bus=bus,
    )
    publish_activity_event(
        service.store,
        event_type=FORGE_RECONCILE_SUCCEEDED,
        project_slug="demo",
        source="forge",
        idempotency_key="insight:forge:1",
        metadata={"ok": True},
        bus=bus,
    )
    overview = service.overview()
    insights = overview["insights"]
    assert insights["periods"]["today"]["created"] == 1
    assert insights["periods"]["today"]["completed"] == 1
    assert insights["periods"]["today"]["projects_touched"] == 1
    series = overview["added_vs_finished"]
    assert any(d["added"] or d["finished"] for d in series)
    assert sum(d["finished"] for d in series) == 1


def test_api_thread_mutations_feed_insights_without_retry_echoes(tmp_path: Path) -> None:
    with TestClient(create_app(Settings(data_dir=tmp_path, auth_token="test-token"))) as client:
        headers = {"Authorization": "Bearer test-token"}
        payload = {"summary": "API completion", "project_slug": "demo", "source_tool": "web"}
        created = client.post("/api/threads", headers=headers, json=payload)
        assert created.status_code == 200
        payload.update(id=created.json()["id"], status="done")
        for _ in range(2):
            assert client.post("/api/threads", headers=headers, json=payload).status_code == 200
        overview = client.get("/api/overview", headers=headers).json()
        assert overview["insights"]["periods"]["today"]["created"] == 1
        assert overview["insights"]["periods"]["today"]["completed"] == 1
        assert overview["insights"]["completion_days"][-1]["completed"] == 1
        events = client.get("/api/events", headers=headers).json()["events"]
        assert all(event["source"] == "web" for event in events)
