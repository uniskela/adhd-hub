from __future__ import annotations

from pathlib import Path

from adhd_hub.config import Settings
from adhd_hub.models import ProgressUpsert, ProjectUpsert, ThreadUpsert
from adhd_hub.service import HubService
from adhd_hub.store import normalize_workspace_path, slugify


def test_project_resolve_and_progress(tmp_path: Path) -> None:
    service = HubService(
        Settings(
            data_dir=tmp_path / "data",
            auth_token="test",
            stale_days=3,
            digest_limit=5,
            overlap_limit=5,
        )
    )
    proj = service.upsert_project(
        ProjectUpsert(
            title="My Website",
            slug="my-website",
            repo_url="https://github.com/example/my-website/",
            workspace_paths=[str(tmp_path / "sites" / "my-website")],
        )
    )
    assert proj.slug == "my-website"
    assert proj.repo_url == "https://github.com/example/my-website"
    resolved = service.resolve_project(
        workspace_path=str(tmp_path / "sites" / "my-website" / "src"),
        create_if_missing=False,
    )
    assert resolved and resolved.slug == "my-website"

    out = service.upsert_progress(
        ProgressUpsert(
            content="## Done\n- Scaffold\n## Next\n- Auth",
            workspace_path=str(tmp_path / "sites" / "my-website"),
            source_tool="cursor",
        )
    )
    assert out["project_slug"] == "my-website"
    assert out["thread_id"]

    updated = service.upsert_project(
        ProjectUpsert(title="My Website", slug="my-website", repo_url=None)
    )
    assert updated.repo_url is None


def test_project_repo_url_rejects_credentials_and_non_http_schemes() -> None:
    import pytest

    for value in ("git@example.com:owner/repo.git", "file:///tmp/repo", "https://u:p@example.com/r"):
        with pytest.raises(ValueError, match="repository URL"):
            ProjectUpsert(title="Unsafe", repo_url=value)


def test_upsert_thread_creates_project(tmp_path: Path) -> None:
    service = HubService(
        Settings(data_dir=tmp_path / "data", auth_token="t")
    )
    t = service.upsert_thread(
        ThreadUpsert(
            summary="Chrome extension popup redesign",
            workspace_path=r"Z:\Projects\chrome-ext",
            source_tool="cursor",
        )
    )
    assert t.project_slug == "chrome-ext"
    assert service.store.get_project("chrome-ext") is not None


def test_project_rename_and_delete(tmp_path: Path) -> None:
    service = HubService(
        Settings(data_dir=tmp_path / "data", auth_token="t")
    )
    service.upsert_project(
        ProjectUpsert(
            title="Alpha",
            slug="alpha",
            workspace_paths=[str(tmp_path / "alpha")],
        )
    )
    service.upsert_progress(
        ProgressUpsert(
            project_slug="alpha",
            content="## Done\n- start\n## Next\n- finish",
            source_tool="cursor",
        )
    )
    assert (tmp_path / "data" / "wiki" / "projects" / "alpha" / "PROGRESS.md").is_file()

    renamed = service.rename_project("alpha", "alpha-app", title="Alpha App")
    assert renamed["project"]["slug"] == "alpha-app"
    assert service.store.get_project("alpha") is None
    assert service.store.get_project("alpha-app") is not None
    assert (tmp_path / "data" / "wiki" / "projects" / "alpha-app" / "PROGRESS.md").is_file()
    assert not (tmp_path / "data" / "wiki" / "projects" / "alpha").exists()
    threads = service.store.list_threads(project_slug="alpha-app", limit=10)
    assert threads and all(t.project_slug == "alpha-app" for t in threads)

    # Safe delete preserves local wiki
    out = service.delete_project("alpha-app", delete_progress=False)
    assert out["store"]["deleted"] == "alpha-app"
    assert (tmp_path / "data" / "wiki" / "projects" / "alpha-app" / "PROGRESS.md").is_file()
    assert service.store.get_project("alpha-app") is None


def test_create_organisation_project_without_repo(tmp_path: Path) -> None:
    """Organisation / no-repo projects omit repo_url and still nest via parent_slug."""
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    parent = service.upsert_project(
        ProjectUpsert(title="Homelab", slug="homelab", repo_url=None)
    )
    assert parent.repo_url is None
    assert parent.forge_owner is None
    assert parent.forge_repo is None

    child = service.upsert_project(
        ProjectUpsert(
            title="DNS",
            slug="dns",
            parent_slug="homelab",
            repo_url=None,
        )
    )
    assert child.repo_url is None
    assert child.parent_slug == "homelab"

    overview = service.overview()
    by_slug = {p["slug"]: p for p in overview["projects"]}
    assert by_slug["homelab"]["repo_url"] is None
    assert by_slug["dns"]["parent_slug"] == "homelab"


def test_forge_sync_skips_organisation_project_without_repo(tmp_path: Path) -> None:
    from adhd_hub.forge.config import project_has_forge_repo_binding

    assert not project_has_forge_repo_binding(repo_url=None)
    assert not project_has_forge_repo_binding(repo_url="", forge_owner="", forge_repo="")
    assert project_has_forge_repo_binding(
        repo_url="https://github.com/acme/widgets"
    )
    assert project_has_forge_repo_binding(forge_owner="acme", forge_repo="widgets")

    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_project(ProjectUpsert(title="Org Folders", slug="org-folders"))
    out = service.sync_forge_project("org-folders")
    assert out["skipped"] is True
    assert out["reason"] == "no_repository"
    assert out["ok"] is True


def test_project_rename_conflict(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_project(ProjectUpsert(title="A", slug="a"))
    service.upsert_project(ProjectUpsert(title="B", slug="b"))
    try:
        service.rename_project("a", "b")
        raise AssertionError("expected conflict")
    except ValueError as exc:
        assert str(exc) == "conflict"


def test_normalize_workspace_path() -> None:
    assert normalize_workspace_path(r"Z:\Projects\Foo") == normalize_workspace_path(
        "z:/Projects/Foo/"
    )
    assert slugify("My Website!") == "my-website"


def test_project_parent_hierarchy_depth_and_cycle(tmp_path: Path) -> None:
    import pytest

    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    work = service.upsert_project(ProjectUpsert(title="Work", slug="work"))
    assert work.parent_slug is None

    hub = service.upsert_project(
        ProjectUpsert(title="ADHD Hub", slug="adhd-hub", parent_slug="work")
    )
    assert hub.parent_slug == "work"

    # Unlimited depth: nest under a child.
    deep = service.upsert_project(
        ProjectUpsert(title="Too Deep", slug="too-deep", parent_slug="adhd-hub")
    )
    assert deep.parent_slug == "adhd-hub"

    with pytest.raises(ValueError, match="cannot_nest_under_self"):
        service.upsert_project(
            ProjectUpsert(title="Work", slug="work", parent_slug="work")
        )

    with pytest.raises(ValueError, match="parent_not_found"):
        service.upsert_project(
            ProjectUpsert(title="Orphan", slug="orphan", parent_slug="missing-parent")
        )

    # Cycle: cannot nest an ancestor under a descendant.
    with pytest.raises(ValueError, match="cycle_detected"):
        service.upsert_project(
            ProjectUpsert(title="Work", slug="work", parent_slug="too-deep")
        )

    # Projects with children may still become children of another branch.
    service.upsert_project(ProjectUpsert(title="Personal", slug="personal"))
    moved = service.upsert_project(
        ProjectUpsert(title="Work", slug="work", parent_slug="personal")
    )
    assert moved.parent_slug == "personal"
    assert service.store.get_project("adhd-hub").parent_slug == "work"

    overview = service.overview()
    by_slug = {p["slug"]: p for p in overview["projects"]}
    assert by_slug["adhd-hub"]["parent_slug"] == "work"
    assert by_slug["work"]["parent_slug"] == "personal"
    assert by_slug["too-deep"]["parent_slug"] == "adhd-hub"
    assert "sort_order" in by_slug["work"]


def test_project_move_reorders_siblings(tmp_path: Path) -> None:
    import pytest

    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_project(ProjectUpsert(title="Alpha", slug="alpha"))
    service.upsert_project(ProjectUpsert(title="Beta", slug="beta"))
    service.upsert_project(ProjectUpsert(title="Gamma", slug="gamma"))

    # Nest beta under alpha, then gamma under alpha before beta.
    service.move_project("beta", {"parent_slug": "alpha"})
    service.move_project("gamma", {"parent_slug": "alpha", "before_slug": "beta"})
    children = service.store.list_child_slugs("alpha")
    assert children == ["gamma", "beta"]

    # Reorder gamma after beta (append).
    service.move_project("gamma", {"parent_slug": "alpha", "before_slug": None})
    assert service.store.list_child_slugs("alpha") == ["beta", "gamma"]

    # Promote beta to top-level before alpha.
    service.move_project("beta", {"parent_slug": None, "before_slug": "alpha"})
    roots = [
        p.slug
        for p in service.store.list_projects()
        if not p.parent_slug
    ]
    assert roots.index("beta") < roots.index("alpha")

    with pytest.raises(ValueError, match="cycle_detected"):
        service.move_project("alpha", {"parent_slug": "gamma"})


def test_project_rename_preserves_parent_links(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_project(ProjectUpsert(title="Work", slug="work"))
    service.upsert_project(
        ProjectUpsert(title="Infra", slug="infra", parent_slug="work")
    )
    renamed = service.rename_project("work", "work-life", title="Work Life")
    assert renamed["project"]["slug"] == "work-life"
    child = service.store.get_project("infra")
    assert child is not None
    assert child.parent_slug == "work-life"


def test_project_archive_clears_child_parents(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_project(ProjectUpsert(title="Personal", slug="personal"))
    service.upsert_project(
        ProjectUpsert(title="Reading", slug="reading", parent_slug="personal")
    )
    service.archive_project("personal")
    child = service.store.get_project("reading")
    assert child is not None
    assert child.parent_slug is None
    assert child.archived_at is None
    parent = service.store.get_project("personal")
    assert parent is not None
    assert parent.archived_at is not None


def test_project_delete_nulls_child_parent_via_fk(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_project(ProjectUpsert(title="Work", slug="work"))
    service.upsert_project(
        ProjectUpsert(title="Hub", slug="hub", parent_slug="work")
    )
    service.delete_project("work", delete_progress=False)
    child = service.store.get_project("hub")
    assert child is not None
    assert child.parent_slug is None


def test_parent_project_thread_scope_includes_descendants(tmp_path: Path) -> None:
    """Selecting a parent My-work filter includes nested child threads (any depth)."""
    from adhd_hub.models import ThreadStatus

    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_project(ProjectUpsert(title="AJP Stuff", slug="ajp-stuff"))
    service.upsert_project(
        ProjectUpsert(
            title="AJP dedicated n8n migration",
            slug="ajp-n8n",
            parent_slug="ajp-stuff",
        )
    )
    service.upsert_project(
        ProjectUpsert(title="Deep child", slug="ajp-deep", parent_slug="ajp-n8n")
    )
    service.upsert_project(ProjectUpsert(title="Other", slug="other"))

    service.upsert_thread(
        ThreadUpsert(summary="Parent-owned", project_slug="ajp-stuff", status=ThreadStatus.open)
    )
    for i in range(3):
        service.upsert_thread(
            ThreadUpsert(
                summary=f"Child open {i}",
                project_slug="ajp-n8n",
                status=ThreadStatus.open,
            )
        )
    service.upsert_thread(
        ThreadUpsert(summary="Grandchild", project_slug="ajp-deep", status=ThreadStatus.open)
    )
    service.upsert_thread(
        ThreadUpsert(summary="Other work", project_slug="other", status=ThreadStatus.open)
    )
    service.upsert_thread(
        ThreadUpsert(
            summary="Child done",
            project_slug="ajp-n8n",
            status=ThreadStatus.done,
        )
    )

    scope = service.project_thread_scope("ajp-stuff")
    assert scope is not None
    assert set(scope) == {"ajp-stuff", "ajp-n8n", "ajp-deep"}

    open_under_parent = service.list_threads_public(
        status=ThreadStatus.open, project_slug="ajp-stuff", limit=50
    )
    open_slugs = {t["project_slug"] for t in open_under_parent}
    assert open_slugs == {"ajp-stuff", "ajp-n8n", "ajp-deep"}
    assert len(open_under_parent) == 5  # 1 parent + 3 child + 1 grandchild

    leaf_only = service.list_threads_public(
        status=ThreadStatus.open, project_slug="ajp-deep", limit=50
    )
    assert {t["project_slug"] for t in leaf_only} == {"ajp-deep"}
    assert len(leaf_only) == 1

    mid_parent = service.list_threads_public(
        status=ThreadStatus.open, project_slug="ajp-n8n", limit=50
    )
    assert {t["project_slug"] for t in mid_parent} == {"ajp-n8n", "ajp-deep"}
    assert len(mid_parent) == 4  # 3 on ajp-n8n + 1 grandchild

    deep_only = leaf_only
    assert deep_only[0]["project_slug"] == "ajp-deep"

    done_under_parent = service.list_threads_public(
        status=ThreadStatus.done, project_slug="ajp-stuff", limit=50
    )
    assert len(done_under_parent) == 1
    assert done_under_parent[0]["project_slug"] == "ajp-n8n"


def test_parent_rail_counts_aggregate_descendants(tmp_path: Path) -> None:
    """Rail open counts on parents roll up descendant threads."""
    from adhd_hub.models import ThreadStatus

    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_project(ProjectUpsert(title="AJP Stuff", slug="ajp-stuff"))
    service.upsert_project(
        ProjectUpsert(title="Child", slug="ajp-n8n", parent_slug="ajp-stuff")
    )
    for i in range(12):
        service.upsert_thread(
            ThreadUpsert(
                summary=f"Migration step {i}",
                project_slug="ajp-n8n",
                status=ThreadStatus.open,
            )
        )

    by_slug = {p["slug"]: p for p in service.list_projects()}
    assert by_slug["ajp-n8n"]["counts"]["open"] == 12
    assert by_slug["ajp-stuff"]["counts"]["open"] == 12

    detail = service.get_project_detail("ajp-stuff")
    assert detail is not None
    assert detail["counts"]["open"] == 12
    assert set(detail["scope_slugs"]) == {"ajp-stuff", "ajp-n8n"}
    assert len(detail["threads"]) == 12


def test_parent_rail_last_touch_uses_descendant_activity(tmp_path: Path) -> None:
    """Parent rail last_touch_at follows the newest descendant thread touch."""
    from adhd_hub.models import ThreadStatus

    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_project(ProjectUpsert(title="AJP Stuff", slug="ajp-stuff"))
    service.upsert_project(
        ProjectUpsert(title="Child", slug="ajp-n8n", parent_slug="ajp-stuff")
    )
    parent_thread = service.upsert_thread(
        ThreadUpsert(
            summary="Older parent work",
            project_slug="ajp-stuff",
            status=ThreadStatus.open,
        )
    )
    child_thread = service.upsert_thread(
        ThreadUpsert(
            summary="Newer child work",
            project_slug="ajp-n8n",
            status=ThreadStatus.open,
        )
    )
    assert child_thread.updated_at >= parent_thread.updated_at

    by_slug = {p["slug"]: p for p in service.list_projects()}
    parent_touch = by_slug["ajp-stuff"]["last_touch_at"]
    child_touch = by_slug["ajp-n8n"]["last_touch_at"]
    assert parent_touch
    assert child_touch
    assert parent_touch == child_touch
    assert child_thread.updated_at.isoformat()[:19] in parent_touch


def test_rewrite_all_on_parent_includes_descendant_open_threads(tmp_path: Path) -> None:
    """Rewrite-all on a parent no-ops with AI off but scopes descendant open threads."""
    from adhd_hub.models import ThreadStatus

    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_project(ProjectUpsert(title="AJP Stuff", slug="ajp-stuff"))
    service.upsert_project(
        ProjectUpsert(title="Child", slug="ajp-n8n", parent_slug="ajp-stuff")
    )
    service.upsert_thread(
        ThreadUpsert(summary="Own", project_slug="ajp-stuff", status=ThreadStatus.open)
    )
    service.upsert_thread(
        ThreadUpsert(summary="Child A", project_slug="ajp-n8n", status=ThreadStatus.open)
    )
    service.upsert_thread(
        ThreadUpsert(summary="Child B", project_slug="ajp-n8n", status=ThreadStatus.open)
    )

    out = service.rewrite_project_scan_lines("ajp-stuff")
    assert out["ai_attempted"] is False
    assert out["total"] == 3
    assert {t["project_slug"] for t in out["threads"]} == {"ajp-stuff", "ajp-n8n"}


def test_rewrite_all_pages_beyond_default_limit(tmp_path: Path) -> None:
    """Rewrite-all pages through every scoped open thread, not just the first page."""
    from adhd_hub.models import ThreadStatus

    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_project(ProjectUpsert(title="AJP Stuff", slug="ajp-stuff"))
    service.upsert_project(
        ProjectUpsert(title="Child", slug="ajp-n8n", parent_slug="ajp-stuff")
    )
    for i in range(5):
        service.upsert_thread(
            ThreadUpsert(
                summary=f"Scoped open {i}",
                project_slug="ajp-n8n",
                status=ThreadStatus.open,
            )
        )

    # Page size 2 would previously stop after two threads and report total=2.
    out = service.rewrite_project_scan_lines("ajp-stuff", limit=2)
    assert out["ai_attempted"] is False
    assert out["total"] == 5
    assert len(out["threads"]) == 5


def test_list_threads_id_keyset_stable_when_updated_at_shifts(tmp_path: Path) -> None:
    """ID keyset keeps paging complete when a prior page row bumps updated_at."""
    from adhd_hub.models import ThreadStatus
    from adhd_hub.store import Store

    store = Store(tmp_path / "hub.db")
    for i in range(4):
        store.upsert_thread(
            ThreadUpsert(
                summary=f"T{i}",
                project_slug="p",
                status=ThreadStatus.open,
            )
        )
    first = store.list_threads(
        status=ThreadStatus.open, project_slug="p", limit=2, order_by_id=True
    )
    assert len(first) == 2
    # Simulate pause_thread bumping updated_at on a thread already returned.
    store.pause_thread(first[0].id, "resume after keyset check")
    rest = store.list_threads(
        status=ThreadStatus.open,
        project_slug="p",
        limit=2,
        order_by_id=True,
        after_id=first[-1].id,
    )
    seen = {t.id for t in first} | {t.id for t in rest}
    assert len(seen) == 4
    assert {t.id for t in rest}.isdisjoint({t.id for t in first})


def test_list_threads_default_order_unchanged(tmp_path: Path) -> None:
    """Default list_threads callers keep updated_at DESC + OFFSET."""
    from datetime import UTC, datetime, timedelta

    from adhd_hub.models import ThreadStatus
    from adhd_hub.store import Store

    store = Store(tmp_path / "hub.db")
    older = store.upsert_thread(
        ThreadUpsert(summary="Older", project_slug="p", status=ThreadStatus.open)
    )
    newer = store.upsert_thread(
        ThreadUpsert(summary="Newer", project_slug="p", status=ThreadStatus.open)
    )
    # Force older to be more recent so DESC order is deterministic.
    with store._conn() as conn:
        stamp = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
        conn.execute(
            "UPDATE threads SET updated_at = ? WHERE id = ?",
            (stamp, older.id),
        )
    page = store.list_threads(status=ThreadStatus.open, project_slug="p", limit=10)
    assert [t.id for t in page] == [older.id, newer.id]
    page2 = store.list_threads(
        status=ThreadStatus.open, project_slug="p", limit=1, offset=1
    )
    assert [t.id for t in page2] == [newer.id]