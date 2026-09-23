"""Wave 6.C organiser suggestions require human confirm before apply."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.models import OrganiseApplyRequest, ProjectUpsert, ThreadUpsert
from adhd_hub.organiser import suggest_tags_for_project
from adhd_hub.service import HubService


def test_suggest_tags_from_keywords(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    proj = service.upsert_project(
        ProjectUpsert(title="Homelab Docker docs", slug="homelab-docs", tags=[])
    )
    service.upsert_thread(
        ThreadUpsert(
            summary="Wire MCP forge path",
            project_slug="homelab-docs",
            focus="Improve forge sync docs",
            source_tool="pytest",
        )
    )
    threads = service.store.list_threads(project_slug="homelab-docs", limit=10)
    suggestion = suggest_tags_for_project(proj, threads)
    assert "homelab" in suggestion["suggested_tags"] or "docs" in suggestion["suggested_tags"]
    assert suggestion["current_tags"] == []


def test_organise_apply_requires_explicit_items(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", auth_token="secret")
    service = HubService(settings)
    service.upsert_project(ProjectUpsert(title="API work", slug="api-work", tags=[]))
    with TestClient(create_app(settings)) as client:
        headers = {"Authorization": "Bearer secret"}
        sug = client.get("/api/projects/organise/suggestions", headers=headers)
        assert sug.status_code == 200
        body = sug.json()
        assert body["auto_applied"] is False

        # Empty apply does nothing
        empty = client.post(
            "/api/projects/organise/apply",
            headers=headers,
            json={"items": []},
        )
        assert empty.status_code == 200
        assert empty.json()["applied"] == []

        applied = client.post(
            "/api/projects/organise/apply",
            headers=headers,
            json={"items": [{"slug": "api-work", "tags": ["api", "docs"]}]},
        )
        assert applied.status_code == 200
        out = applied.json()
        assert out["auto_applied"] is False
        assert out["applied"][0]["tags"] == ["api", "docs"]

    again = service.store.get_project("api-work")
    assert again is not None
    assert again.tags == ["api", "docs"]


def test_organise_apply_model_normalizes_tags() -> None:
    req = OrganiseApplyRequest.model_validate(
        {"items": [{"slug": "x", "tags": ["Home Lab", "docs", "docs"]}]}
    )
    assert req.items[0].tags == ["home-lab", "docs"]


def test_apply_preserves_project_settings_and_skips_archived(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    before = service.upsert_project(
        ProjectUpsert(title="API", slug="api", tags=["docs"], default_energy="high")
    )
    service.apply_project_organisation({"items": [{"slug": "api", "tags": ["api"]}]})
    after = service.store.get_project("api")
    assert after.default_energy == before.default_energy
    assert after.tags == ["docs", "api"]

    service.store.set_project_archived("api", archived=True)
    result = service.apply_project_organisation({"items": [{"slug": "api", "tags": ["ci"]}]})
    assert result["applied"] == []
    assert result["skipped"] == [{"slug": "api", "reason": "archived"}]
    assert service.store.get_project("api").tags == ["docs", "api"]


def test_suggestions_and_apply_respect_available_tag_slots(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    tags = [f"tag-{i}" for i in range(8)]
    proj = service.upsert_project(ProjectUpsert(title="API docs", slug="api", tags=tags))
    assert suggest_tags_for_project(proj, [])["suggested_tags"] == []
    result = service.apply_project_organisation({"items": [{"slug": "api", "tags": ["ci"]}]})
    assert result["applied"] == []
    assert result["skipped"] == [{"slug": "api", "reason": "tag_limit"}]
    assert service.store.get_project("api").tags == tags
