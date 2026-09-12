from __future__ import annotations

from pathlib import Path

import pytest

from adhd_hub.config import Settings
from adhd_hub.forge.config import ForgeConfig, ForgeProvider, save_forge_config
from adhd_hub.models import ProjectUpsert, ThreadStatus, ThreadUpsert
from adhd_hub.service import HubService
from adhd_hub.store import Store
from adhd_hub.work_identity import (
    WORK_IDENTITY_MIGRATED_META,
    DuplicateExternalIdentityError,
    ExternalIdentity,
    WorkAuthority,
    WorkSource,
    authority_for,
    external_identity_key,
    normalize_external_identity,
    normalize_host,
    resolve_work_source,
)


def _service(tmp_path: Path) -> HubService:
    return HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))


def test_normalize_github_host_and_casing() -> None:
    identity = normalize_external_identity(
        WorkSource.github,
        "https://api.github.com",
        "Owner",
        "Repo",
        12,
    )
    assert identity.host == "github.com"
    assert identity.owner == "owner"
    assert identity.repo == "repo"
    assert external_identity_key(identity) == "github:github.com/owner/repo#12"
    assert normalize_host(WorkSource.github, "https://github.com") == "github.com"


def test_gitea_hosts_do_not_collide() -> None:
    a = normalize_external_identity(WorkSource.gitea, "https://git.a.example", "o", "r", 7)
    b = normalize_external_identity(WorkSource.gitea, "https://git.b.example", "o", "r", 7)
    assert a.host == "git.a.example"
    assert b.host == "git.b.example"
    assert external_identity_key(a) != external_identity_key(b)


def test_local_work_defaults(tmp_path: Path) -> None:
    service = _service(tmp_path)
    proj = service.store.upsert_project(ProjectUpsert(title="Homelab"))
    assert proj.default_work_source == WorkSource.local
    thread = service.store.upsert_thread(
        ThreadUpsert(summary="Harden VPS", project_slug=proj.slug)
    )
    assert thread.work_source is None
    assert resolve_work_source(proj, thread) == WorkSource.local
    assert authority_for(WorkSource.local) == WorkAuthority.hub
    pub = service.thread_public_dict(thread)
    assert pub["work_source"] == "local"
    assert pub["authority"] == "hub"
    assert pub.get("external_issue_number") is None
    assert thread.external_issue_state is None


def test_project_default_and_thread_override(tmp_path: Path) -> None:
    service = _service(tmp_path)
    proj = service.store.upsert_project(
        ProjectUpsert(title="ADHD Hub", default_work_source=WorkSource.github)
    )
    local = service.store.upsert_thread(
        ThreadUpsert(
            summary="Private exploration",
            project_slug=proj.slug,
            work_source=WorkSource.local,
        )
    )
    inherited = service.store.upsert_thread(
        ThreadUpsert(summary="Feature work", project_slug=proj.slug)
    )
    assert resolve_work_source(proj, local) == WorkSource.local
    assert resolve_work_source(proj, inherited) == WorkSource.github


def test_attach_pins_source_against_project_default_change(tmp_path: Path) -> None:
    service = _service(tmp_path)
    proj = service.store.upsert_project(
        ProjectUpsert(title="App", default_work_source=WorkSource.local)
    )
    thread = service.store.upsert_thread(
        ThreadUpsert(summary="Fix bug", project_slug=proj.slug)
    )
    identity = normalize_external_identity(
        WorkSource.github, "github.com", "acme", "app", 42
    )
    linked = service.store.attach_external_identity(thread.id, identity)
    assert linked.work_source == WorkSource.github
    assert linked.external_host == "github.com"
    assert linked.external_issue_state is None
    service.store.upsert_project(
        ProjectUpsert(
            slug=proj.slug,
            title=proj.title,
            default_work_source=WorkSource.gitea,
        )
    )
    proj2 = service.store.get_project(proj.slug)
    refreshed = service.store.get_thread(thread.id)
    assert refreshed is not None and proj2 is not None
    assert resolve_work_source(proj2, refreshed) == WorkSource.github
    assert service.store.get_meta(f"forge_issue:{thread.id}") == "42"


def test_duplicate_external_identity_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    a = service.store.upsert_thread(ThreadUpsert(summary="One"))
    b = service.store.upsert_thread(ThreadUpsert(summary="Two"))
    identity = normalize_external_identity(
        WorkSource.gitea, "https://git.example.com", "org", "repo", 9
    )
    service.store.attach_external_identity(a.id, identity)
    with pytest.raises(DuplicateExternalIdentityError):
        service.store.attach_external_identity(b.id, identity)
    found = service.store.get_thread_by_external_identity(
        WorkSource.gitea, "git.example.com", "ORG", "REPO", 9
    )
    assert found is not None
    assert found.id == a.id


def test_github_case_folding_unique(tmp_path: Path) -> None:
    service = _service(tmp_path)
    a = service.store.upsert_thread(ThreadUpsert(summary="A"))
    b = service.store.upsert_thread(ThreadUpsert(summary="B"))
    service.store.attach_external_identity(
        a.id,
        ExternalIdentity(WorkSource.github, "github.com", "owner", "repo", 1),
    )
    with pytest.raises(DuplicateExternalIdentityError):
        service.store.attach_external_identity(
            b.id,
            ExternalIdentity(WorkSource.github, "github.com", "Owner", "Repo", 1),
        )


def test_two_gitea_instances_same_number(tmp_path: Path) -> None:
    service = _service(tmp_path)
    a = service.store.upsert_thread(ThreadUpsert(summary="A"))
    b = service.store.upsert_thread(ThreadUpsert(summary="B"))
    service.store.attach_external_identity(
        a.id,
        normalize_external_identity(WorkSource.gitea, "git.one.example", "o", "r", 3),
    )
    service.store.attach_external_identity(
        b.id,
        normalize_external_identity(WorkSource.gitea, "git.two.example", "o", "r", 3),
    )
    assert service.store.get_thread_by_external_identity(
        WorkSource.gitea, "git.one.example", "o", "r", 3
    ).id == a.id
    assert service.store.get_thread_by_external_identity(
        WorkSource.gitea, "git.two.example", "o", "r", 3
    ).id == b.id


def test_migration_promotes_confident_forge_mapping(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    save_forge_config(
        data,
        ForgeConfig(
            provider=ForgeProvider.github,
            token="tok",
            owner="acme",
            repo="hub",
            board_enabled=True,
        ),
    )
    settings = Settings(data_dir=data, auth_token="t")
    store = Store(settings.db_path)
    thread = store.upsert_thread(ThreadUpsert(summary="Mapped work", status=ThreadStatus.open))
    store.set_meta(f"forge_issue:{thread.id}", "55")
    assert store.get_meta(WORK_IDENTITY_MIGRATED_META) is None

    def resolve(_slug: str | None) -> dict[str, str] | None:
        return {
            "provider": "github",
            "host": "github.com",
            "owner": "acme",
            "repo": "hub",
        }

    result = store.migrate_work_identity(resolve)
    assert thread.id in result["promoted"]
    assert result["unresolved_count"] == 0
    migrated = store.get_thread(thread.id)
    assert migrated is not None
    assert migrated.work_source == WorkSource.github
    assert migrated.external_issue_number == 55
    assert migrated.external_issue_state is None
    assert store.get_meta(f"forge_issue:{thread.id}") == "55"
    assert store.get_meta(WORK_IDENTITY_MIGRATED_META) == "1"
    # Hub done must not become external closed during migration path
    store.mark_status(thread.id, ThreadStatus.done)
    again = store.get_thread(thread.id)
    assert again is not None
    assert again.external_issue_state is None


def test_migration_fail_safe_unresolved(tmp_path: Path) -> None:
    store = Store(tmp_path / "hub.db")
    thread = store.upsert_thread(ThreadUpsert(summary="Legacy map"))
    store.set_meta(f"forge_issue:{thread.id}", "8")

    result = store.migrate_work_identity(lambda _slug: None)
    assert result["unresolved_count"] == 1
    assert result["unresolved"][0]["thread_id"] == thread.id
    assert store.get_meta(f"forge_issue:{thread.id}") == "8"
    unchanged = store.get_thread(thread.id)
    assert unchanged is not None
    assert unchanged.external_issue_number is None
    assert store.get_meta(WORK_IDENTITY_MIGRATED_META) == "1"


def test_migration_no_forge_config_via_service(tmp_path: Path) -> None:
    service = _service(tmp_path)
    thread = service.store.upsert_thread(ThreadUpsert(summary="Only meta"))
    # Clear migrated flag and re-seed mapping to exercise service resolver
    service.store.set_meta(WORK_IDENTITY_MIGRATED_META, "0")
    # meta value "0" is not "1", so migrate runs again
    service.store.set_meta(f"forge_issue:{thread.id}", "99")
    result = service.store.migrate_work_identity(service._confident_forge_target)
    assert result["unresolved_count"] == 1
    assert service.store.get_meta(f"forge_issue:{thread.id}") == "99"


def test_service_init_migrates_when_forge_configured(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    save_forge_config(
        data,
        ForgeConfig(
            provider=ForgeProvider.gitea,
            base_url="https://git.example.com/api/v1",
            web_base_url="https://git.example.com",
            token="tok",
            owner="org",
            repo="mem",
            board_enabled=True,
        ),
    )
    settings = Settings(data_dir=data, auth_token="t")
    store = Store(settings.db_path)
    thread = store.upsert_thread(ThreadUpsert(summary="From inbox"))
    store.set_meta(f"forge_issue:{thread.id}", "3")
    # New HubService runs migration
    service = HubService(settings)
    migrated = service.store.get_thread(thread.id)
    assert migrated is not None
    assert migrated.external_provider == WorkSource.gitea
    assert migrated.external_host == "git.example.com"
    assert migrated.external_issue_number == 3
    pub = service.thread_public_dict(migrated)
    assert pub["authority"] == "external"
    assert pub["forge_issue_number"] == 3


def test_partial_project_override_is_unresolved(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    save_forge_config(
        data,
        ForgeConfig(
            provider=ForgeProvider.github,
            token="tok",
            owner="global-owner",
            repo="global-repo",
        ),
    )
    service = HubService(Settings(data_dir=data, auth_token="t"))
    service.store.upsert_project(
        ProjectUpsert(title="Partial", forge_owner="only-owner")
    )
    assert service._confident_forge_target("partial") is None


def test_refuse_remap_different_identity(tmp_path: Path) -> None:
    service = _service(tmp_path)
    thread = service.store.upsert_thread(ThreadUpsert(summary="Pinned"))
    service.store.attach_external_identity(
        thread.id,
        normalize_external_identity(WorkSource.github, None, "acme", "app", 1),
    )
    with pytest.raises(DuplicateExternalIdentityError):
        service.store.attach_external_identity(
            thread.id,
            normalize_external_identity(WorkSource.github, None, "acme", "app", 2),
        )
    # upsert cannot unpin linked work_source
    service.store.upsert_thread(
        ThreadUpsert(
            id=thread.id,
            summary="Pinned",
            work_source=WorkSource.local,
        )
    )
    refreshed = service.store.get_thread(thread.id)
    assert refreshed is not None
    assert refreshed.work_source == WorkSource.github


def test_serializers_include_identity(tmp_path: Path) -> None:
    service = _service(tmp_path)
    thread = service.store.upsert_thread(ThreadUpsert(summary="Linked"))
    service.store.attach_external_identity(
        thread.id,
        normalize_external_identity(WorkSource.github, None, "acme", "app", 11),
    )
    thread = service.store.get_thread(thread.id)
    assert thread is not None
    pub = service.thread_public_dict(thread)
    compact = service._enrich_compact_thread(thread)
    assert pub["work_source"] == "github"
    assert pub["authority"] == "external"
    assert pub["external_host"] == "github.com"
    assert compact["external_issue_number"] == 11
    assert compact["authority"] == "external"
