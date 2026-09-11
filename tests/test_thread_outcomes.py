from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from adhd_hub.config import Settings
from adhd_hub.models import ProgressUpsert, ThreadUpsert
from adhd_hub.service import HubService


@pytest.fixture
def service(tmp_path: Path) -> HubService:
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="test-token",
        stale_days=3,
        digest_limit=5,
        overlap_limit=5,
    )
    return HubService(settings)


def test_two_open_threads_coexist(service: HubService) -> None:
    a = service.upsert_thread(
        ThreadUpsert(
            summary="OAuth for MCP",
            project_slug="adhd-hub",
            goal="Ship MCP OAuth discovery + token endpoint",
        )
    )
    b = service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            title="v0.5.0 release",
            goal="Cut and publish v0.5.0",
            force_new_thread=True,
            content="Draft release notes",
        )
    )
    assert b["thread_id"] and b["thread_id"] != a.id
    opens = service.list_open_threads(project_slug="adhd-hub")
    assert len(opens) == 2


def test_progress_targets_only_named_thread(service: HubService) -> None:
    a = service.upsert_thread(
        ThreadUpsert(
            summary="Docs portal",
            project_slug="adhd-hub",
            goal="Publish GitHub Pages documentation portal",
            focus="Outline docs IA",
        )
    )
    b = service.upsert_thread(
        ThreadUpsert(
            summary="Settings dark UI",
            project_slug="adhd-hub",
            goal="Ship Settings page + dark UI redesign",
            focus="Sketch tokens",
        )
    )
    service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            thread_id=a.id,
            focus="Write portal landing page",
            next_steps=["Add nav", "Deploy Pages"],
            content="Landing draft in progress",
        )
    )
    a2 = service.store.get_thread(a.id)
    b2 = service.store.get_thread(b.id)
    assert a2 and a2.focus == "Write portal landing page"
    assert a2.next_steps == ["Add nav", "Deploy Pages"]
    assert b2 and b2.focus == "Sketch tokens"
    assert b2.summary == "Settings dark UI"

    service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            thread_id=b.id,
            focus="Implement dark theme tokens",
            content="Tokens half done",
        )
    )
    a3 = service.store.get_thread(a.id)
    b3 = service.store.get_thread(b.id)
    assert a3 and a3.focus == "Write portal landing page"
    assert b3 and b3.focus == "Implement dark theme tokens"


def test_ambiguous_threadless_progress_does_not_pick_newest(service: HubService) -> None:
    service.upsert_thread(
        ThreadUpsert(
            summary="OAuth",
            project_slug="adhd-hub",
            goal="Ship MCP OAuth",
        )
    )
    service.upsert_thread(
        ThreadUpsert(
            summary="Homelab deploy",
            project_slug="adhd-hub",
            goal="Deploy v0.5.0 to homelab",
        )
    )
    out = service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            title="Something unrelated",
            content="Working on a mystery task",
        )
    )
    assert out.get("needs_thread_selection") is True
    assert out.get("thread_id") is None
    assert len(out.get("candidates") or []) == 2
    assert len(service.list_open_threads(project_slug="adhd-hub")) == 2


def test_new_outcome_force_new_and_same_outcome_reuses(service: HubService) -> None:
    first = service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            title="OAuth",
            goal="Ship MCP OAuth discovery + token endpoint",
            focus="Implement discovery",
            content="Started OAuth",
        )
    )
    tid = first["thread_id"]
    assert tid
    second = service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            thread_id=tid,
            goal="Ship MCP OAuth discovery + token endpoint",
            focus="Implement token endpoint",
            next_steps=["Write tests", "Document flow"],
            content="Token endpoint WIP",
        )
    )
    assert second["thread_id"] == tid
    third = service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            title="Release v0.5.0",
            goal="Cut and publish v0.5.0",
            force_new_thread=True,
            content="Start release",
        )
    )
    assert third["thread_id"] != tid
    assert len(service.list_open_threads(project_slug="adhd-hub")) == 2


def test_focus_next_limits_and_blocked_omitted(service: HubService) -> None:
    out = service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            title="Settings UI",
            goal="Ship Settings + dark UI",
            focus="Build settings form",
            next_steps=["a", "b", "c", "d", "e"],
            content="checkpoint",
        )
    )
    thread = service.store.get_thread(out["thread_id"])
    assert thread
    assert len(thread.next_steps) == 3
    text = Path(out["progress_path"]).read_text(encoding="utf-8")
    assert "## Active threads" in text
    assert "Blocked:" not in text
    assert "None" not in text.split("## Active threads", 1)[1].split("## Recent", 1)[0]

    service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            thread_id=thread.id,
            blocked_reason="Waiting on design review",
            content="blocked",
        )
    )
    text2 = service.wiki.read_progress("adhd-hub") or ""
    assert "Blocked:" in text2
    assert "Waiting on design review" in text2


def test_identical_state_does_not_duplicate_history(service: HubService) -> None:
    out = service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            title="OAuth",
            goal="Ship OAuth",
            focus="Write tests",
            next_steps=["Run pytest"],
            resume_step="Open tests/test_oauth.py",
            content="first",
        )
    )
    tid = out["thread_id"]
    before = service.store.list_progress_notes("adhd-hub", thread_id=tid)
    service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            thread_id=tid,
            goal="Ship OAuth",
            focus="Write tests",
            next_steps=["Run pytest"],
            resume_step="Open tests/test_oauth.py",
        )
    )
    after = service.store.list_progress_notes("adhd-hub", thread_id=tid)
    assert len(after) == len(before)


def test_session_digest_compact(service: HubService) -> None:
    service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            title="OAuth",
            goal="Ship OAuth",
            focus="Implement discovery",
            next_steps=["Token endpoint", "Docs"],
            resume_step="Open oauth.py",
            content="note",
        )
    )
    digest = service.session_digest(query="oauth")
    assert digest.items
    item = digest.items[0]
    dumped = item.model_dump(mode="json")
    assert dumped["goal"] == "Ship OAuth"
    assert dumped["focus"] == "Implement discovery"
    assert len(dumped["next_steps"]) <= 3
    assert "progress_log" not in dumped


def test_overlap_distinguishes_outcomes_in_same_project(service: HubService) -> None:
    service.upsert_thread(
        ThreadUpsert(
            summary="OAuth",
            project_slug="adhd-hub",
            goal="Ship MCP OAuth discovery and token endpoint",
            focus="Implement discovery",
        )
    )
    service.upsert_thread(
        ThreadUpsert(
            summary="Docs portal",
            project_slug="adhd-hub",
            goal="Publish GitHub Pages documentation portal",
            focus="Write landing page",
        )
    )
    result = service.check_overlap("continue GitHub Pages documentation portal")
    assert result.hits
    assert "portal" in result.hits[0].thread.summary.lower() or (
        result.hits[0].thread.goal and "portal" in result.hits[0].thread.goal.lower()
    )


def test_legacy_db_and_progress_md_migrate(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    db = data / "hub.sqlite3"
    wiki = data / "wiki" / "projects" / "legacy-proj"
    wiki.mkdir(parents=True)
    (wiki / "PROGRESS.md").write_text(
        "# Legacy proj\n\n_slug:_ `legacy-proj`\n\n## Status\n\n"
        "- status: open\n- updated: 2020-01-01\n\n## Progress log\n\n"
        "### 2020-01-01\n\nOld unscoped diary entry about everything.\n",
        encoding="utf-8",
    )
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE threads (
            id TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            status TEXT NOT NULL,
            energy TEXT NOT NULL,
            source_tool TEXT,
            workspace_path TEXT,
            project_slug TEXT,
            chat_ref TEXT,
            transcript_ref TEXT,
            origin TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_reminded_at TEXT
        );
        CREATE TABLE progress_notes (
            id TEXT PRIMARY KEY,
            project_slug TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE projects (
            slug TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            repo_url TEXT,
            workspace_paths TEXT NOT NULL DEFAULT '[]',
            default_energy TEXT NOT NULL DEFAULT 'unknown',
            forge_owner TEXT,
            forge_repo TEXT,
            forge_wiki_path TEXT,
            forge_project_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE reminders (
            id TEXT PRIMARY KEY,
            message TEXT NOT NULL,
            kind TEXT NOT NULL,
            due_at TEXT,
            created_at TEXT NOT NULL,
            handled INTEGER NOT NULL DEFAULT 0,
            last_fired_at TEXT
        );
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE pending_actions (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            payload TEXT NOT NULL DEFAULT '{}',
            reason TEXT,
            source_tool TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT
        );
        INSERT INTO projects (slug, title, workspace_paths, created_at, updated_at)
        VALUES ('legacy-proj', 'Legacy', '[]', '2020-01-01T00:00:00+00:00', '2020-01-01T00:00:00+00:00');
        INSERT INTO threads (
            id, summary, status, energy, source_tool, workspace_path, project_slug,
            chat_ref, transcript_ref, origin, created_at, updated_at, last_reminded_at
        ) VALUES (
            't-legacy', 'Old mega thread', 'open', 'unknown', NULL, NULL, 'legacy-proj',
            NULL, NULL, 'manual', '2020-01-01T00:00:00+00:00', '2020-01-01T00:00:00+00:00', NULL
        );
        INSERT INTO progress_notes (id, project_slug, content, created_at)
        VALUES ('n1', 'legacy-proj', 'Unscoped note', '2020-01-01T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    settings = Settings(data_dir=data, auth_token="t", wiki_dir=data / "wiki")
    svc = HubService(settings)
    thread = svc.store.get_thread("t-legacy")
    assert thread is not None
    assert thread.goal is None
    notes = svc.store.list_progress_notes("legacy-proj")
    assert notes[0]["thread_id"] == ""
    assert "Unscoped note" in notes[0]["content"]

    svc.upsert_progress(
        ProgressUpsert(
            project_slug="legacy-proj",
            thread_id="t-legacy",
            goal="Finish one clear outcome",
            focus="Trim the mega thread",
            content="Migrated checkpoint",
        )
    )
    text = svc.wiki.read_progress("legacy-proj") or ""
    assert "## Active threads" in text
    assert "## History" in text
    assert "Legacy project-level history" in text or "Old unscoped diary" in text
    assert "Finish one clear outcome" in text


def test_pause_resume_mark_done(service: HubService) -> None:
    out = service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            title="OAuth",
            goal="Ship OAuth",
            focus="Implement discovery",
            content="go",
        )
    )
    tid = out["thread_id"]
    paused = service.pause_thread(tid, "Open oauth discovery handler")
    assert paused.resume_step == "Open oauth discovery handler"
    done = service.mark_done(tid, note="Shipped OAuth")
    assert done and done.status.value == "done"
    assert service.list_open_threads(project_slug="adhd-hub") == []


def test_dismiss_removes_from_active_threads(service: HubService) -> None:
    t = service.upsert_thread(
        ThreadUpsert(summary="Temp spike", project_slug="adhd-hub", goal="Explore spike")
    )
    service.mark_dismissed(t.id, note="Not needed")
    text = service.wiki.read_progress("adhd-hub") or ""
    assert "Temp spike" not in text.split("## Active threads", 1)[1].split("## Recent", 1)[0]


def test_weak_match_creates_separate_thread(service: HubService) -> None:
    first = service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            title="OAuth",
            goal="Ship MCP OAuth",
            content="oauth work",
        )
    )
    second = service.upsert_progress(
        ProgressUpsert(
            project_slug="adhd-hub",
            title="Homelab deploy",
            goal="Deploy release to homelab Proxmox",
            content="deploy checklist",
        )
    )
    assert second["thread_id"] != first["thread_id"]
    assert not second.get("needs_thread_selection")
