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
            workspace_paths=[str(tmp_path / "sites" / "my-website")],
        )
    )
    assert proj.slug == "my-website"
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
