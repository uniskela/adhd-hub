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
