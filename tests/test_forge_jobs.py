"""In-process forge job queue: spam-clicks enqueue instead of clobbering."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.forge.jobs import ForgeJobQueue
from adhd_hub.service import HubService


def test_forge_jobs_queue_serializes_spam_clicks(tmp_path: Path) -> None:
    svc = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    execution: list[tuple[str, int]] = []
    first_started = threading.Event()
    release_first = threading.Event()
    calls = 0

    def slow_sync():
        nonlocal calls
        calls += 1
        call = calls
        execution.append(("start", call))
        if call == 1:
            first_started.set()
            assert release_first.wait(timeout=10), "test did not release first job"
        execution.append(("finish", call))
        return {"ok": True, "wiki": {"uploaded": []}, "warnings": []}

    svc.sync_forge_now = slow_sync  # type: ignore[method-assign]

    try:
        first = svc.enqueue_forge_job("sync")
        assert first_started.wait(timeout=5), "worker did not start first job"
        second = svc.enqueue_forge_job("sync")
        third = svc.enqueue_forge_job("sync")

        # Positions count waiting jobs, not the job already running. Hold the
        # first job until these assertions finish, independent of scheduling.
        assert second["status"] == third["status"] == "queued"
        assert second["queue_position"] == 1
        assert third["queue_position"] == 2
        listed = {job["job_id"]: job for job in svc.list_forge_jobs(limit=5)}
        assert listed[first["job_id"]]["status"] == "running"
        assert "queue_position" not in listed[first["job_id"]]
        for queued, position in [(second, 1), (third, 2)]:
            assert listed[queued["job_id"]]["queue_position"] == position
            assert svc.get_forge_job(queued["job_id"])["queue_position"] == position
        assert execution == [("start", 1)]

        release_first.set()
        for job in (first, second, third):
            assert svc.wait_forge_job(job["job_id"], timeout=5)["status"] == "done"
        assert execution == [
            ("start", 1), ("finish", 1),
            ("start", 2), ("finish", 2),
            ("start", 3), ("finish", 3),
        ]
    finally:
        release_first.set()
        svc._forge_jobs.shutdown(wait=True)


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
