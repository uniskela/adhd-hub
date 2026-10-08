from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from itertools import count
from pathlib import Path
from threading import Event
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import adhd_hub.store as storage
from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.models import ProjectUpsert, Thread, ThreadStatus, ThreadUpsert
from adhd_hub.overlap import check_overlap, normalize_goal, score_thread
from adhd_hub.service import HubService
from adhd_hub.work_identity import DuplicateExternalIdentityError, ExternalIdentity, WorkSource

CASES = json.loads((Path(__file__).parent / "fixtures/merge_dedupe/cases.json").read_text())


@pytest.fixture
def service(tmp_path):
    return HubService(Settings(data_dir=tmp_path, auth_token="secret"))


def pair(service, *, source_goal="Ship DNS cutover", target_goal="Ship DNS cutover"):
    service.store.upsert_project(ProjectUpsert(slug="dns", title="DNS"))
    source = service.store.upsert_thread(
        ThreadUpsert(
            id="source",
            summary="Ship DNS cutover",
            project_slug="dns",
            goal=source_goal,
            focus="Verify nameservers",
            next_steps=["Source one", "Source two", "Source three"],
            resume_step="Read the cutover log",
            blocked_reason="Waiting for TTL",
            source_tool="cursor",
            chat_ref="chat-source",
            transcript_ref="source-log",
        )
    )
    target = service.store.upsert_thread(
        ThreadUpsert(
            id="target",
            summary="Ship DNS cutover",
            project_slug="dns",
            goal=target_goal,
            focus="Run the deployment",
            next_steps=["Target one", "Target two", "Target three"],
            resume_step="Open the deployment checklist",
            source_tool="codex",
            chat_ref="chat-target",
            transcript_ref="target-log",
        )
    )
    return source, target


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_cursor_suggestion_fixtures(service, case):
    source, target = pair(service, source_goal=case["source_goal"], target_goal=case["target_goal"])
    if case.get("target_source"):
        service.store.attach_external_identity(
            target.id,
            ExternalIdentity(
                provider=WorkSource.github,
                host="github.com",
                owner="demo",
                repo="dns",
                number=54,
            ),
        )
    suggestion = service.suggest_duplicate_threads(source.id)["hits"][0]
    assert suggestion["thread"]["id"] == target.id
    assert suggestion["outcome"] == case["outcome"]
    assert suggestion["merge_allowed"] is case["merge_allowed"]
    assert suggestion["merge_blocked_reason"] == case["reason"]
    assert suggestion["reason"]
    assert suggestion["evidence"]


def test_scores_reused_and_ties_stable():
    now = datetime(2026, 10, 8, tzinfo=UTC)
    threads = [
        Thread(
            id=tid,
            summary="DNS",
            goal="Ship DNS cutover",
            created_at=now,
            updated_at=now,
            project_slug="dns",
        )
        for tid in ("z", "a")
    ]
    for ordered in (threads, list(reversed(threads))):
        hits = check_overlap("Ship DNS cutover", ordered).hits
        assert [h.thread.id for h in hits] == ["a", "z"]
        assert hits[0].score == round(score_thread("Ship DNS cutover", threads[0])[0], 4)


def test_project_path_title_and_common_steps_are_not_duplicate_evidence(service):
    source, target = pair(service, target_goal="Write DNS troubleshooting guide")
    # Routing and shared next steps can produce high overlap but never authorize a merge.
    with service.store._conn() as conn:
        conn.execute(
            "UPDATE threads SET workspace_path = '/demo/dns', next_steps = ?",
            (json.dumps(["Run DNS cutover checks"]),),
        )
    hit = service.suggest_duplicate_threads(source.id)["hits"][0]
    assert hit["outcome"] == "related"
    assert hit["merge_allowed"] is False
    request = service.request_thread_merge(source.id, target.id)
    assert request["reason"] == "distinct_outcomes"
    assert request["alternatives"] == ["review_separately", "link_in_progress_note"]
    assert service.list_pending_actions() == []


def test_unicode_normalization_preserves_semantics():
    assert normalize_goal("  SHIP Cafe\u0301 \n") == normalize_goal("ship Café")
    assert normalize_goal("Ship #54") != normalize_goal("Ship #55")
    assert normalize_goal("Ship DNS") != normalize_goal("Do not ship DNS")
    assert normalize_goal("Ship A then B") != normalize_goal("Ship B then A")
    assert normalize_goal("Ship v1.2") != normalize_goal("Ship v12")


def test_cursor_response_fixtures_match_backend(service, monkeypatch):
    fixtures = json.loads((Path(__file__).parent / "fixtures/merge_dedupe/responses.json").read_text())
    sequence = count(1)
    monkeypatch.setattr(storage, "utcnow", lambda: datetime(2026, 10, 8, tzinfo=UTC))
    monkeypatch.setattr(storage, "uuid4", lambda: UUID(int=next(sequence)))
    service.store.upsert_project(ProjectUpsert(slug="dns", title="DNS"))
    for tid in ("source", "target"):
        snapshot = fixtures["queued"]["action"]["payload"][tid]
        service.store.upsert_thread(ThreadUpsert(**{
            field: snapshot[field] for field in ThreadUpsert.model_fields if field in snapshot
        }))
        service.store.add_progress_note("dns", f"{tid} cutover decision", thread_id=tid)
    assert service.suggest_duplicate_threads("source") == fixtures["suggestions"]
    queued = service.request_thread_merge("source", "target")
    assert queued == fixtures["queued"]
    assert service.approve_pending_action(queued["action"]["id"], confirm_merge=True) == fixtures["approved"]
    assert service.thread_merge_history("target") == fixtures["history"]


@pytest.mark.parametrize(
    "provenance", ["pinned", "inherited", "legacy_url", "legacy_meta", "import", "snapshot"]
)
@pytest.mark.parametrize("side", ["source", "target"])
def test_forge_sources_refused_without_forge_calls(service, monkeypatch, provenance, side):
    source, target = pair(service)
    tid = source.id if side == "source" else target.id
    if provenance == "pinned":
        service.store.attach_external_identity(
            tid,
            ExternalIdentity(
                provider=WorkSource.gitea,
                host="forge.example",
                owner="demo",
                repo="dns",
                number=1,
            ),
        )
    elif provenance == "inherited":
        service.store.upsert_project(
            ProjectUpsert(
                slug="dns",
                title="DNS",
                default_work_source=WorkSource.github,
            )
        )
    elif provenance == "legacy_meta":
        service.store.set_meta(f"forge_issue:{tid}", "54")
    else:
        with service.store._conn() as conn:
            if provenance == "legacy_url":
                conn.execute(
                    "UPDATE threads SET source_issue_url = ? WHERE id = ?",
                    ("https://github.com/demo/dns/issues/54", tid),
                )
            elif provenance == "snapshot":
                conn.execute("UPDATE threads SET source_snapshot = ? WHERE id = ?",
                             (json.dumps({"goal": "Imported source goal"}), tid))
            else:
                conn.execute("UPDATE threads SET origin = 'forge-import' WHERE id = ?", (tid,))
    monkeypatch.setattr(service, "_forge_after_thread", lambda *a, **k: pytest.fail("forge write"))
    before = [service.store.get_thread(t).model_dump() for t in (source.id, target.id)]
    request = service.request_thread_merge(source.id, target.id)
    assert request["pending"] is False
    assert request["reason"] == "forge_authoritative"
    assert [service.store.get_thread(t).model_dump() for t in (source.id, target.id)] == before


@pytest.mark.parametrize(
    "change,reason",
    [
        ("self", "same_thread"),
        ("done", "unfinished_required"),
        ("project", "different_projects"),
        ("goal", "goal_required"),
    ],
)
def test_unsafe_merges_refused(service, change, reason):
    source, target = pair(service)
    if change == "self":
        target = source
    else:
        with service.store._conn() as conn:
            if change == "done":
                conn.execute("UPDATE threads SET status = 'done' WHERE id = ?", (target.id,))
            elif change == "project":
                conn.execute("UPDATE threads SET project_slug = 'other' WHERE id = ?", (target.id,))
            else:
                conn.execute("UPDATE threads SET goal = NULL WHERE id = ?", (target.id,))
    assert service.request_thread_merge(source.id, target.id)["reason"] == reason


def test_confirmation_history_identity_and_retry(service, monkeypatch):
    source, target = pair(service)
    service.store.pause_thread(source.id, "Read source paused cue")
    service.store.pause_thread(target.id, "Read target paused cue")
    source, target = [service.store.get_thread(t.id) for t in (source, target)]
    note_ids = [
        service.store.add_progress_note("dns", f"{t.id} decision", thread_id=t.id)
        for t in (source, target)
    ]
    service.publish_hub_event("thread.progress_updated", thread_id=source.id, project_slug="dns")
    before_events = [e.public_dict() for e in service.store.list_activity_events()]
    monkeypatch.setattr(service, "_forge_after_thread", lambda *a, **k: pytest.fail("forge write"))
    request = service.request_thread_merge(source.id, target.id)
    assert request["pending"] is True
    assert (
        service.request_thread_merge(source.id, target.id)["action"]["id"]
        == request["action"]["id"]
    )
    assert service.store.get_thread(source.id) == source
    aid = request["action"]["id"]
    with pytest.raises(ValueError, match="merge_confirmation_required"):
        service.approve_pending_action(aid)
    assert service.store.get_thread(source.id) == source
    assert service.approve_pending_action(aid, confirm_merge=True)["approved"] is True
    retained, active = [service.store.get_thread(t.id) for t in (source, target)]
    assert retained.status == ThreadStatus.dismissed
    assert retained.merged_into == target.id
    for field in Thread.model_fields:
        if field not in {"updated_at", "status", "merged_into"}:
            assert getattr(retained, field) == getattr(source, field)
        if field != "updated_at":
            assert getattr(active, field) == getattr(target, field)
    notes = service.store.list_progress_notes("dns")
    assert set(note_ids) <= {n["id"] for n in notes}
    assert {n["thread_id"] for n in notes if n["id"] in note_ids} == {source.id, target.id}
    after_events = [e.public_dict() for e in service.store.list_activity_events()]
    assert all(e in after_events for e in before_events)
    assert len(after_events) == len(before_events) + 2
    history = service.thread_merge_history(target.id)
    assert {i["thread"]["id"] for i in history["items"]} == {source.id, target.id}
    assert service.approve_pending_action(aid, confirm_merge=True)["already_resolved"] is True
    assert [e.public_dict() for e in service.store.list_activity_events()] == after_events
    with pytest.raises(ValueError, match="merged_thread_read_only"):
        service.store.upsert_thread(
            ThreadUpsert(id=source.id, summary="Reopen", project_slug="dns")
        )
    with pytest.raises(ValueError, match="merged_thread_read_only"):
        service.store.transition_status(source.id, ThreadStatus.open)
    with pytest.raises(DuplicateExternalIdentityError, match="merged_thread_read_only"):
        service.store.attach_external_identity(source.id, ExternalIdentity(
            provider=WorkSource.github, host="github.com", owner="demo", repo="dns", number=54,
        ))
    assert service.promote_thread_to_issue(source.id)["error"] == "merged_thread_read_only"


def test_reject_changes_nothing(service):
    source, target = pair(service)
    aid = service.request_thread_merge(source.id, target.id)["action"]["id"]
    service.reject_pending_action(aid)
    assert service.approve_pending_action(aid, confirm_merge=True)["already_resolved"] is True
    assert service.store.get_thread(source.id) == source
    assert service.store.get_thread(target.id) == target


@pytest.mark.parametrize("side", ["source", "target"])
@pytest.mark.parametrize("operation", ["remind", "confirm", "snooze"])
def test_reminder_and_triage_changes_do_not_invalidate_merge(service, side, operation):
    source, target = pair(service)
    tid = source.id if side == "source" else target.id
    service.store.snooze_thread_triage(tid, days=7)
    queued = service.request_thread_merge(source.id, target.id)
    snapshot = queued["action"]["payload"][side]
    if operation == "remind":
        service.store.touch_reminded([tid])
    elif operation == "confirm":
        service.store.confirm_thread_relevant(tid)
    else:
        service.store.snooze_thread_triage(tid, days=14)
    current = service.store.get_thread(tid).model_dump(mode="json")
    changed = {field for field in snapshot if snapshot[field] != current[field]}
    assert changed
    assert changed <= {"last_reminded_at", "triage_snooze_until"}
    aid = queued["action"]["id"]
    approved = service.approve_pending_action(aid, confirm_merge=True)
    assert approved["approved"] is True
    assert approved["action"]["payload"] == queued["action"]["payload"]
    retained = service.store.get_thread(tid).model_dump(mode="json")
    for field in ("last_reminded_at", "triage_snooze_until"):
        assert retained[field] == current[field]


def test_rejection_racing_approval_reports_the_winner(service, monkeypatch):
    source, target = pair(service)
    aid = service.request_thread_merge(source.id, target.id)["action"]["id"]
    original = service.store.resolve_pending_action
    def resolve_after_approval(action_id, status):
        assert service.store.approve_thread_merge(action_id)["approved"] is True
        return original(action_id, status)
    monkeypatch.setattr(service.store, "resolve_pending_action", resolve_after_approval)
    response = service.reject_pending_action(aid)
    assert response["already_resolved"] is True
    assert response["action"]["status"] == "approved"
    assert service.store.get_thread(source.id).merged_into == target.id


def test_identity_attach_racing_merge_preserves_original_source(service, monkeypatch):
    source, target = pair(service)
    aid = service.request_thread_merge(source.id, target.id)["action"]["id"]
    original = service.store.get_thread
    fired = False
    def get_before_merge(tid):
        nonlocal fired
        thread = original(tid)
        if tid == source.id and not fired:
            fired = True
            service.store.approve_thread_merge(aid)
        return thread
    monkeypatch.setattr(service.store, "get_thread", get_before_merge)
    with pytest.raises(DuplicateExternalIdentityError, match="merged_thread_read_only"):
        service.store.attach_external_identity(source.id, ExternalIdentity(
            provider=WorkSource.github, host="github.com", owner="demo", repo="dns", number=54,
        ))
    retained = original(source.id)
    assert retained.merged_into == target.id
    assert retained.external_provider is None
    assert retained.source_tool == source.source_tool
    assert service.store.get_meta(f"forge_issue:{source.id}") is None


@pytest.mark.parametrize("operation", ["upsert", "status", "pause"])
def test_source_writes_lock_before_read_against_concurrent_merge(service, monkeypatch, operation):
    source, target = pair(service)
    aid = service.request_thread_merge(source.id, target.id)["action"]["id"]
    read_started, proceed = Event(), Event()
    original_conn = service.store._conn

    @contextmanager
    def guarded_conn():
        with original_conn() as conn:
            class Connection:
                def execute(self, sql, args=()):
                    cursor = conn.execute(sql, args)
                    if sql.startswith("SELECT") and "FROM threads WHERE id = ?" in sql:
                        read_started.set()
                        assert proceed.wait(5)
                    return cursor
            yield Connection()

    monkeypatch.setattr(service.store, "_conn", guarded_conn)
    def write():
        if operation == "upsert":
            return service.store.upsert_thread(ThreadUpsert(
                id=source.id, summary=source.summary, goal=source.goal, project_slug="dns",
                resume_step="New progress cue",
            ))
        if operation == "status":
            return service.store.transition_status(source.id, ThreadStatus.blocked)
        return service.store.pause_thread(source.id, "New pause cue")

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(write)
        try:
            assert read_started.wait(5)
            # Approval cannot acquire its write lock between the source guard and update.
            with (
                sqlite3.connect(service.store.db_path, timeout=0) as competing,
                pytest.raises(sqlite3.OperationalError, match="locked"),
            ):
                competing.execute("BEGIN IMMEDIATE")
        finally:
            proceed.set()
        future.result(timeout=5)
    monkeypatch.setattr(service.store, "_conn", original_conn)
    with pytest.raises(ValueError, match="merge_preview_stale"):
        service.approve_pending_action(aid, confirm_merge=True)
    assert service.store.get_thread(source.id).merged_into is None


@pytest.mark.parametrize(
    "change", ["goal", "resume", "source_identity", "project_authority", "legacy_link"]
)
def test_stale_preview_requires_new_review(service, change):
    source, target = pair(service)
    aid = service.request_thread_merge(source.id, target.id)["action"]["id"]
    if change == "project_authority":
        service.store.upsert_project(
            ProjectUpsert(
                slug="dns",
                title="DNS",
                default_work_source=WorkSource.github,
            )
        )
    elif change == "legacy_link":
        service.store.set_meta(f"forge_issue:{source.id}", "54")
    else:
        with service.store._conn() as conn:
            column = {"goal": "goal", "resume": "resume_step", "source_identity": "chat_ref"}[
                change
            ]
            conn.execute(f"UPDATE threads SET {column} = 'changed' WHERE id = ?", (source.id,))
    with pytest.raises(ValueError, match="merge_refused|merge_preview_stale"):
        service.approve_pending_action(aid, confirm_merge=True)
    assert service.store.get_pending_action(aid).status.value == "pending"
    assert service.store.get_thread(source.id).merged_into is None
    assert service.store.get_thread(target.id) == target


@pytest.mark.parametrize("table", ["progress_notes", "activity_events", "pending_actions"])
def test_failure_rolls_back_every_merge_write(service, table):
    source, target = pair(service)
    aid = service.request_thread_merge(source.id, target.id)["action"]["id"]
    before_notes = service.store.list_progress_notes("dns")
    before_events = service.store.list_activity_events()
    event = "UPDATE" if table == "pending_actions" else "INSERT"
    with service.store._conn() as conn:
        conn.execute(
            f"CREATE TRIGGER fail_merge BEFORE {event} ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        service.approve_pending_action(aid, confirm_merge=True)
    assert service.store.get_thread(source.id) == source
    assert service.store.get_thread(target.id) == target
    assert service.store.get_pending_action(aid).status.value == "pending"
    assert service.store.list_progress_notes("dns") == before_notes
    assert service.store.list_activity_events() == before_events
    with service.store._conn() as conn:
        conn.execute("DROP TRIGGER fail_merge")
    assert service.approve_pending_action(aid, confirm_merge=True)["approved"] is True


def test_projection_failure_is_reported_after_atomic_commit(service, monkeypatch):
    source, target = pair(service)
    aid = service.request_thread_merge(source.id, target.id)["action"]["id"]

    def fail(*args, **kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(service, "_sync_project_progress", fail)
    result = service.approve_pending_action(aid, confirm_merge=True)
    assert result["approved"] is True
    assert result["projection_warning"]
    assert service.store.get_thread(source.id).merged_into == target.id


def test_merge_history_handles_multiple_merges(service):
    source, target = pair(service)
    other = service.store.upsert_thread(
        ThreadUpsert(
            id="other",
            summary="Other",
            goal=target.goal,
            project_slug="dns",
        )
    )
    for left, right in ((source, target), (target, other)):
        aid = service.request_thread_merge(left.id, right.id)["action"]["id"]
        service.approve_pending_action(aid, confirm_merge=True)
    assert service.store.merged_thread_ids(other.id) == ["other", "source", "target"]
    assert len(service.thread_merge_history(other.id)["items"]) == 3


def test_rest_contract_auth_confirmation_and_errors(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, auth_token="secret"))
    _source, target = pair(app.state.service)
    headers = {"Authorization": "Bearer secret"}
    with TestClient(app) as client:
        for suffix in ("duplicates", "merge-history"):
            assert client.get(f"/api/threads/source/{suffix}").status_code == 401
            assert client.get(f"/api/threads/missing/{suffix}", headers=headers).status_code == 404
        assert (
            client.post(
                "/api/threads/source/merge", json={"target_thread_id": "target"}
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/threads/source/duplicates", headers=headers, params={"limit": 0}
            ).status_code
            == 422
        )
        assert client.post("/api/threads/source/merge", headers=headers, json={}).status_code == 422
        hits = client.get("/api/threads/source/duplicates", headers=headers).json()["hits"]
        assert hits[0]["merge_allowed"] is True
        queued = client.post(
            "/api/threads/source/merge", headers=headers, json={"target_thread_id": "target"}
        ).json()
        aid = queued["action"]["id"]
        assert (
            client.post(f"/api/pending-actions/{aid}/approve", headers=headers).status_code == 400
        )
        assert (
            client.post(
                f"/api/pending-actions/{aid}/approve",
                headers=headers,
                json={"confirm_merge": "true"},
            ).status_code
            == 422
        )
        approved = client.post(
            f"/api/pending-actions/{aid}/approve", headers=headers, json={"confirm_merge": True}
        )
        assert approved.status_code == 200
        assert approved.json()["result"]["remote_changed"] is False
        history = client.get("/api/threads/target/merge-history", headers=headers).json()
        assert len(history["items"]) == 2
        assert client.get("/api/threads/source", headers=headers).json()["merged_into"] == target.id


def test_rest_stale_preview_conflict(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, auth_token="secret"))
    source, target = pair(app.state.service)
    aid = app.state.service.request_thread_merge(source.id, target.id)["action"]["id"]
    app.state.service.store.pause_thread(source.id, "New resume cue")
    with TestClient(app) as client:
        response = client.post(
            f"/api/pending-actions/{aid}/approve",
            headers={"Authorization": "Bearer secret"},
            json={"confirm_merge": True},
        )
        assert response.status_code == 409


def test_mcp_contract_and_no_agent_approval(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, auth_token="secret"))
    source, target = pair(app.state.service)
    headers = {"Authorization": "Bearer secret", "Accept": "application/json, text/event-stream"}
    with TestClient(app, base_url="http://127.0.0.1:8787") as client:

        def rpc(method, params):
            return client.post(
                "/mcp",
                headers=headers,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            )

        rpc(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        ).raise_for_status()
        tools = {t["name"]: t for t in rpc("tools/list", {}).json()["result"]["tools"]}
        assert "approve_pending_action" not in tools
        assert tools["suggest_duplicate_threads"]["annotations"]["readOnlyHint"] is True
        assert tools["thread_merge_history"]["annotations"]["readOnlyHint"] is True
        assert tools["request_thread_merge"]["annotations"]["destructiveHint"] is False
        invalid = rpc(
            "tools/call",
            {
                "name": "suggest_duplicate_threads",
                "arguments": {"thread_id": source.id, "limit": -1},
            },
        )
        assert invalid.json()["result"]["isError"] is True
        for name, arguments in (
            ("check_overlap", {"query": source.goal}),
            ("suggest_duplicate_threads", {"thread_id": source.id}),
            (
                "request_thread_merge",
                {"source_thread_id": source.id, "target_thread_id": target.id},
            ),
            ("thread_merge_history", {"thread_id": target.id}),
        ):
            result = rpc("tools/call", {"name": name, "arguments": arguments}).json()["result"]
            assert not result.get("isError"), result
            assert result["structuredContent"]
        assert app.state.service.store.get_thread(source.id).merged_into is None
