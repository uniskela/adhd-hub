"""In-process forge job queue: spam-clicks enqueue instead of clobbering."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.forge.jobs import ForgeJobQueue
from adhd_hub.service import HubService


def test_forge_jobs_queue_serializes_spam_clicks(tmp_path: Path) -> None:
    svc = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    started: list[str] = []
    finished: list[str] = []

    def slow_sync():
        started.append("sync")
        time.sleep(0.15)
        finished.append("sync")
        return {"ok": True, "wiki": {"uploaded": []}, "warnings": []}

    svc.sync_forge_now = slow_sync  # type: ignore[method-assign]

    first = svc.enqueue_forge_job("sync")
    second = svc.enqueue_forge_job("sync")
    assert second["status"] == "queued"
    assert second.get("queue_position") == 2

    done1 = svc.wait_forge_job(first["job_id"], timeout=5.0)
    done2 = svc.wait_forge_job(second["job_id"], timeout=5.0)
    assert done1["status"] == "done"
    assert done2["status"] == "done"
    assert started == ["sync", "sync"]
    assert finished == ["sync", "sync"]

    listed = svc.list_forge_jobs(limit=5)
    assert any(j["job_id"] == first["job_id"] for j in listed)


def test_forge_job_queue_records_failure() -> None:
    def runner(_job):
        raise RuntimeError("boom")

    q = ForgeJobQueue(runner)
    try:
        job = q.enqueue("import", label="Import")
        done = q.wait(job["job_id"], timeout=3)
        assert done["status"] == "failed"
        assert "boom" in (done.get("error") or "")
    finally:
        q.shutdown(wait=False)


def test_api_forge_sync_enqueues_job(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_token="secret")
    with TestClient(create_app(settings)) as client:
        r = client.post(
            "/api/forge/sync",
            headers={"Authorization": "Bearer secret"},
            json={},
        )
        assert r.status_code == 200
        body = r.json()
        assert "job_id" in body
        assert body["kind"] == "sync"
        assert body["status"] in {"queued", "running", "done"}

        listed = client.get(
            "/api/forge/jobs",
            headers={"Authorization": "Bearer secret"},
        )
        assert listed.status_code == 200
        assert any(j["job_id"] == body["job_id"] for j in listed.json()["jobs"])

        deadline = time.time() + 10
        final = None
        while time.time() < deadline:
            got = client.get(
                f"/api/forge/jobs/{body['job_id']}",
                headers={"Authorization": "Bearer secret"},
            )
            assert got.status_code == 200
            final = got.json()
            if final["status"] in {"done", "failed"}:
                break
            time.sleep(0.05)
        assert final is not None
        assert final["status"] == "done"
        assert isinstance(final.get("result"), dict)
