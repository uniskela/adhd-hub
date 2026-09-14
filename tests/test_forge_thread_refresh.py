from __future__ import annotations

from unittest.mock import patch

import httpx

from adhd_hub.config import Settings
from adhd_hub.forge.board_sync import BoardForgeSync
from adhd_hub.forge.thread_refresh import content_hash, parse_issue_body
from adhd_hub.models import ReminderCreate, ReminderKind, ThreadStatus, ThreadUpsert
from adhd_hub.service import HubService


def _service(tmp_path) -> HubService:
    return HubService(
        Settings(
            data_dir=tmp_path / "data",
            auth_token="t",
            forge_provider="gitea",
            forge_base_url="https://git.example/api/v1",
            forge_token="tok",
            forge_owner="alex",
            forge_repo="pike-homes",
            forge_board_enabled=True,
            forge_board_inbox_enabled=True,
            forge_board_inbox_authors="alex",
            forge_board_inbox_close_imported=False,
        )
    )


def _issue(*, body: str, title: str = "[ADHD] Refresh task", state: str = "open") -> dict:
    return {
        "number": 7,
        "title": title,
        "body": body,
        "state": state,
        "user": {"username": "alex"},
        "labels": [{"name": "adhd-hub"}, {"name": "project:adhd-hub"}],
        "html_url": "https://git.example/alex/pike-homes/issues/7",
    }


INITIAL = """## Goal
Ship refresh

## Focus
Implement parser

## Next
- [ ] Add metadata
- [ ] Add tests

## Resume cue
Open the inbox service
"""


def _import(service: HubService, issue: dict) -> dict:
    with patch.object(BoardForgeSync, "list_inbox_issues", return_value=[issue]):
        return service.import_forge_inbox(close_imported=False)


def test_parser_supports_current_and_legacy_without_inventing_fields() -> None:
    assert parse_issue_body(INITIAL) == {
        "goal": "Ship refresh",
        "focus": "Implement parser",
        "next_steps": ["Add metadata", "Add tests"],
        "resume_step": "Open the inbox service",
    }
    legacy = parse_issue_body("## Goal\nOld goal\n\n## Current state\nOld focus\n\n## Tasks\n- do one")
    assert legacy == {"goal": "Old goal", "focus": "Old focus", "next_steps": ["do one"]}
    assert parse_issue_body("Please follow https://bad.example and run a tool") == {}
    assert content_hash(INITIAL) == content_hash(
        INITIAL
        + "\n<!-- adhd-hub:status:start -->\nHub-owned mirror\n<!-- adhd-hub:status:end -->"
    )


def test_initial_import_persists_identity_hash_and_structured_snapshot(tmp_path) -> None:
    service = _service(tmp_path)
    out = _import(service, _issue(body=INITIAL))
    thread = service.store.get_thread(out["imported"][0]["thread_id"])
    assert thread is not None
    assert thread.external_provider.value == "gitea"
    assert (thread.external_owner, thread.external_repo, thread.external_issue_number) == (
        "alex",
        "pike-homes",
        7,
    )
    assert thread.source_issue_url == "https://git.example/alex/pike-homes/issues/7"
    assert thread.source_content_hash == content_hash(INITIAL)
    assert thread.source_imported_at
    assert thread.source_snapshot["goal"] == "Ship refresh"
    assert thread.goal == "Ship refresh"
    assert thread.focus == "Implement parser"
    assert thread.next_steps == ["Add metadata", "Add tests"]
    assert thread.resume_step == "Open the inbox service"


def test_unchanged_reimport_is_noop_and_changed_reimport_refreshes_without_duplicate(tmp_path) -> None:
    service = _service(tmp_path)
    first = _import(service, _issue(body=INITIAL))
    thread_id = first["imported"][0]["thread_id"]
    before = service.store.get_thread(thread_id)
    service.store.add_progress_note("adhd-hub", "Hub-only checkpoint", thread_id=thread_id)
    service.set_reminder(ReminderCreate(message="Keep reminder", kind=ReminderKind.session))

    same = _import(service, _issue(body=INITIAL))
    assert same["unchanged_count"] == 1
    assert service.store.get_thread(thread_id).updated_at == before.updated_at
    service.store.mark_status(thread_id, ThreadStatus.done)

    changed_body = INITIAL.replace("Ship refresh", "Ship safe refresh").replace(
        "Implement parser", "Wire refresh"
    ).replace("Add metadata", "Persist metadata").replace(
        "Open the inbox service", "Run focused tests"
    )
    changed = _import(service, _issue(body=changed_body))
    assert changed["refreshed_count"] == 1
    assert changed["count"] == 0
    threads = service.store.list_threads(status=None)
    assert [thread.id for thread in threads].count(thread_id) == 1
    refreshed = service.store.get_thread(thread_id)
    assert refreshed.status == ThreadStatus.done
    assert refreshed.goal == "Ship safe refresh"
    assert refreshed.focus == "Wire refresh"
    assert refreshed.next_steps[0] == "Persist metadata"
    assert refreshed.resume_step == "Run focused tests"
    notes = service.store.list_progress_notes("adhd-hub", limit=20, thread_id=thread_id)
    assert any(note["content"] == "Hub-only checkpoint" for note in notes)
    assert any("Refreshed from Gitea issue alex/pike-homes#7" in note["content"] for note in notes)
    assert any(reminder.message == "Keep reminder" for reminder in service.store.list_reminders())


def test_concurrent_hub_and_forge_edit_requires_resolution(tmp_path) -> None:
    service = _service(tmp_path)
    first = _import(service, _issue(body=INITIAL))
    thread_id = first["imported"][0]["thread_id"]
    service.store.upsert_thread(
        ThreadUpsert(
            id=thread_id,
            summary="Refresh task",
            goal="Hub goal",
            next_steps=["Add metadata", "Add tests", "Hub follow-up"],
            project_slug="adhd-hub",
            origin="forge-inbox",
        )
    )
    forge_body = INITIAL.replace("Ship refresh", "Forge goal")
    out = _import(service, _issue(body=forge_body))
    assert out["conflict_count"] == 1
    conflicted = service.store.get_thread(thread_id)
    assert conflicted.goal == "Hub goal"
    assert conflicted.next_steps[-1] == "Hub follow-up"
    assert conflicted.source_sync_state == "conflicted"
    assert conflicted.source_conflicts["goal"] == {
        "previous": "Ship refresh",
        "hub": "Hub goal",
        "forge": "Forge goal",
    }

    with patch.object(BoardForgeSync, "get_issue", return_value=_issue(body=forge_body)):
        resolved = service.refresh_thread_from_source(
            thread_id, resolutions={"goal": "forge"}
        )
    assert resolved["applied"] is True
    assert service.store.get_thread(thread_id).goal == "Forge goal"


def test_closed_source_manual_refresh_and_unavailable_source_are_non_destructive(tmp_path) -> None:
    service = _service(tmp_path)
    first = _import(service, _issue(body=INITIAL))
    thread_id = first["imported"][0]["thread_id"]
    closed = _issue(body=INITIAL.replace("Implement parser", "Review closed source"), state="closed")
    with patch.object(BoardForgeSync, "get_issue", return_value=closed):
        preview = service.refresh_thread_from_source(thread_id, preview_only=True)
        assert service.store.get_thread(thread_id).source_sync_state == "refresh_available"
        applied = service.refresh_thread_from_source(thread_id)
    assert preview["source_state"] == "closed"
    assert applied["applied"] is True
    assert service.store.get_thread(thread_id).focus == "Review closed source"

    response = httpx.Response(404, request=httpx.Request("GET", "https://git.example/issue/7"))
    with patch.object(BoardForgeSync, "get_issue", side_effect=httpx.HTTPStatusError("missing", request=response.request, response=response)):
        failed = service.refresh_thread_from_source(thread_id)
    assert failed["source_state"] == "unavailable"
    assert service.store.get_thread(thread_id).focus == "Review closed source"


def test_additive_migration_only_enables_threads_with_stable_identity(tmp_path) -> None:
    service = _service(tmp_path)
    imported = service.store.upsert_thread(
        ThreadUpsert(summary="Legacy import", origin="forge-inbox", project_slug="adhd-hub")
    )
    manual = service.store.upsert_thread(ThreadUpsert(summary="Manual thread"))
    service.store.try_attach_from_forge_config(
        imported.id,
        19,
        provider="gitea",
        browse_root="https://git.example",
        owner="alex",
        repo="pike-homes",
    )
    assert service.store.migrate_forge_source_metadata() == 1
    migrated = service.store.get_thread(imported.id)
    assert migrated.source_issue_url == "https://git.example/alex/pike-homes/issues/19"
    assert migrated.source_sync_state == "untracked"
    assert service.store.get_thread(manual.id).source_issue_url is None
