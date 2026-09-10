from __future__ import annotations

from pathlib import Path

from adhd_hub.config import Settings
from adhd_hub.forge.config import ForgeConfig, ForgeProvider, save_forge_config
from adhd_hub.forge.migrate_wiki_paths import apply_forge_wiki_path_cleanup
from adhd_hub.models import ProjectUpsert
from adhd_hub.service import HubService


def test_forge_wiki_path_cleanup_dry_run_and_apply(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", auth_token="secret")
    svc = HubService(settings)
    save_forge_config(
        settings.data_dir,
        ForgeConfig(
            provider=ForgeProvider.gitea,
            base_url="https://git.example/api/v1",
            token="t",
            owner="alex",
            repo="memory",
            wiki_enabled=True,
            wiki_path="adhd-hub/wiki",
        ),
    )
    svc.upsert_project(
        ProjectUpsert(
            slug="demo",
            title="Demo",
            forge_wiki_path="adhd-hub/wiki",
            default_energy="medium",
        )
    )
    plan = apply_forge_wiki_path_cleanup(settings, dry_run=True)
    assert plan["count"] >= 2
    assert plan["applied"] is False

    applied = apply_forge_wiki_path_cleanup(settings, dry_run=False)
    assert applied["applied"] is True
    assert svc.forge_config().wiki_path == ""
    proj = svc.store.get_project("demo")
    assert proj is not None
    assert proj.forge_wiki_path == ""
    assert proj.default_energy.value == "medium"
