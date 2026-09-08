from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.backup import export_data_dir, import_data_dir
from adhd_hub.config import Settings
from adhd_hub.forge.config import ForgeConfig, ForgeProvider
from adhd_hub.forge.wiki_sync import WikiForgeSync
from adhd_hub.models import ProjectUpsert
from adhd_hub.service import HubService


def test_backup_roundtrip(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "prefs.json").write_text('{"timezone":"UTC"}', encoding="utf-8")
    wiki = data / "wiki" / "projects" / "demo"
    wiki.mkdir(parents=True)
    (wiki / "PROGRESS.md").write_text("# Demo\n\nhello\n", encoding="utf-8")
    (data / "hub.sqlite3").write_bytes(b"sqlite-placeholder")

    archive = export_data_dir(data)
    dest = tmp_path / "restored"
    result = import_data_dir(dest, archive)
    assert "wiki" in result["restored"]
    assert (dest / "wiki" / "projects" / "demo" / "PROGRESS.md").read_text(
        encoding="utf-8"
    ).startswith("# Demo")


def test_title_from_progress() -> None:
    assert HubService._title_from_progress("# Cool Project\n\nbody", "x") == "Cool Project"
    assert HubService._title_from_progress(None, "my-app") == "My App"


def test_preview_and_import_from_forge(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", auth_token="secret")
    svc = HubService(settings)
    cfg = ForgeConfig(
        provider=ForgeProvider.gitea,
        base_url="https://git.example/api/v1",
        token="t",
        owner="alex",
        repo="projects",
        wiki_enabled=True,
        wiki_path="",
    )
    svc.save_forge_config(cfg)

    remote = {
        "skipped": False,
        "projects": [
            {"slug": "alpha", "has_progress": True, "path": "projects/alpha/PROGRESS.md"},
            {"slug": "beta", "has_progress": True, "path": "projects/beta/PROGRESS.md"},
        ],
        "errors": [],
    }
    with patch.object(WikiForgeSync, "list_remote_project_slugs", return_value=remote):
        preview = svc.preview_forge_import()
    assert preview["importable_count"] == 2

    # Register alpha locally first
    svc.upsert_project(ProjectUpsert(slug="alpha", title="Alpha"))
    svc.wiki.write_progress_raw("alpha", "# Alpha\n\nlocal\n")

    with patch.object(WikiForgeSync, "list_remote_project_slugs", return_value=remote):
        preview2 = svc.preview_forge_import()
    assert preview2["importable_count"] == 1
    assert preview2["candidates"][0]["status"] == "registered"

    content = "# Beta From Forge\n\n## Progress log\n\nok\n"

    def fake_read(rel: str) -> str | None:
        if rel.endswith("beta/PROGRESS.md"):
            return content
        if rel == "INDEX.md":
            return "# index\n"
        return None

    with (
        patch.object(WikiForgeSync, "list_remote_project_slugs", return_value=remote),
        patch.object(WikiForgeSync, "read_file_text", side_effect=fake_read),
    ):
        out = svc.import_from_forge(slugs=["beta"])
    assert len(out["imported"]) == 1
    assert out["imported"][0]["slug"] == "beta"
    assert svc.store.get_project("beta") is not None
    assert "Beta From Forge" in (svc.wiki.read_progress("beta") or "")


def test_list_remote_decodes_file() -> None:
    cfg = ForgeConfig(
        provider=ForgeProvider.github,
        token="t",
        owner="o",
        repo="r",
        wiki_enabled=True,
    )
    sync = WikiForgeSync(cfg)
    encoded = base64.b64encode(b"# Hi\n").decode("ascii")
    fake_client = MagicMock()
    with (
        patch.object(
            WikiForgeSync,
            "_get_file",
            return_value={"type": "file", "content": encoded, "encoding": "base64"},
        ),
        patch("adhd_hub.forge.wiki_sync.httpx.Client") as client_cls,
    ):
        client_cls.return_value.__enter__.return_value = fake_client
        text = sync.read_file_text("projects/x/PROGRESS.md")
    assert text == "# Hi\n"


def test_admin_export_api(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="secret",
        host="127.0.0.1",
        port=8787,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        r = client.get("/api/admin/export")
        assert r.status_code == 401
        r = client.get(
            "/api/admin/export",
            headers={"Authorization": "Bearer secret"},
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/zip")
        assert r.content[:2] == b"PK"
