"""Activity insights Slice A — ledger aggregation (#72 / #343)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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


def test_list_insight_event_rows_keeps_newest_when_capped(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="secret"))
    bus = service.event_bus
    base = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    for i in range(5):
        publish_activity_event(
            service.store,
            event_type=THREAD_CREATED,
            project_slug="cap",
            thread_id=f"t-{i}",
            source="api",
            idempotency_key=f"cap:created:{i}",
            bus=bus,
        )
        with service.store._conn() as conn:
            conn.execute(
                "UPDATE activity_events SET created_at = ? WHERE thread_id = ?",
                ((base + timedelta(hours=i)).isoformat(), f"t-{i}"),
            )
    rows = service.store.list_insight_event_rows(
        since_iso=base.isoformat(),
        event_types=[THREAD_CREATED],
        limit=2,
    )
    stamps = [r["created_at"] for r in rows]
    assert stamps == [
        (base + timedelta(hours=3)).isoformat(),
        (base + timedelta(hours=4)).isoformat(),
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
