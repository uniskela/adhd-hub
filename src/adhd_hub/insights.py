"""Activity insights Slice A — ledger-backed period totals (reflection only)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from adhd_hub.events import (
    THREAD_COMPLETED,
    THREAD_CREATED,
    THREAD_PAUSED,
    THREAD_PROGRESS_UPDATED,
)

# Person-facing Hub activity — never forge reconcile echoes.
INSIGHT_EVENT_TYPES = frozenset(
    {
        THREAD_CREATED,
        THREAD_COMPLETED,
        THREAD_PROGRESS_UPDATED,
        THREAD_PAUSED,
    }
)

_EMPTY_COUNTS = {
    "created": 0,
    "completed": 0,
    "progress": 0,
    "paused": 0,
    "projects_touched": 0,
}


def _empty_counts() -> dict[str, int]:
    return dict(_EMPTY_COUNTS)


def period_bounds(today: date) -> dict[str, tuple[date, date]]:
    """Inclusive [start, end] dates for insight windows (local calendar)."""
    month_start = today.replace(day=1)
    return {
        "today": (today, today),
        "last_7": (today - timedelta(days=6), today),
        "last_30": (today - timedelta(days=29), today),
        "month": (month_start, today),
    }


def local_day(iso_ts: str, zone: ZoneInfo) -> date | None:
    try:
        return datetime.fromisoformat(iso_ts).astimezone(zone).date()
    except ValueError:
        return None


def bucket_for_event_type(event_type: str) -> str | None:
    if event_type == THREAD_CREATED:
        return "created"
    if event_type == THREAD_COMPLETED:
        return "completed"
    if event_type == THREAD_PROGRESS_UPDATED:
        return "progress"
    if event_type == THREAD_PAUSED:
        return "paused"
    return None


def aggregate_insight_rows(
    rows: list[dict[str, Any]],
    *,
    timezone: str,
    chart_days: int = 14,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Build period totals + chart series from raw event rows.

    Each row: ``{event_type, created_at, project_slug}``.
    """
    from adhd_hub.timeutil import resolve_zone

    zone = resolve_zone(timezone)
    today = as_of or datetime.now(zone).date()
    bounds = period_bounds(today)
    periods = {name: _empty_counts() for name in bounds}
    period_projects: dict[str, set[str]] = {name: set() for name in bounds}

    chart_start = today - timedelta(days=max(1, chart_days) - 1)
    days_map: dict[str, dict[str, Any]] = {}
    for i in range(max(1, chart_days)):
        d = (chart_start + timedelta(days=i)).isoformat()
        days_map[d] = {"date": d, "added": 0, "finished": 0}

    for row in rows:
        event_type = str(row.get("event_type") or "")
        if event_type not in INSIGHT_EVENT_TYPES:
            continue
        bucket = bucket_for_event_type(event_type)
        if not bucket:
            continue
        day = local_day(str(row.get("created_at") or ""), zone)
        if day is None:
            continue
        slug = (row.get("project_slug") or "").strip() or None
        for name, (start, end) in bounds.items():
            if start <= day <= end:
                periods[name][bucket] += 1
                if slug:
                    period_projects[name].add(slug)
        key = day.isoformat()
        if key in days_map:
            if event_type == THREAD_CREATED:
                days_map[key]["added"] += 1
            elif event_type == THREAD_COMPLETED:
                days_map[key]["finished"] += 1

    for name, projects in period_projects.items():
        periods[name]["projects_touched"] = len(projects)

    return {
        "timezone": timezone,
        "as_of": today.isoformat(),
        "source": "activity_events",
        "periods": periods,
        "added_vs_finished": [days_map[k] for k in sorted(days_map.keys())],
    }
