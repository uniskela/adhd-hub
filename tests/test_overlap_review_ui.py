"""UI contract for the Possible overlap review."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "js" / "overlap_review_smoke.mjs"


def test_overlap_review_ui_smoke() -> None:
    assert FIXTURE.is_file()
    proc = subprocess.run(
        ["node", str(FIXTURE)],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "overlap_review_smoke: ok" in proc.stdout


def test_duplicate_review_api_when_present(tmp_path: Path) -> None:
    """Runs the read path once the Codex merge API is on this build.

    A 404 means this UI branch does not include that API yet. Do not merge the
    UI until this test runs without skipping.
    """
    settings = Settings(data_dir=tmp_path / "data", auth_token="secret")
    headers = {"Authorization": "Bearer secret"}
    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/threads",
            headers=headers,
            json={"summary": "Ship DNS cutover", "project_slug": "dns", "goal": "Ship DNS cutover"},
        )
        assert created.status_code == 200
        thread_id = created.json()["id"]
        listed = client.get(f"/api/threads/{thread_id}/duplicates", headers=headers)
        if listed.status_code == 404:
            pytest.skip("duplicate-thread API is not on this build yet")
        assert listed.status_code == 200
        body = listed.json()
        assert body["thread_id"] == thread_id
        assert "hits" in body
        again = client.get(f"/api/threads/{thread_id}", headers=headers)
        assert again.status_code == 200
        assert again.json()["status"] == created.json()["status"]
        assert again.json().get("merged_into") in (None, "")
