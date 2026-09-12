"""Foundation B2a — repo-primary inbound authority tests (#74)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adhd_hub.config import Settings
from adhd_hub.forge.board_sync import BoardForgeSync
from adhd_hub.forge.config import (
    ForgeConfig,
    ForgeProvider,
    IssueImportPolicy,
    load_forge_config,
    save_forge_config,
)
from adhd_hub.forge.repo_sync import (
    IssueSnapshot,
    discover_issue_payloads,
    fingerprint_for,
    is_pull_request_payload,
    issue_snapshot_from_raw,
    resolve_assigned_to_me_login,
)
from adhd_hub.models import ProgressUpsert, ProjectUpsert, ThreadUpsert
from adhd_hub.service import HubService
from adhd_hub.store import Store
from adhd_hub.work_identity import (
    ExternalIssueState,
    WorkSource,
    normalize_external_identity,
)


def _service(tmp_path: Path) -> HubService:
    return HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))


def test_forge_config_defaults_are_safe() -> None:
    cfg = ForgeConfig()
    assert cfg.issue_import_policy == IssueImportPolicy.manual
    assert cfg.board_inbox_close_imported is False
    assert cfg.board_mirror_local is False
    assert cfg.publish_hub_status_block is False


def test_migrated_inbox_config_keeps_adhd_inbox_policy(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    path = data / "forge.json"
    path.write_text(
        '{"provider":"github","token":"x","owner":"o","repo":"r",'
        '"board_enabled":true,"board_inbox_enabled":true}\n',
        encoding="utf-8",
    )
    cfg = load_forge_config(data)
    assert cfg.issue_import_policy == IssueImportPolicy.adhd_inbox


def test_thread_revision_columns_round_trip(tmp_path: Path) -> None:
    store = Store(tmp_path / "hub.sqlite3")
    with store._conn() as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(threads)").fetchall()}
    assert "external_updated_at" in cols
    assert "external_fingerprint" in cols
    assert "external_labels" in cols


def test_fingerprint_stable_under_label_order_and_casing() -> None:
    a = IssueSnapshot(
        identity=normalize_external_identity(WorkSource.github, "github.com", "Acme", "App", 9),
        title=" Fix me ",
        state=ExternalIssueState.open,
        labels=("Bug", "help wanted"),
        updated_at="2026-09-12T00:00:00Z",
    )
    b = IssueSnapshot(
        identity=normalize_external_identity(WorkSource.github, "github.com", "acme", "app", 9),
        title=" Fix me ",
        state=ExternalIssueState.open,
        labels=("help wanted", "BUG"),
        updated_at="2026-09-12T99:99:99Z",
    )
    assert fingerprint_for(a) == fingerprint_for(b)


def test_fingerprint_nfc_title_normalization() -> None:
    composed = "caf\u00e9"
    decomposed = "cafe\u0301"
    a = IssueSnapshot(
        identity=normalize_external_identity(WorkSource.github, "github.com", "o", "r", 1),
        title=composed,
        state=ExternalIssueState.open,
        labels=(),
        updated_at="t1",
    )
    b = IssueSnapshot(
        identity=normalize_external_identity(WorkSource.github, "github.com", "o", "r", 1),
        title=decomposed,
        state=ExternalIssueState.open,
        labels=(),
        updated_at="t2",
    )
    assert fingerprint_for(a) == fingerprint_for(b)


def test_fingerprint_changes_when_state_changes() -> None:
    identity = normalize_external_identity(WorkSource.github, "github.com", "o", "r", 1)
    open_s = IssueSnapshot(
        identity=identity,
        title="T",
        state=ExternalIssueState.open,
        labels=(),
        updated_at="t",
    )
    closed_s = IssueSnapshot(
        identity=identity,
        title="T",
        state=ExternalIssueState.closed,
        labels=(),
        updated_at="t",
    )
    assert fingerprint_for(open_s) != fingerprint_for(closed_s)


def test_github_pull_requests_excluded_from_discover() -> None:
    assert is_pull_request_payload({"number": 1, "pull_request": {}})
    assert not is_pull_request_payload({"number": 1, "pull_request": None})
    assert (
        issue_snapshot_from_raw(
            {
                "number": 2,
                "title": "PR",
                "state": "open",
                "pull_request": {},
                "labels": [],
            },
            provider=WorkSource.github,
            host="github.com",
            owner="o",
            repo="r",
        )
        is None
    )


def test_apply_projection_updates_state_not_hub_status(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    proj = svc.store.upsert_project(ProjectUpsert(title="App"))
    thread = svc.store.upsert_thread(
        ThreadUpsert(
            summary="Old title",
            project_slug=proj.slug,
            focus="Keep me",
            next_steps=["A"],
        )
    )
    identity = normalize_external_identity(WorkSource.github, "github.com", "acme", "app", 7)
    svc.store.attach_external_identity(thread.id, identity)
    snap = IssueSnapshot(
        identity=identity,
        title="New remote title",
        state=ExternalIssueState.closed,
        labels=("bug",),
        updated_at="2026-09-12T01:00:00Z",
    )
    fp = fingerprint_for(snap)
    out = svc.store.apply_external_projection(
        thread.id,
        summary=snap.title,
        external_issue_state=snap.state,
        external_updated_at=snap.updated_at,
        external_fingerprint=fp,
        external_labels=list(snap.labels),
    )
    assert out["applied"] is True
    refreshed = svc.store.get_thread(thread.id)
    assert refreshed is not None
    assert refreshed.summary == "New remote title"
    assert refreshed.external_issue_state == ExternalIssueState.closed
    assert refreshed.status.value == "open"
    assert refreshed.focus == "Keep me"
    assert refreshed.next_steps == ["A"]
    again = svc.store.apply_external_projection(
        thread.id,
        summary=snap.title,
        external_issue_state=snap.state,
        external_updated_at=snap.updated_at,
        external_fingerprint=fp,
        external_labels=list(snap.labels),
    )
    assert again["applied"] is False


def test_get_or_create_atomic_no_orphan_on_collision(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    proj = svc.store.upsert_project(ProjectUpsert(title="App"))
    identity = normalize_external_identity(WorkSource.github, "github.com", "acme", "app", 3)
    a, created_a = svc.store.get_or_create_thread_for_external_identity(
        identity=identity,
        project_slug=proj.slug,
        summary="One",
        external_issue_state=ExternalIssueState.open,
    )
    b, created_b = svc.store.get_or_create_thread_for_external_identity(
        identity=identity,
        project_slug=proj.slug,
        summary="Two",
        external_issue_state=ExternalIssueState.open,
    )
    assert created_a is True
    assert created_b is False
    assert a.id == b.id
    assert a.external_issue_number == 3
    linked = [
        t
        for t in svc.store.list_externally_linked_threads()
        if t.external_issue_number == 3
    ]
    assert len(linked) == 1


def test_upsert_progress_allows_title_when_project_default_external_but_unlinked(
    tmp_path: Path,
) -> None:
    svc = _service(tmp_path)
    proj = svc.store.upsert_project(
        ProjectUpsert(title="App", default_work_source=WorkSource.github)
    )
    thread = svc.store.upsert_thread(
        ThreadUpsert(summary="Local title", project_slug=proj.slug)
    )
    updated = svc.upsert_progress(
        ProgressUpsert(
            project_slug=proj.slug,
            thread_id=thread.id,
            title="Renamed locally",
            focus="still hub-owned",
        )
    )
    assert updated["thread"]["summary"] == "Renamed locally"
    refreshed = svc.store.get_thread(thread.id)
    assert refreshed is not None
    assert refreshed.summary == "Renamed locally"


def test_upsert_progress_rejects_title_change_on_external(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    proj = svc.store.upsert_project(ProjectUpsert(title="App"))
    thread = svc.store.upsert_thread(
        ThreadUpsert(summary="Canonical title", project_slug=proj.slug)
    )
    svc.store.attach_external_identity(
        thread.id,
        normalize_external_identity(WorkSource.github, "github.com", "acme", "app", 1),
    )
    with pytest.raises(ValueError, match="repo_owned_field_forbidden"):
        svc.upsert_progress(
            ProgressUpsert(
                project_slug=proj.slug,
                thread_id=thread.id,
                title="Hacked remote title",
                focus="ok focus",
            )
        )


def test_upsert_progress_allows_focus_on_external(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    proj = svc.store.upsert_project(ProjectUpsert(title="App"))
    thread = svc.store.upsert_thread(
        ThreadUpsert(summary="Canonical title", project_slug=proj.slug)
    )
    svc.store.attach_external_identity(
        thread.id,
        normalize_external_identity(WorkSource.github, "github.com", "acme", "app", 1),
    )
    out = svc.upsert_progress(
        ProgressUpsert(
            project_slug=proj.slug,
            thread_id=thread.id,
            focus="new focus only",
        )
    )
    assert out["thread"]["focus"] == "new focus only"
    assert out["thread"]["title"] == "Canonical title"


def test_sync_thread_skips_external_and_does_not_patch() -> None:
    cfg = ForgeConfig(
        provider=ForgeProvider.github,
        token="tok",
        owner="o",
        repo="r",
        board_enabled=True,
    )
    board = BoardForgeSync(cfg, lambda _k: "5", lambda _k, _v: None)
    from datetime import UTC, datetime

    from adhd_hub.models import EnergyLevel, Thread, ThreadStatus

    thread = Thread(
        id="t1",
        summary="Sum",
        status=ThreadStatus.open,
        energy=EnergyLevel.unknown,
        work_source=WorkSource.github,
        external_provider=WorkSource.github,
        external_host="github.com",
        external_owner="o",
        external_repo="r",
        external_issue_number=5,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    with patch("httpx.Client") as client_cls:
        result = board.sync_thread(thread)
        client_cls.assert_not_called()
    assert result.get("skipped") is True


def test_external_publish_status_block_only_no_state_title_labels() -> None:
    cfg = ForgeConfig(
        provider=ForgeProvider.github,
        token="tok",
        owner="o",
        repo="r",
        board_enabled=True,
        publish_hub_status_block=True,
    )
    board = BoardForgeSync(cfg, lambda _k: "5", lambda _k, _v: None)
    from datetime import UTC, datetime

    from adhd_hub.models import EnergyLevel, Thread, ThreadStatus

    thread = Thread(
        id="t1",
        summary="Sum",
        status=ThreadStatus.done,
        energy=EnergyLevel.unknown,
        work_source=WorkSource.github,
        external_provider=WorkSource.github,
        external_host="github.com",
        external_owner="o",
        external_repo="r",
        external_issue_number=5,
        focus="F",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.json.return_value = {"body": "user body\n"}
    patch_resp = MagicMock()
    patch_resp.status_code = 200
    patch_resp.content = b"{}"
    patch_resp.json.return_value = {}
    patch_resp.raise_for_status = MagicMock()
    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.return_value = get_resp
        client.patch.return_value = patch_resp
        out = board.sync_thread(thread)
    assert out.get("status_block_only") is True
    payload = client.patch.call_args.kwargs["json"]
    assert "state" not in payload
    assert "title" not in payload
    assert "labels" not in payload
    assert "body" in payload


def test_board_mirror_local_does_not_create_new_issues() -> None:
    cfg = ForgeConfig(
        provider=ForgeProvider.github,
        token="tok",
        owner="o",
        repo="r",
        board_enabled=True,
        board_mirror_local=True,
    )
    board = BoardForgeSync(cfg, lambda _k: None, lambda _k, _v: None)
    from datetime import UTC, datetime

    from adhd_hub.models import EnergyLevel, Thread, ThreadStatus

    thread = Thread(
        id="local1",
        summary="Local only",
        status=ThreadStatus.open,
        energy=EnergyLevel.unknown,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    with patch("httpx.Client") as client_cls:
        out = board.sync_thread(thread)
        client_cls.assert_not_called()
    assert out.get("reason") == "board_mirror_preserve_only"


def test_external_publish_status_block_uses_pinned_owner_repo() -> None:
    cfg = ForgeConfig(
        provider=ForgeProvider.github,
        token="tok",
        owner="configOwner",
        repo="configRepo",
        board_enabled=True,
        publish_hub_status_block=True,
    )
    board = BoardForgeSync(cfg, lambda _k: "5", lambda _k, _v: None)
    from datetime import UTC, datetime

    from adhd_hub.models import EnergyLevel, Thread, ThreadStatus

    thread = Thread(
        id="t1",
        summary="Sum",
        status=ThreadStatus.open,
        energy=EnergyLevel.unknown,
        work_source=WorkSource.github,
        external_provider=WorkSource.github,
        external_host="github.com",
        external_owner="pinnedowner",
        external_repo="pinnedrepo",
        external_issue_number=5,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.json.return_value = {"body": "user body\n"}
    patch_resp = MagicMock()
    patch_resp.status_code = 200
    patch_resp.content = b"{}"
    patch_resp.json.return_value = {}
    patch_resp.raise_for_status = MagicMock()
    urls: list[str] = []
    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value

        def capture_get(url, *a, **k):
            urls.append(url)
            return get_resp

        def capture_patch(url, *a, **k):
            urls.append(url)
            return patch_resp

        client.get.side_effect = capture_get
        client.patch.side_effect = capture_patch
        board.sync_thread(thread)
    assert any("pinnedowner/pinnedrepo/issues/5" in u for u in urls)
    assert not any("configOwner/configRepo/issues/5" in u for u in urls)


def test_adhd_inbox_discovery_requires_authors() -> None:
    cfg = ForgeConfig(
        provider=ForgeProvider.github,
        token="t",
        owner="o",
        repo="r",
        board_enabled=True,
        board_inbox_enabled=True,
        issue_import_policy=IssueImportPolicy.adhd_inbox,
        board_inbox_authors=[],
    )
    out = discover_issue_payloads(cfg)
    assert isinstance(out, dict)
    assert out["reason"] == "board_inbox_authors_required"


def test_adhd_inbox_discovery_respects_inbox_disabled() -> None:
    cfg = ForgeConfig(
        provider=ForgeProvider.github,
        token="t",
        owner="o",
        repo="r",
        board_enabled=True,
        board_inbox_enabled=False,
        issue_import_policy=IssueImportPolicy.adhd_inbox,
        board_inbox_authors=["bot"],
    )
    out = discover_issue_payloads(cfg)
    assert isinstance(out, dict)
    assert out["reason"] == "board_inbox_disabled"


def test_mark_done_unlinked_github_project_default_stays_local(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    proj = svc.store.upsert_project(
        ProjectUpsert(title="App", default_work_source=WorkSource.github)
    )
    thread = svc.store.upsert_thread(
        ThreadUpsert(summary="Local continuity only", project_slug=proj.slug)
    )
    with patch.object(BoardForgeSync, "_set_issue_state") as set_state:
        done = svc.mark_done(thread.id)
    set_state.assert_not_called()
    assert done is not None
    assert done.status.value == "done"

    cfg = ForgeConfig(
        provider=ForgeProvider.github,
        token="t",
        owner="o",
        repo="r",
        board_enabled=True,
        issue_import_policy=IssueImportPolicy.manual,
    )
    assert discover_issue_payloads(cfg) == []


def test_assigned_to_me_does_not_use_inbox_authors() -> None:
    cfg = ForgeConfig(
        provider=ForgeProvider.github,
        token="",
        owner="o",
        repo="r",
        board_enabled=True,
        issue_import_policy=IssueImportPolicy.assigned_to_me,
        board_inbox_authors=["alice"],
    )
    out = resolve_assigned_to_me_login(cfg)
    assert isinstance(out, dict)
    assert out["error"] == "assigned_to_me_login_unavailable"


def test_sync_now_reconciles_linked_thread_when_project_forge_repo_differs(
    tmp_path: Path,
) -> None:
    svc = _service(tmp_path)
    proj = svc.store.upsert_project(
        ProjectUpsert(title="App", forge_owner="ownerB", forge_repo="repoB")
    )
    thread = svc.store.upsert_thread(
        ThreadUpsert(summary="Pinned", project_slug=proj.slug, focus="stay")
    )
    identity = normalize_external_identity(
        WorkSource.github, "github.com", "ownerA", "repoA", 3
    )
    svc.store.attach_external_identity(thread.id, identity)
    save_forge_config(
        svc.settings.data_dir,
        ForgeConfig(
            provider=ForgeProvider.github,
            token="tok",
            owner="ownerB",
            repo="repoB",
            board_enabled=True,
            wiki_enabled=False,
            issue_import_policy=IssueImportPolicy.manual,
        ),
    )

    get_urls: list[str] = []

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "number": 3,
                "title": "From A",
                "state": "closed",
                "labels": [],
                "updated_at": "2026-09-12T02:00:00Z",
            }

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, *args, **kwargs):
            get_urls.append(url)
            return FakeResp()

        def close(self):
            return None

    with (
        patch("adhd_hub.forge.scaffold.push_primary_scaffold", return_value={}),
        patch.object(svc._forge, "preview_forge_import", return_value={}),
        patch("adhd_hub.forge.wiki_sync.WikiForgeSync.push_wiki_tree", return_value={}),
        patch("httpx.Client", FakeClient),
    ):
        result = svc.sync_forge_now()

    assert any("ownera/repoa/issues/3" in u for u in get_urls)
    assert not any("ownerb/repob/issues/3" in u for u in get_urls)
    refreshed = svc.store.get_thread(thread.id)
    assert refreshed is not None
    assert refreshed.external_issue_state == ExternalIssueState.closed
    assert refreshed.summary == "From A"
    assert refreshed.focus == "stay"
    assert refreshed.status.value == "open"
    assert "reconcile" in result
