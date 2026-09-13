"""In-process forge job queue: spam-clicks enqueue instead of clobbering."""

from __future__ import annotations

import time
from pathlib import Path

from adhd_hub.config import Settings
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

    done1 = svc.wait_forge_job(first["job_id"], timeout=5.0)
    done2 = svc.wait_forge_job(second["job_id"], timeout=5.0)
    assert done1["status"] == "done"
    assert done2["status"] == "done"
    assert started == ["sync", "sync"]
    assert finished == ["sync", "sync"]

    listed = svc.list_forge_jobs(limit=5)
    assert any(j["job_id"] == first["job_id"] for j in listed)
