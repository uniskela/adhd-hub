"""Wave 6.B — project tags and last-touch cues."""

from __future__ import annotations

from pathlib import Path

from adhd_hub.config import Settings
from adhd_hub.models import ProjectUpsert, ThreadUpsert, normalize_project_tags
from adhd_hub.service import HubService


def test_normalize_project_tags():
    assert normalize_project_tags(["Home Lab", "docs", "docs", "Bad Tag!!"]) == [
        "home-lab",
        "docs",
        "bad-tag",
    ]
    assert normalize_project_tags(["a"] * 20) == ["a"]
    assert normalize_project_tags(None) == []


def test_project_tags_and_last_touch(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    proj = service.upsert_project(
        ProjectUpsert(
            title="Wave Six Demo",
            slug="wave-six-demo",
            tags=["Home Lab", "Docs", "docs"],
        )
    )
    assert proj.tags == ["home-lab", "docs"]

    thread = service.upsert_thread(
        ThreadUpsert(
            summary="Touch the project",
            project_slug="wave-six-demo",
            focus="Bump last_touch",
            source_tool="pytest",
        )
    )
    listed = {p["slug"]: p for p in service.list_projects()}
    row = listed["wave-six-demo"]
    assert row["tags"] == ["home-lab", "docs"]
    assert row["last_touch_at"]
    assert thread.updated_at.isoformat()[:19] in row["last_touch_at"]

    # Omitting tags on upsert preserves existing tags.
    again = service.upsert_project(
        ProjectUpsert(title="Wave Six Demo", slug="wave-six-demo", description="kept")
    )
    assert again.tags == ["home-lab", "docs"]

    cleared = service.upsert_project(
        ProjectUpsert(title="Wave Six Demo", slug="wave-six-demo", tags=[])
    )
    assert cleared.tags == []
