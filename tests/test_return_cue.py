"""Wave 7 return-cue coaching — deterministic, advisory, never blocking."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.models import ProgressUpsert, Thread, ThreadStatus, ThreadUpsert
from adhd_hub.return_cue import (
    HINT_MISSING,
    HINT_REPEATS_GOAL,
    HINT_VAGUE,
    assess_return_cue,
    thread_return_cue,
)
from adhd_hub.service import HubService
from adhd_hub.thread_state import compact_thread_dict

CASES = json.loads((Path(__file__).parent / "fixtures/return_cue/cases.json").read_text())


@pytest.fixture
def service(tmp_path: Path) -> HubService:
    return HubService(Settings(data_dir=tmp_path / "data", auth_token="test-token"))


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


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_cursor_return_cue_fixtures(case: dict) -> None:
    result = assess_return_cue(case["resume_step"], goal=case.get("goal"))
    assert result["quality"] == case["quality"]
    assert result["signals"] == case["signals"]
    assert result["advisory"] is True
    assert result["version"] == 1
    assert (result["hint"] is None) == (case["quality"] == "concrete")


def test_empty_cue_gets_calm_hint_and_no_invented_suggestion() -> None:
    result = assess_return_cue(None, goal="Ship the importer")
    assert result == {
        "quality": "missing",
        "signals": ["empty"],
        "hint": HINT_MISSING,
        "suggestion": None,
        "advisory": True,
        "version": 1,
    }


def test_vague_cue_hints() -> None:
    assert assess_return_cue("Continue later")["hint"] == HINT_VAGUE
    assert (
        assess_return_cue("Ship feature", title="Ship feature")["hint"] == HINT_REPEATS_GOAL
    )


def test_concrete_cue_has_no_hint_or_suggestion() -> None:
    result = assess_return_cue(
        "Open service.py, finish the failing sync test, then run pytest",
        focus="Rewrite the sync retry loop",
    )
    assert result["quality"] == "concrete"
    assert result["hint"] is None
    assert result["suggestion"] is None


def test_assessment_is_deterministic() -> None:
    kwargs = {"goal": "Ship sync", "focus": "Fix retry in sync_worker", "next_steps": ["Run pytest"]}
    assert assess_return_cue("Fix the issue", **kwargs) == assess_return_cue(
        "Fix the issue", **kwargs
    )


def test_suggestion_only_echoes_the_threads_own_fields() -> None:
    result = assess_return_cue(
        "Continue later",
        focus="Rewrite the retry loop in sync_worker",
        next_steps=["Run pytest tests/test_sync.py"],
    )
    assert result["suggestion"] == {
        "source": "focus",
        "text": "Rewrite the retry loop in sync_worker",
    }
    # A vague Focus is skipped in favour of a concrete first Next step.
    result = assess_return_cue(
        "", focus="Keep going", next_steps=["Run pytest tests/test_sync.py", "Open a PR"]
    )
    assert result["suggestion"] == {
        "source": "next_steps",
        "text": "Run pytest tests/test_sync.py",
    }
    # Nothing concrete stored → nothing offered (never invents files or commands).
    assert assess_return_cue("Fix it", focus="Keep going", next_steps=["Finish"])[
        "suggestion"
    ] is None


def test_hints_never_name_project_facts() -> None:
    for hint in (HINT_MISSING, HINT_VAGUE, HINT_REPEATS_GOAL):
        assert len(hint) <= 120
        assert "/" not in hint and ".py" not in hint and "`" not in hint


def test_finished_threads_get_no_coaching() -> None:
    assert thread_return_cue(_thread(status=ThreadStatus.done)) is None
    assert thread_return_cue(_thread(status=ThreadStatus.dismissed)) is None
    assert thread_return_cue(_thread(merged_into="t2")) is None
    assert compact_thread_dict(_thread(status=ThreadStatus.done))["return_cue"] is None
    assert thread_return_cue(_thread(status=ThreadStatus.blocked))["quality"] == "missing"


def test_agent_checkpoint_saves_vague_cue_and_returns_coaching(service: HubService) -> None:
    out = service.upsert_progress(
        ProgressUpsert(
            project_slug="alpha",
            title="Sync importer",
            goal="Importer retries survive a dropped connection",
            focus="Rewrite the retry loop in sync_worker",
            resume_step="Continue later",
            source_tool="cursor",
        )
    )
    assert out["created_thread"] is True
    thread = service.store.get_thread(out["thread_id"])
    assert thread is not None and thread.resume_step == "Continue later"
    coaching = out["thread"]["return_cue"]
    assert coaching["quality"] == "vague"
    assert coaching["suggestion"]["source"] == "focus"

    out = service.upsert_progress(
        ProgressUpsert(
            project_slug="alpha",
            thread_id=out["thread_id"],
            resume_step="Open sync_worker.py and rerun the dropped-connection test",
            source_tool="cursor",
        )
    )
    assert out["thread"]["return_cue"]["quality"] == "concrete"
    assert out["thread"]["return_cue"]["hint"] is None


def test_agent_checkpoint_without_resume_is_not_blocked(service: HubService) -> None:
    out = service.upsert_progress(
        ProgressUpsert(project_slug="alpha", title="Sync importer", goal="Ship it")
    )
    assert out["thread_id"]
    assert out["thread"]["return_cue"]["quality"] == "missing"


def test_pause_is_never_blocked_by_weak_wording(service: HubService) -> None:
    thread = service.upsert_thread(ThreadUpsert(summary="Auth fix", project_slug="alpha"))
    paused = service.pause_thread(thread.id, "Fix the issue")
    assert paused.resume_step == "Fix the issue"
    assert paused.paused_at is not None
    public = service.thread_public_dict(paused)
    assert public["return_cue"]["quality"] == "vague"
    assert public["return_cue"]["hint"] == HINT_VAGUE


def test_completion_is_independent_of_cue_quality(service: HubService) -> None:
    out = service.upsert_progress(
        ProgressUpsert(
            project_slug="alpha",
            title="Docs tidy",
            goal="README links resolve",
            resume_step="Continue later",
        )
    )
    assert out["thread"]["completion"] == {"ready": True, "reasons": []}
    done = service.mark_done(out["thread_id"])
    assert done is not None and done.status == ThreadStatus.done
    assert service.thread_public_dict(done)["return_cue"] is None


def test_coaching_uses_only_the_same_thread_context(service: HubService) -> None:
    """Unrelated threads never leak into another thread's suggestion."""
    other = service.upsert_thread(
        ThreadUpsert(
            summary="Tax return",
            project_slug="home",
            focus="Scan the P60 into the accountant portal",
            next_steps=["Email Priya the mortgage statement"],
        )
    )
    vague = service.upsert_thread(
        ThreadUpsert(summary="Auth fix", project_slug="alpha", resume_step="Fix the issue")
    )
    coaching = service.thread_public_dict(service.store.get_thread(vague.id))["return_cue"]
    assert coaching["quality"] == "vague"
    assert coaching["suggestion"] is None
    assert "P60" not in json.dumps(coaching) and "Priya" not in json.dumps(coaching)
    own = service.thread_public_dict(service.store.get_thread(other.id))["return_cue"]
    assert own["suggestion"]["text"] == "Scan the P60 into the accountant portal"


def test_read_paths_expose_coaching(service: HubService) -> None:
    service.upsert_thread(
        ThreadUpsert(
            summary="Auth fix",
            project_slug="alpha",
            workspace_path="/work/alpha",
            goal="OAuth callback handles expired state",
            resume_step="Fix the issue",
        )
    )
    digest = service.session_digest(workspace_path="/work/alpha").model_dump(mode="json")
    assert digest["items"][0]["return_cue"]["quality"] == "vague"
    assert service.overview()["next_up"]["return_cue"]["quality"] == "vague"
    assert service.agent_overview()["next_up"]["return_cue"]["signals"] == ["no_specifics"]


def test_mcp_checkpoint_pause_and_digest_carry_coaching(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_token="secret")
    headers = {
        "Authorization": "bearer secret",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as client:

        def call(name: str, arguments: dict) -> dict:
            response = client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                },
            )
            assert response.status_code == 200
            result = response.json()["result"]
            assert not result.get("isError")
            return result["structuredContent"]

        saved = call(
            "upsert_progress",
            {
                "project_slug": "alpha",
                "title": "Auth fix",
                "goal": "OAuth callback handles expired state",
                "resume_step": "Continue later",
                "source_tool": "claude-code",
            },
        )
        assert saved["thread"]["return_cue"]["quality"] == "vague"

        paused = call(
            "pause_thread",
            {
                "thread_id": saved["thread_id"],
                "next_step": "Reproduce the auth error and inspect the failing OAuth callback test",
            },
        )
        assert paused["resume_step"].startswith("Reproduce the auth error")
        assert paused["return_cue"]["quality"] == "concrete"

        digest = call("session_digest", {"query": "auth"})
        assert digest["items"][0]["return_cue"]["quality"] == "concrete"

        # REST pause mirrors MCP for the dashboard.
        response = client.post(
            f"/api/threads/{saved['thread_id']}/pause",
            headers={"Authorization": "bearer secret"},
            json={"next_step": "Fix the issue"},
        )
        assert response.status_code == 200
        assert response.json()["return_cue"]["quality"] == "vague"
