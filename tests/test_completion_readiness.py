"""Deterministic local completion readiness for agent end-of-task routing."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from adhd_hub.config import Settings
from adhd_hub.models import ProgressUpsert, Thread, ThreadStatus, ThreadUpsert
from adhd_hub.service import HubService
from adhd_hub.thread_state import compact_thread_dict, completion_readiness


@pytest.fixture
def service(tmp_path: Path) -> HubService:
    return HubService(
        Settings(
            data_dir=tmp_path / "data",
            auth_token="test-token",
            stale_days=3,
            digest_limit=5,
            overlap_limit=5,
        )
    )


def _thread(**overrides: object) -> Thread:
    now = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    base = {
        "id": "t1",
        "summary": "Ship feature",
        "status": ThreadStatus.open,
        "created_at": now,
        "updated_at": now,
        "next_steps": [],
    }
    base.update(overrides)
    return Thread(**base)  # type: ignore[arg-type]


def test_completion_ready_when_open_and_clear() -> None:
    result = completion_readiness(_thread(goal="Open a review-ready PR", focus=None))
    assert result == {"ready": True, "reasons": []}


def test_completion_not_ready_when_next_steps_remain() -> None:
    result = completion_readiness(_thread(next_steps=["Merge the PR", "Verify deploy"]))
    assert result["ready"] is False
    assert "next steps remain" in result["reasons"]


def test_completion_not_ready_when_paused() -> None:
    result = completion_readiness(
        _thread(paused_at=datetime(2026, 3, 1, 13, 0, tzinfo=UTC), resume_step="Fix CI")
    )
    assert result["ready"] is False
    assert "thread paused" in result["reasons"]


def test_completion_not_ready_when_blocked() -> None:
    result = completion_readiness(
        _thread(status=ThreadStatus.blocked, blocked_reason="Waiting on review")
    )
    assert result["ready"] is False
    assert "thread blocked" in result["reasons"]
    assert "blocked reason set" in result["reasons"]


def test_resume_step_alone_does_not_block_ready() -> None:
    """resume_step can be historical context; do not treat it as unfinished work alone."""
    result = completion_readiness(_thread(resume_step="Previously: open oauth.py", next_steps=[]))
    assert result["ready"] is True
    assert result["reasons"] == []


def test_done_thread_is_ready() -> None:
    result = completion_readiness(_thread(status=ThreadStatus.done))
    assert result == {"ready": True, "reasons": []}


def test_compact_and_public_include_completion(service: HubService) -> None:
    thread = service.upsert_thread(
        ThreadUpsert(
            summary="OAuth",
            project_slug="adhd-hub",
            goal="Ship OAuth",
            next_steps=["Write docs"],
        )
    )
    compact = compact_thread_dict(thread)
    assert compact["completion"]["ready"] is False
    assert "next steps remain" in compact["completion"]["reasons"]

    public = service.thread_public_dict(thread)
    assert public["completion"]["ready"] is False
    assert "id" in public and "summary" in public  # backward compatible keys


def test_session_digest_items_include_completion(service: HubService) -> None:
    service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            title="OAuth",
            goal="Ship OAuth",
            next_steps=["Token endpoint"],
            content="checkpoint",
        )
    )
    digest = service.session_digest(query="oauth")
    dumped = digest.model_dump(mode="json")
    assert dumped["items"]
    item = dumped["items"][0]
    assert item["goal"] == "Ship OAuth"
    assert item["completion"]["ready"] is False
    assert "next steps remain" in item["completion"]["reasons"]


def test_mark_done_and_pause_unchanged(service: HubService) -> None:
    tid = service.upsert_thread(
        ThreadUpsert(summary="Finishable", project_slug="adhd-hub", goal="Done")
    ).id
    paused = service.pause_thread(tid, "Come back to polish")
    assert paused.resume_step == "Come back to polish"
    assert paused.paused_at is not None
    assert completion_readiness(paused)["ready"] is False

    # Clear unfinished signals then mark done (pause leaves resume; mark_done still works).
    service.upsert_progress(
        ProgressUpsert(
            thread_id=tid,
            project_slug="adhd-hub",
            next_steps=[],
            content="cleared",
        )
    )
    done = service.mark_done(tid, note="Shipped")
    assert done is not None
    assert done.status == ThreadStatus.done
