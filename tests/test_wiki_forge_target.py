"""Wiki sync must target Hub memory repo, not per-project code forge_repo."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from adhd_hub.config import Settings
from adhd_hub.forge.config import (
    DEFAULT_CONNECTION_PROFILE_ID,
    ForgeConfig,
    ForgeConnectionProfile,
    ForgeProvider,
    save_forge_config,
)
from adhd_hub.models import ProjectUpsert, ProgressUpsert
from adhd_hub.service import HubService


def _svc(tmp_path: Path) -> HubService:
    return HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))


def _memory_and_code_bound(svc: HubService) -> str:
    """Global wiki = alex/projects; project code forge = alex/portainer-stacks."""
    save_forge_config(
        svc.settings.data_dir,
        ForgeConfig(
            provider=ForgeProvider.gitea,
            base_url="https://git.example/api/v1",
            web_base_url="https://git.example",
            token="wiki-token",
            owner="alex",
            repo="projects",
            wiki_enabled=True,
            wiki_path="",
            primary_memory_repo=True,
            connection_profiles=[
                ForgeConnectionProfile(
                    id=DEFAULT_CONNECTION_PROFILE_ID,
                    name="Gitea",
                    provider=ForgeProvider.gitea,
                    base_url="https://git.example/api/v1",
                    web_base_url="https://git.example",
                    token="wiki-token",
                )
            ],
            default_connection_profile_id=DEFAULT_CONNECTION_PROFILE_ID,
        ),
    )
    proj = svc.store.upsert_project(
        ProjectUpsert(
            title="Portainer Stacks",
            slug="portainer-stacks",
            forge_owner="alex",
            forge_repo="portainer-stacks",
            forge_connection_profile_id=DEFAULT_CONNECTION_PROFILE_ID,
        )
    )
    return proj.slug


def test_wiki_forge_config_ignores_project_code_repo(tmp_path: Path) -> None:
    svc = _svc(tmp_path)
    slug = _memory_and_code_bound(svc)
    wiki = svc.wiki_forge_config()
    project = svc.forge_config(slug)
    assert wiki.owner == "alex"
    assert wiki.repo == "projects"
    assert project.owner == "alex"
    assert project.repo == "portainer-stacks"


def test_upsert_progress_pushes_wiki_to_memory_repo_not_code_repo(
    tmp_path: Path,
) -> None:
    svc = _svc(tmp_path)
    slug = _memory_and_code_bound(svc)
    seen: list[tuple[str, str]] = []

    class CapturingWiki:
        def __init__(self, config):
            seen.append((config.owner, config.repo))

        def push_wiki_tree(self, wiki_dir):
            return {"uploaded": [], "errors": []}

    with patch("adhd_hub.service.WikiForgeSync", CapturingWiki), patch(
        "adhd_hub.forge.facade.WikiForgeSync", CapturingWiki
    ):
        svc.upsert_progress(
            ProgressUpsert(
                project_slug=slug,
                thread_id=None,
                force_new_thread=True,
                goal="Keep stacks tidy",
                focus="Check compose drift",
                next_steps=["Diff stacks"],
                resume_step="Open compose files",
            )
        )

    assert seen, "expected at least one wiki push"
    assert all(owner == "alex" and repo == "projects" for owner, repo in seen)
    assert not any(repo == "portainer-stacks" for _, repo in seen)


def test_sync_forge_now_does_not_dual_write_wiki_to_code_repos(
    tmp_path: Path,
) -> None:
    svc = _svc(tmp_path)
    _memory_and_code_bound(svc)
    svc.store.upsert_project(
        ProjectUpsert(
            title="Other App",
            slug="other-app",
            forge_owner="alex",
            forge_repo="other-app",
            forge_connection_profile_id=DEFAULT_CONNECTION_PROFILE_ID,
        )
    )
    seen: list[tuple[str, str]] = []

    class CapturingWiki:
        def __init__(self, config):
            seen.append((config.owner, config.repo))

        def push_wiki_tree(self, wiki_dir):
            return {"uploaded": ["INDEX.md"], "errors": []}

    with (
        patch("adhd_hub.forge.scaffold.push_primary_scaffold", return_value={}),
        patch.object(svc._forge, "preview_forge_import", return_value={}),
        patch("adhd_hub.forge.facade.WikiForgeSync", CapturingWiki),
    ):
        out = svc.sync_forge_now()

    assert seen
    assert all(repo == "projects" for _, repo in seen)
    assert "portainer-stacks" not in {r for _, r in seen}
    assert "other-app" not in {r for _, r in seen}
    assert len(out.get("per_project_wiki") or []) == 1
    assert out["per_project_wiki"][0].get("target") == "wiki_forge_config"


def test_status_block_progress_link_uses_wiki_config_not_issue_repo() -> None:
    from datetime import UTC, datetime

    from adhd_hub.forge.board_sync import BoardForgeSync
    from adhd_hub.models import Thread, ThreadStatus

    issue_cfg = ForgeConfig(
        provider=ForgeProvider.gitea,
        base_url="https://git.example/api/v1",
        web_base_url="https://git.example",
        token="t",
        owner="alex",
        repo="portainer-stacks",
        board_enabled=True,
        wiki_path="",
    )
    wiki_cfg = ForgeConfig(
        provider=ForgeProvider.gitea,
        base_url="https://git.example/api/v1",
        web_base_url="https://git.example",
        token="t",
        owner="alex",
        repo="projects",
        wiki_enabled=True,
        wiki_path="",
    )
    sync = BoardForgeSync(
        issue_cfg,
        lambda _k: None,
        lambda _k, _v: None,
        wiki_config=wiki_cfg,
    )
    thread = Thread(
        id="t1",
        summary="Compose drift",
        status=ThreadStatus.open,
        project_slug="portainer-stacks",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    body = sync.render_status_block(thread)
    assert "/alex/projects/" in body
    assert "portainer-stacks/PROGRESS.md" in body
    assert "/alex/portainer-stacks/" not in body
