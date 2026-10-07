"""Sample pack: load alongside real data, no-op when owned, remove only pack rows."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.models import ProjectUpsert, ThreadUpsert
from adhd_hub.sample_data import DEMO_SOURCE_TOOL, SAMPLE_PROJECT_SLUGS, sample_payload
from adhd_hub.service import HubService


def _client(tmp_path: Path, *, seed_demo: bool = False) -> tuple[TestClient, Settings]:
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="test-token-sample-data",
        forge_provider="none",
        openclaw_webhook_url=None,
        seed_demo=seed_demo,
    )
    app = create_app(settings)
    return TestClient(app), settings


def test_sample_payload_is_generic() -> None:
    data = sample_payload()
    assert {p["slug"] for p in data["projects"]} == set(SAMPLE_PROJECT_SLUGS)
    assert all(t["source_tool"] == DEMO_SOURCE_TOOL for t in data["threads"])
    blob = repr(data).lower()
    assert "pike" not in blob
    assert "@" not in blob


def test_load_is_noop_when_already_present(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    headers = {"Authorization": "Bearer test-token-sample-data"}
    first = client.post("/api/sample-data/load", headers=headers)
    assert first.status_code == 200
    assert first.json()["already_loaded"] is False
    assert first.json()["loaded"] is True
    second = client.post("/api/sample-data/load", headers=headers)
    assert second.status_code == 200
    body = second.json()
    assert body["already_loaded"] is True
    assert body["message"] == "Sample data already loaded"
    status = client.get("/api/sample-data", headers=headers).json()
    assert status["loaded"] is True
    assert status["owned"] is True


def test_load_does_not_touch_real_projects(tmp_path: Path) -> None:
    client, settings = _client(tmp_path)
    service = HubService(settings)
    service.upsert_project(ProjectUpsert(slug="my-real-work", title="My real work"))
    service.store.upsert_thread(
        ThreadUpsert(
            summary="Ship the real feature",
            project_slug="my-real-work",
            source_tool="web",
            focus="Write the test",
            resume_step="Write the test",
        )
    )
    # A real thread that reuses demo source_tool must survive Remove.
    service.store.upsert_thread(
        ThreadUpsert(
            summary="Not sample",
            project_slug="my-real-work",
            source_tool=DEMO_SOURCE_TOOL,
            focus="Keep me",
            resume_step="Keep me",
        )
    )
    headers = {"Authorization": "Bearer test-token-sample-data"}
    assert client.post("/api/sample-data/load", headers=headers).status_code == 200
    assert client.post("/api/sample-data/remove", headers=headers).status_code == 200
    assert service.store.get_project("my-real-work") is not None
    real = [
        t
        for t in service.store.list_threads(status=None, limit=50)
        if t.summary in {"Ship the real feature", "Not sample"}
    ]
    assert len(real) == 2
    for slug in SAMPLE_PROJECT_SLUGS:
        assert service.store.get_project(slug) is None


def test_occupied_sample_slug_without_pack_meta_conflicts(tmp_path: Path) -> None:
    client, settings = _client(tmp_path)
    service = HubService(settings)
    service.upsert_project(
        ProjectUpsert(slug="sample-demo-site", title="My coincidental project")
    )
    headers = {"Authorization": "Bearer test-token-sample-data"}
    res = client.post("/api/sample-data/load", headers=headers)
    assert res.status_code == 409
    assert service.store.get_project("sample-demo-site").title == "My coincidental project"


def test_seed_demo_env_loads_on_boot(tmp_path: Path) -> None:
    client, _settings = _client(tmp_path, seed_demo=True)
    headers = {"Authorization": "Bearer test-token-sample-data"}
    with client:
        status = client.get("/api/sample-data", headers=headers).json()
        assert status["loaded"] is True
