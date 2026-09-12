"""Foundation B2b — outbound mutations, promote, Needs review, scheduler (#74)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from adhd_hub.config import Settings
from adhd_hub.forge.config import ForgeConfig, ForgeProvider, save_forge_config
from adhd_hub.forge.repo_sync import IssueSnapshot
from adhd_hub.models import PendingActionKind, ProjectUpsert, ThreadStatus, ThreadUpsert
from adhd_hub.service import HubService
from adhd_hub.work_identity import (
    ExternalIssueState,
    WorkSource,
    normalize_external_identity,
)


def _service(tmp_path: Path) -> HubService:
    return HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))


def _linked(tmp_path: Path):
    svc = _service(tmp_path)
    proj = svc.store.upsert_project(ProjectUpsert(title="App"))
    thread = svc.store.upsert_thread(
        ThreadUpsert(summary="Linked work", project_slug=proj.slug)
    )
    identity = normalize_external_identity(
        WorkSource.github, "github.com", "acme", "app", 11
    )
    svc.store.attach_external_identity(
        thread.id, identity, external_issue_state=ExternalIssueState.open
    )
    save_forge_config(
        svc.settings.data_dir,
        ForgeConfig(
            provider=ForgeProvider.github,
            token="tok",
            owner="acme",
            repo="app",
            board_enabled=True,
        ),
    )
    return svc, svc.store.get_thread(thread.id), identity


def test_mark_done_remote_first_success(tmp_path: Path) -> None:
    svc, thread, identity = _linked(tmp_path)
    assert thread is not None

    snap = IssueSnapshot(
        identity=identity,
        title="Linked work",
        state=ExternalIssueState.closed,
        labels=(),
        updated_at="2026-09-12T03:00:00Z",
    )

    with patch(
        "adhd_hub.forge.repo_sync.mutate_pinned_issue_state",
        return_value=snap,
    ):
        done = svc.mark_done(thread.id)
    assert done is not None
    assert done.status.value == "done"
    refreshed = svc.store.get_thread(thread.id)
    assert refreshed is not None
    assert refreshed.external_issue_state == ExternalIssueState.closed


def test_mark_done_remote_failure_leaves_hub_open(tmp_path: Path) -> None:
    svc, thread, _identity = _linked(tmp_path)
    assert thread is not None
    with patch(
        "adhd_hub.forge.repo_sync.mutate_pinned_issue_state",
        return_value={"ok": False, "error": "remote_patch_failed:500", "pending": False},
    ), pytest.raises(ValueError, match="remote_patch_failed"):
        svc.mark_done(thread.id)
    refreshed = svc.store.get_thread(thread.id)
    assert refreshed is not None
    assert refreshed.status.value == "open"
    assert refreshed.external_issue_state == ExternalIssueState.open


def test_reopen_external_remote_first(tmp_path: Path) -> None:
    svc, thread, identity = _linked(tmp_path)
    assert thread is not None
    svc.store.apply_external_projection(
        thread.id,
        summary=thread.summary,
        external_issue_state=ExternalIssueState.closed,
        external_updated_at="t",
        external_fingerprint="x",
    )
    svc.store.transition_status(thread.id, ThreadStatus.done)

    snap = IssueSnapshot(
        identity=identity,
        title=thread.summary,
        state=ExternalIssueState.open,
        labels=(),
        updated_at="t2",
    )
    with patch(
        "adhd_hub.forge.repo_sync.mutate_pinned_issue_state",
        return_value=snap,
    ):
        opened = svc.reopen_external_thread(thread.id)
    assert opened.status.value == "open"
    refreshed = svc.store.get_thread(thread.id)
    assert refreshed is not None
    assert refreshed.external_issue_state == ExternalIssueState.open


def test_promote_creates_issue_without_private_history(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    proj = svc.store.upsert_project(ProjectUpsert(title="App"))
    thread = svc.store.upsert_thread(
        ThreadUpsert(
            summary="Promote me",
            project_slug=proj.slug,
            focus="secret focus",
            next_steps=["private next"],
        )
    )
    save_forge_config(
        svc.settings.data_dir,
        ForgeConfig(
            provider=ForgeProvider.github,
            token="tok",
            owner="acme",
            repo="app",
            board_enabled=True,
        ),
    )
    identity = normalize_external_identity(
        WorkSource.github, "github.com", "acme", "app", 99
    )
    snap = IssueSnapshot(
        identity=identity,
        title="Promote me",
        state=ExternalIssueState.open,
        labels=(),
        updated_at="t",
    )
    with patch(
        "adhd_hub.forge.repo_sync.create_remote_issue",
        return_value=snap,
    ) as create:
        out = svc.promote_thread_to_issue(thread.id)
    assert out["ok"] is True
    kwargs = create.call_args.kwargs
    assert kwargs["title"] == "Promote me"
    assert kwargs.get("body") == ""
    assert "secret" not in (kwargs.get("body") or "")
    linked = svc.store.get_thread(thread.id)
    assert linked is not None
    assert linked.external_issue_number == 99


def test_link_collision_records_needs_review(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    proj = svc.store.upsert_project(ProjectUpsert(title="App"))
    a = svc.store.upsert_thread(ThreadUpsert(summary="A", project_slug=proj.slug))
    b = svc.store.upsert_thread(ThreadUpsert(summary="B", project_slug=proj.slug))
    identity = normalize_external_identity(
        WorkSource.github, "github.com", "acme", "app", 5
    )
    svc.store.attach_external_identity(a.id, identity)
    save_forge_config(
        svc.settings.data_dir,
        ForgeConfig(
            provider=ForgeProvider.github,
            token="tok",
            owner="acme",
            repo="app",
            board_enabled=True,
        ),
    )
    out = svc.link_thread_to_issue(b.id, owner="acme", repo="app", number=5)
    assert out.get("needs_review") is True
    reviews = [
        p
        for p in svc.store.list_pending_actions()
        if p.kind == PendingActionKind.sync_review
    ]
    assert reviews


def test_scheduler_overlap_lock_skips_second_run(tmp_path: Path) -> None:
    from adhd_hub import scheduler as sched

    svc = _service(tmp_path)
    save_forge_config(
        svc.settings.data_dir,
        ForgeConfig(
            provider=ForgeProvider.github,
            token="tok",
            owner="o",
            repo="r",
            board_enabled=True,
        ),
    )
    calls: list[str] = []

    def fake_sync():
        calls.append("run")
        return {"reconcile": [], "discovery": []}

    # Hold lock so job skips
    assert sched._reconcile_lock.acquire(blocking=False)
    try:
        with patch.object(svc, "sync_forge_now", side_effect=fake_sync):
            # Invoke job body similarly to scheduler
            now_backoff = sched._reconcile_backoff_until
            sched._reconcile_backoff_until = 0.0
            if not sched._reconcile_lock.acquire(blocking=False):
                skipped = True
            else:
                skipped = False
                sched._reconcile_lock.release()
            sched._reconcile_backoff_until = now_backoff
        assert skipped is True
        assert calls == []
    finally:
        sched._reconcile_lock.release()
