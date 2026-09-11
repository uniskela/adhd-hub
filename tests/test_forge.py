from __future__ import annotations

from pathlib import Path

from adhd_hub.forge.config import ForgeConfig, ForgeProvider, load_forge_config, save_forge_config
from adhd_hub.forge.scaffold import primary_repo_files, push_primary_scaffold


def test_forge_config_roundtrip(tmp_path: Path) -> None:
    cfg = ForgeConfig(
        provider=ForgeProvider.gitea,
        base_url="https://git.example/api/v1",
        token="secret-token",
        owner="alex",
        repo="homelab",
        wiki_enabled=True,
        board_enabled=True,
        primary_memory_repo=True,
        hub_public_url="http://100.64.0.1:8787",
        project_id="3",
    )
    save_forge_config(tmp_path, cfg)
    loaded = load_forge_config(tmp_path)
    assert loaded.provider == ForgeProvider.gitea
    assert loaded.wiki_enabled is True
    assert loaded.primary_memory_repo is True
    assert loaded.hub_public_url == "http://100.64.0.1:8787"
    assert loaded.token == "secret-token"
    assert loaded.public_dict()["token"].startswith("***")


def test_forge_config_keeps_token_when_masked(tmp_path: Path) -> None:
    save_forge_config(
        tmp_path,
        ForgeConfig(provider=ForgeProvider.github, token="real-secret-value", owner="o", repo="r"),
    )
    current = load_forge_config(tmp_path)
    data = current.model_dump()
    data["token"] = "***alue"
    data["wiki_enabled"] = True
    # emulate API merge
    if str(data["token"]).startswith("***"):
        data["token"] = current.token
    updated = ForgeConfig.model_validate(data)
    assert updated.token == "real-secret-value"
    assert updated.wiki_enabled is True


def test_primary_repo_files_include_readme() -> None:
    files = primary_repo_files()
    assert "README.md" in files
    assert "AGENTS.md" in files
    assert "ADHD Hub memory" in files["README.md"]
    assert "ADHD_HUB_PUBLIC_URL" in files["README.md"]


def test_primary_repo_readme_links_ui() -> None:
    files = primary_repo_files(hub_ui_url="http://100.64.0.1:8787")
    assert "[http://100.64.0.1:8787/ui](http://100.64.0.1:8787/ui)" in files["README.md"]
    assert "http://100.64.0.1:8787/ui" in files["AGENTS.md"]


def test_gitea_issue_web_url_from_api_base() -> None:
    cfg = ForgeConfig(
        provider=ForgeProvider.gitea,
        base_url="https://git.pike.homes/api/v1",
        web_base_url="https://github.com",  # wrong leftover — should be ignored
        owner="alex",
        repo="projects",
    )
    assert cfg.web_browse_root() == "https://git.pike.homes"
    assert cfg.issue_web_url(1) == "https://git.pike.homes/alex/projects/issues/1"


def test_push_primary_scaffold_skipped_when_disabled() -> None:
    cfg = ForgeConfig(provider=ForgeProvider.gitea, token="t", owner="a", repo="r")
    out = push_primary_scaffold(cfg)
    assert out["skipped"] is True


def test_issue_body_is_thread_scoped_not_project_log() -> None:
    from datetime import UTC, datetime

    from adhd_hub.forge.board_sync import STATUS_END, STATUS_START, BoardForgeSync
    from adhd_hub.models import Thread, ThreadStatus

    cfg = ForgeConfig(
        provider=ForgeProvider.gitea,
        base_url="https://git.example/api/v1",
        token="t",
        owner="a",
        repo="r",
        board_enabled=True,
        wiki_path="",
        wiki_branch="main",
    )
    sync = BoardForgeSync(
        cfg,
        lambda _k: None,
        lambda _k, _v: None,
        progress_reader=lambda _slug: (
            "## Active threads\n\n### Other thread\n\nGoal: Should not appear\n"
        ),
    )
    thread = Thread(
        id="abc",
        summary="Settings redesign",
        status=ThreadStatus.open,
        project_slug="adhd-hub",
        goal="Ship Settings page + dark UI",
        focus="Build form layout",
        next_steps=["Wire prefs API", "Add dark tokens", "Polish a11y", "extra ignored"],
        blocked_reason=None,
        resume_step="Open settings.js",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    body = sync._issue_body(thread)
    assert STATUS_START in body and STATUS_END in body
    assert "### Progress log" not in body
    assert "Should not appear" not in body
    assert "Ship Settings page + dark UI" in body
    assert "Build form layout" in body
    assert "Wire prefs API" in body
    assert "extra ignored" not in body
    assert "Blocked" not in body
    assert "Open settings.js" in body
    assert "projects/adhd-hub/PROGRESS.md" in body
    labels = sync._labels_for_thread(thread)
    assert "adhd-hub" in labels
    assert "project:adhd-hub" in labels


def test_two_threads_produce_distinct_issue_bodies() -> None:
    from datetime import UTC, datetime

    from adhd_hub.forge.board_sync import BoardForgeSync
    from adhd_hub.models import Thread, ThreadStatus

    cfg = ForgeConfig(
        provider=ForgeProvider.gitea,
        base_url="https://git.example/api/v1",
        token="t",
        owner="a",
        repo="r",
        board_enabled=True,
    )
    sync = BoardForgeSync(cfg, lambda _k: None, lambda _k, _v: None)
    now = datetime.now(UTC)
    a = Thread(
        id="a1",
        summary="Settings",
        status=ThreadStatus.open,
        project_slug="hub",
        goal="Ship Settings UI",
        focus="Form",
        created_at=now,
        updated_at=now,
    )
    b = Thread(
        id="b1",
        summary="OAuth",
        status=ThreadStatus.open,
        project_slug="hub",
        goal="Ship MCP OAuth",
        focus="Discovery endpoint",
        created_at=now,
        updated_at=now,
    )
    body_a = sync._issue_body(a)
    body_b = sync._issue_body(b)
    assert "Ship Settings UI" in body_a and "Ship Settings UI" not in body_b
    assert "Ship MCP OAuth" in body_b and "Ship MCP OAuth" not in body_a
    assert "Discovery endpoint" not in body_a
    assert "Form" not in body_b


def test_merge_preserves_user_authored_issue_body() -> None:
    from datetime import UTC, datetime

    from adhd_hub.forge.board_sync import STATUS_START, BoardForgeSync
    from adhd_hub.models import Thread, ThreadStatus

    cfg = ForgeConfig(
        provider=ForgeProvider.github,
        token="t",
        owner="o",
        repo="r",
        board_enabled=True,
    )
    sync = BoardForgeSync(cfg, lambda _k: None, lambda _k, _v: None)
    now = datetime.now(UTC)
    thread = Thread(
        id="t1",
        summary="OAuth",
        status=ThreadStatus.open,
        project_slug="hub",
        goal="Ship OAuth",
        focus="Token endpoint",
        created_at=now,
        updated_at=now,
    )
    user_body = "## My notes\n\nPlease keep this paragraph.\n"
    merged = sync.merge_issue_body(user_body, thread)
    assert "Please keep this paragraph." in merged
    assert STATUS_START in merged
    assert "Ship OAuth" in merged
    # Second merge is idempotent for user content + single status block
    again = sync.merge_issue_body(merged, thread)
    assert again.count(STATUS_START) == 1
    assert "Please keep this paragraph." in again


def test_blocked_omitted_when_empty_included_when_set() -> None:
    from datetime import UTC, datetime

    from adhd_hub.forge.board_sync import BoardForgeSync
    from adhd_hub.models import Thread, ThreadStatus

    cfg = ForgeConfig(provider=ForgeProvider.gitea, token="t", owner="a", repo="r")
    sync = BoardForgeSync(cfg, lambda _k: None, lambda _k, _v: None)
    now = datetime.now(UTC)
    open_t = Thread(
        id="x",
        summary="Work",
        status=ThreadStatus.open,
        project_slug="p",
        goal="Done when shipped",
        focus="Code",
        blocked_reason="",
        created_at=now,
        updated_at=now,
    )
    assert "**Blocked**" not in sync._issue_body(open_t)
    blocked = open_t.model_copy(update={"blocked_reason": "Waiting on review"})
    body = sync._issue_body(blocked)
    assert "**Blocked**" in body
    assert "Waiting on review" in body
    assert "None" not in body.split("**Blocked**", 1)[1].split("**Resume**", 1)[0]


def test_gitea_file_web_url_root_wiki() -> None:
    cfg = ForgeConfig(
        provider=ForgeProvider.gitea,
        base_url="https://git.pike.homes/api/v1",
        owner="alex",
        repo="projects",
        wiki_path="",
        wiki_branch="main",
    )
    assert (
        cfg.file_web_url("projects/adhd-hub/PROGRESS.md")
        == "https://git.pike.homes/alex/projects/src/branch/main/projects/adhd-hub/PROGRESS.md"
    )
