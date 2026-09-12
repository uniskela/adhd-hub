"""v0.8.1 — forge connection profiles, selective bind, cross-host isolation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adhd_hub.config import Settings
from adhd_hub.forge.config import (
    DEFAULT_CONNECTION_PROFILE_ID,
    ForgeConfig,
    ForgeConnectionProfile,
    ForgeProvider,
    IssueImportPolicy,
    load_forge_config,
    profile_matches_identity_host,
    save_forge_config,
)
from adhd_hub.forge.repo_sync import credentials_apply_to_pinned, discover_issue_payloads
from adhd_hub.models import ProjectUpsert, ThreadUpsert
from adhd_hub.service import HubService
from adhd_hub.work_identity import (
    ExternalIssueState,
    WorkSource,
    normalize_external_identity,
)


def _svc(tmp_path: Path) -> HubService:
    return HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))


def test_legacy_forge_json_migrates_to_default_profile(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    path = data / "forge.json"
    path.write_text(
        '{"provider":"gitea","token":"sekret","owner":"alex","repo":"projects",'
        '"base_url":"https://git.pike.homes/api/v1",'
        '"web_base_url":"https://git.pike.homes",'
        '"board_enabled":true,"board_inbox_enabled":true,'
        '"issue_import_policy":"adhd_inbox"}\n',
        encoding="utf-8",
    )
    cfg = load_forge_config(data)
    assert cfg.default_connection_profile_id == DEFAULT_CONNECTION_PROFILE_ID
    assert len(cfg.connection_profiles) == 1
    prof = cfg.connection_profiles[0]
    assert prof.id == DEFAULT_CONNECTION_PROFILE_ID
    assert prof.provider == ForgeProvider.gitea
    assert prof.token == "sekret"
    assert prof.issue_import_policy == IssueImportPolicy.adhd_inbox
    assert "git.pike.homes" in (prof.name or "")


def test_public_dict_redacts_profile_tokens(tmp_path: Path) -> None:
    cfg = ForgeConfig(
        provider=ForgeProvider.github,
        token="ghp_abcdefghij",
        owner="o",
        repo="r",
        connection_profiles=[
            ForgeConnectionProfile(
                id="p1",
                name="GitHub",
                provider=ForgeProvider.github,
                token="ghp_abcdefghij",
            )
        ],
        default_connection_profile_id="p1",
    )
    pub = cfg.public_dict()
    assert pub["token"].startswith("***")
    assert pub["connection_profiles"][0]["token"].startswith("***")
    assert "ghp_" not in pub["connection_profiles"][0]["token"]


def test_github_com_identity_matches_api_github_profile() -> None:
    identity = normalize_external_identity(
        WorkSource.github, "github.com", "acme", "app", 1
    )
    prof = ForgeConnectionProfile(
        id="gh",
        name="GitHub",
        provider=ForgeProvider.github,
        token="tok",
        base_url="https://api.github.com",
        web_base_url="https://github.com",
    )
    assert profile_matches_identity_host(prof, identity) is True
    cfg = ForgeConfig(
        provider=ForgeProvider.github,
        token="tok",
        owner="acme",
        repo="app",
        base_url="https://api.github.com",
    )
    assert credentials_apply_to_pinned(cfg, identity) is True


def test_preserve_token_when_masked_on_save(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    original = ForgeConfig(
        provider=ForgeProvider.github,
        token="real-token-value",
        owner="o",
        repo="r",
        connection_profiles=[
            ForgeConnectionProfile(
                id="default",
                name="GitHub",
                provider=ForgeProvider.github,
                token="real-token-value",
                base_url="https://api.github.com",
                web_base_url="https://github.com",
            )
        ],
        default_connection_profile_id="default",
    )
    save_forge_config(data, original)
    # Simulate API merge: load current, apply payload with masked tokens
    current = load_forge_config(data)
    payload = current.public_dict()
    payload["connection_profiles"][0]["name"] = "GitHub renamed"
    from adhd_hub.forge.config import merge_forge_config_payload

    saved = merge_forge_config_payload(current, payload)
    assert saved.connection_profiles[0].token == "real-token-value"
    assert saved.connection_profiles[0].name == "GitHub renamed"


def test_selective_bind_matches_provider_host_only(tmp_path: Path) -> None:
    svc = _svc(tmp_path)
    data = svc.settings.data_dir
    data.mkdir(parents=True, exist_ok=True)
    save_forge_config(
        data,
        ForgeConfig(
            provider=ForgeProvider.gitea,
            token="gitea-tok",
            owner="alex",
            repo="projects",
            base_url="https://git.pike.homes/api/v1",
            web_base_url="https://git.pike.homes",
            board_enabled=True,
        ),
    )
    gitea_proj = svc.store.upsert_project(
        ProjectUpsert(
            title="Gitea App",
            forge_owner="alex",
            forge_repo="projects",
            repo_url="https://git.pike.homes/alex/ajp-n8n-workflow",
        )
    )
    local_proj = svc.store.upsert_project(ProjectUpsert(title="Local only"))
    gh_proj = svc.store.upsert_project(ProjectUpsert(title="GitHub app"))
    gh_thread = svc.store.upsert_thread(
        ThreadUpsert(summary="GH work", project_slug=gh_proj.slug)
    )
    svc.store.attach_external_identity(
        gh_thread.id,
        normalize_external_identity(
            WorkSource.github, "github.com", "uniskela", "adhd-hub", 9
        ),
        external_issue_state=ExternalIssueState.open,
    )
    result = svc.migrate_forge_connection_profiles()
    assert result["default_profile_id"] == DEFAULT_CONNECTION_PROFILE_ID
    gitea = svc.store.get_project(gitea_proj.slug)
    local = svc.store.get_project(local_proj.slug)
    gh = svc.store.get_project(gh_proj.slug)
    assert gitea is not None and gitea.forge_connection_profile_id == DEFAULT_CONNECTION_PROFILE_ID
    assert local is not None and local.forge_connection_profile_id is None
    assert gh is not None and gh.forge_connection_profile_id is None


def test_independent_profile_policies_drive_discovery(tmp_path: Path) -> None:
    cfg_g = ForgeConfig(
        provider=ForgeProvider.gitea,
        token="gt",
        owner="alex",
        repo="projects",
        board_enabled=True,
        issue_import_policy=IssueImportPolicy.manual,
    )
    assert discover_issue_payloads(cfg_g) == []

    cfg_gh = ForgeConfig(
        provider=ForgeProvider.github,
        token="gh",
        owner="acme",
        repo="app",
        board_enabled=True,
        issue_import_policy=IssueImportPolicy.labels,
        issue_import_labels=["b2a-smoke"],
    )
    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = [
            {
                "number": 1,
                "title": "Wanted",
                "state": "open",
                "labels": [{"name": "b2a-smoke"}],
                "updated_at": "t",
                "user": {"login": "x"},
            },
            {
                "number": 2,
                "title": "Skip",
                "state": "open",
                "labels": [{"name": "other"}],
                "updated_at": "t",
                "user": {"login": "x"},
            },
        ]
        resp.raise_for_status = MagicMock()
        resp.text = ""
        client.get.return_value = resp
        out = discover_issue_payloads(cfg_gh)
    assert isinstance(out, list)
    assert [x["snapshot"].identity.number for x in out] == [1]


def test_cross_host_credentials_never_apply() -> None:
    identity = normalize_external_identity(
        WorkSource.gitea, "git.pike.homes", "alex", "projects", 40
    )
    gh_cfg = ForgeConfig(
        provider=ForgeProvider.github,
        token="gh-secret",
        owner="uniskela",
        repo="adhd-hub",
        base_url="https://api.github.com",
        web_base_url="https://github.com",
    )
    assert credentials_apply_to_pinned(gh_cfg, identity) is False


def test_delete_in_use_profile_blocked(tmp_path: Path) -> None:
    svc = _svc(tmp_path)
    save_forge_config(
        svc.settings.data_dir,
        ForgeConfig(
            provider=ForgeProvider.github,
            token="t",
            owner="o",
            repo="r",
            connection_profiles=[
                ForgeConnectionProfile(
                    id="default",
                    name="GH",
                    provider=ForgeProvider.github,
                    token="t",
                ),
                ForgeConnectionProfile(
                    id="extra",
                    name="Extra",
                    provider=ForgeProvider.github,
                    token="t2",
                ),
            ],
            default_connection_profile_id="default",
        ),
    )
    svc.migrate_forge_connection_profiles()
    proj = svc.store.upsert_project(
        ProjectUpsert(title="Bound", forge_connection_profile_id="extra")
    )
    # Force the column if upsert ignores unknown — set via store helper
    svc.store.set_project_forge_connection_profile(proj.slug, "extra")
    with pytest.raises(ValueError, match="in_use"):
        svc.delete_forge_connection_profile("extra")


def test_url_suggest_does_not_overwrite_saved_profile(tmp_path: Path) -> None:
    svc = _svc(tmp_path)
    save_forge_config(
        svc.settings.data_dir,
        ForgeConfig(
            provider=ForgeProvider.github,
            token="t",
            owner="o",
            repo="r",
            connection_profiles=[
                ForgeConnectionProfile(
                    id="default",
                    name="GitHub — github.com",
                    provider=ForgeProvider.github,
                    token="t",
                    web_base_url="https://github.com",
                ),
                ForgeConnectionProfile(
                    id="gitea",
                    name="Home Gitea — git.pike.homes",
                    provider=ForgeProvider.gitea,
                    token="gt",
                    base_url="https://git.pike.homes/api/v1",
                    web_base_url="https://git.pike.homes",
                ),
            ],
            default_connection_profile_id="default",
        ),
    )
    suggested = svc.suggest_forge_connection_profile_id(
        repo_url="https://git.pike.homes/alex/x",
        current_profile_id="default",
    )
    assert suggested is None  # do not overwrite saved
    fresh = svc.suggest_forge_connection_profile_id(
        repo_url="https://git.pike.homes/alex/x",
        current_profile_id=None,
    )
    assert fresh == "gitea"


def test_profile_test_connection_success_and_error(tmp_path: Path) -> None:
    svc = _svc(tmp_path)
    save_forge_config(
        svc.settings.data_dir,
        ForgeConfig(
            provider=ForgeProvider.github,
            token="secret-token",
            owner="o",
            repo="r",
            connection_profiles=[
                ForgeConnectionProfile(
                    id="default",
                    name="GitHub",
                    provider=ForgeProvider.github,
                    token="secret-token",
                    base_url="https://api.github.com",
                    web_base_url="https://github.com",
                )
            ],
            default_connection_profile_id="default",
        ),
    )
    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"login": "octocat"}
        client.get.return_value = resp
        ok = svc.test_forge_connection_profile("default")
    assert ok["ok"] is True
    assert ok["login"] == "octocat"
    assert "token" not in ok
    assert "secret" not in str(ok)

    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        resp = MagicMock()
        resp.status_code = 401
        resp.text = "nope"
        client.get.return_value = resp
        bad = svc.test_forge_connection_profile("default")
    assert bad["ok"] is False
    assert "token" not in bad
    assert "secret" not in str(bad)
