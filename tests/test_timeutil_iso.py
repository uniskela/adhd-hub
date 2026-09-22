"""UTC ISO normalization for Hub timestamps (My Work / Notes display)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from adhd_hub.config import Settings
from adhd_hub.models import ThreadUpsert
from adhd_hub.service import HubService
from adhd_hub.timeutil import ensure_aware_utc, normalize_public_timestamps, to_iso_utc


def test_to_iso_utc_aware_and_naive() -> None:
    aware = datetime(2026, 9, 23, 14, 30, 21, tzinfo=UTC)
    assert to_iso_utc(aware) == "2026-09-23T14:30:21Z"

    sydney = timezone(timedelta(hours=10))
    localish = datetime(2026, 9, 23, 0, 0, 0, tzinfo=sydney)
    assert to_iso_utc(localish) == "2026-09-22T14:00:00Z"

    naive = datetime(2026, 9, 23, 14, 30, 21)  # noqa: DTZ001 — intentional naive input
    assert to_iso_utc(naive) == "2026-09-23T14:30:21Z"


def test_to_iso_utc_date_only_and_strings() -> None:
    assert to_iso_utc(date(2026, 9, 23)) == "2026-09-23T00:00:00Z"
    assert to_iso_utc("2026-09-23") == "2026-09-23T00:00:00Z"
    assert to_iso_utc("2026-09-23T14:30:21") == "2026-09-23T14:30:21Z"
    assert to_iso_utc("2026-09-23 14:30:21") == "2026-09-23T14:30:21Z"
    assert to_iso_utc("2026-09-23T14:30:21+00:00") == "2026-09-23T14:30:21Z"
    assert ensure_aware_utc(None) is None
    assert to_iso_utc(None) == ""


def test_thread_public_dict_emits_z_utc_not_naive_midnight(tmp_path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    thread = service.store.upsert_thread(
        ThreadUpsert(summary="Stamp", project_slug="demo", origin="forge-inbox")
    )
    # Simulate a legacy naive midnight row (date-only coerce path).
    with service.store._conn() as conn:
        conn.execute(
            "UPDATE threads SET updated_at = ?, source_imported_at = ? WHERE id = ?",
            ("2026-09-23T00:00:00", "2026-09-23T10:15:30", thread.id),
        )
    refreshed = service.store.get_thread(thread.id)
    assert refreshed is not None
    pub = service.thread_public_dict(refreshed)
    assert pub["updated_at"] == "2026-09-23T00:00:00Z"
    assert pub["source_imported_at"] == "2026-09-23T10:15:30Z"
    assert pub["updated_at"].endswith("Z")
    assert pub["source_imported_at"] != "2026-09-23T00:00:00Z"


def test_normalize_public_timestamps_rewrites_keys() -> None:
    data = {
        "updated_at": "2026-09-23T14:30:21",
        "source_imported_at": datetime(2026, 9, 23, 1, 2, 3, tzinfo=UTC),
        "other": "keep",
    }
    normalize_public_timestamps(data)
    assert data["updated_at"] == "2026-09-23T14:30:21Z"
    assert data["source_imported_at"] == "2026-09-23T01:02:03Z"
    assert data["other"] == "keep"
