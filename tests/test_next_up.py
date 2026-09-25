"""Wave 7 Next-up ranking: calm cross-project pick."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.models import EnergyLevel, ThreadStatus, ThreadUpsert
from adhd_hub.next_up import pick_next_up, rank_next_up
from adhd_hub.service import HubService


def _service(tmp_path: Path) -> HubService:
    return HubService(
        Settings(data_dir=tmp_path / "data", auth_token="test-token", stale_days=3)
    )


def _age(service: HubService, thread_id: str, *, days: int) -> None:
    stamp = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with service.store._conn() as conn:
        conn.execute(
            "UPDATE threads SET updated_at = ? WHERE id = ?",
            (stamp, thread_id),
        )


def test_rank_prefers_stale_with_resume_over_fresh_high_energy(tmp_path: Path) -> None:
    service = _service(tmp_path)
    fresh = service.upsert_thread(
        ThreadUpsert(
            summary="Fresh loud work",
            status=ThreadStatus.open,
            energy=EnergyLevel.high,
            project_slug="alpha",
        )
    )
    stale = service.upsert_thread(
        ThreadUpsert(
            summary="Quiet return",
            status=ThreadStatus.open,
            energy=EnergyLevel.unknown,
            project_slug="beta",
            resume_step="Open the draft and write one sentence",
        )
    )
    _age(service, stale.id, days=10)
    stale = service.store.get_thread(stale.id)
    fresh = service.store.get_thread(fresh.id)
    assert stale is not None and fresh is not None

    pick = service.pick_next_up()
    assert pick is not None
    assert pick.id == stale.id
    assert pick.summary == "Quiet return"


def test_focus_project_honours_drift(tmp_path: Path) -> None:
    service = _service(tmp_path)
    other = service.upsert_thread(
        ThreadUpsert(
            summary="Other project stale",
            project_slug="other",
            resume_step="Do the other thing",
        )
    )
    focus = service.upsert_thread(
        ThreadUpsert(summary="Focus project open", project_slug="focus-proj")
    )
    _age(service, other.id, days=10)
    pick = service.pick_next_up(focus_project_slug="focus-proj")
    assert pick is not None
    assert pick.id == focus.id


def test_energy_filter_prefers_matching(tmp_path: Path) -> None:
    service = _service(tmp_path)
    low = service.upsert_thread(
        ThreadUpsert(summary="Low energy", energy=EnergyLevel.low, project_slug="a")
    )
    service.upsert_thread(
        ThreadUpsert(summary="High energy", energy=EnergyLevel.high, project_slug="b")
    )
    pick = service.pick_next_up(energy=EnergyLevel.low)
    assert pick is not None
    assert pick.id == low.id


def test_overview_and_api_next_up(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data", auth_token="test-token", stale_days=3
    )
    app = create_app(settings)
    service = app.state.service
    quiet = service.upsert_thread(
        ThreadUpsert(
            summary="Ask me next",
            resume_step="One tiny step",
            project_slug="demo",
        )
    )
    _age(service, quiet.id, days=8)
    service.upsert_thread(
        ThreadUpsert(summary="Brand new", energy=EnergyLevel.high, project_slug="demo")
    )

    overview = service.overview()
    assert overview["next_up"]["id"] == quiet.id

    with TestClient(app) as client:
        headers = {"Authorization": "Bearer test-token"}
        res = client.get("/api/next-up", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body["next_up"]["id"] == quiet.id
        assert body["next_up"]["summary"] == "Ask me next"


def test_rank_next_up_empty() -> None:
    assert pick_next_up([]) is None
    assert rank_next_up([]) == []
