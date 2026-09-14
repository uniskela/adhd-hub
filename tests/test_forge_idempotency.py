from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adhd_hub.config import Settings
from adhd_hub.forge.config import ForgeConfig, ForgeProvider
from adhd_hub.forge.scaffold import push_primary_scaffold
from adhd_hub.forge.wiki_sync import WikiForgeSync
from adhd_hub.models import ProgressUpsert, ProjectUpsert
from adhd_hub.service import HubService
from adhd_hub.wiki import Wiki


def _config(provider: ForgeProvider = ForgeProvider.gitea) -> ForgeConfig:
    return ForgeConfig(
        provider=provider,
        token="token",
        owner="owner",
        repo="repo",
        wiki_enabled=True,
        primary_memory_repo=True,
        wiki_branch="main",
    )


def _contents_response(
    status_code: int, *, content: str | None = None, sha: str = "a" * 40
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    if status_code != 404:
        payload = {"type": "file", "sha": sha}
        if content is not None:
            payload["content"] = base64.b64encode(content.encode()).decode()
        response.json.return_value = payload
    return response


@pytest.mark.parametrize("provider", [ForgeProvider.github, ForgeProvider.gitea])
@pytest.mark.parametrize(
    ("remote", "expected_skipped", "expected_puts"),
    [("same\n", True, 0), ("old\n", False, 1), (None, False, 1)],
)
def test_individual_file_write_detects_unchanged_changed_and_missing(
    provider: ForgeProvider,
    remote: str | None,
    expected_skipped: bool,
    expected_puts: int,
) -> None:
    sync = WikiForgeSync(_config(provider))
    get_response = (
        _contents_response(404) if remote is None else _contents_response(200, content=remote)
    )
    put_response = MagicMock(status_code=200)
    put_response.json.return_value = {"commit": {"sha": "new"}}

    with patch("httpx.Client") as client_class:
        client = client_class.return_value.__enter__.return_value
        client.get.return_value = get_response
        client.put.return_value = put_response
        result = sync.put_file("INDEX.md", "same\n", "update")

    assert bool(result.get("skipped")) is expected_skipped
    if expected_skipped:
        assert result == {"skipped": True, "reason": "unchanged", "path": "INDEX.md"}
    assert client.put.call_count == expected_puts


def test_individual_file_uses_git_blob_sha_when_content_is_unavailable() -> None:
    sync = WikiForgeSync(_config())
    content = "same\n"
    sha = sync._git_blob_sha(content, 40)
    assert sha is not None

    with patch("httpx.Client") as client_class:
        client = client_class.return_value.__enter__.return_value
        client.get.return_value = _contents_response(200, sha=sha)
        result = sync.put_file("INDEX.md", content, "update")

    assert result["reason"] == "unchanged"
    client.put.assert_not_called()


def test_individual_file_refuses_indeterminate_remote_content() -> None:
    sync = WikiForgeSync(_config())

    with patch("httpx.Client") as client_class:
        client = client_class.return_value.__enter__.return_value
        client.get.return_value = _contents_response(200, sha="unsupported")
        with pytest.raises(RuntimeError, match="cannot determine remote content"):
            sync.put_file("INDEX.md", "local\n", "update")

    client.put.assert_not_called()


def test_individual_file_read_failure_does_not_write() -> None:
    sync = WikiForgeSync(_config())
    response = MagicMock(status_code=500)
    response.raise_for_status.side_effect = RuntimeError("forge unavailable")

    with patch("httpx.Client") as client_class:
        client = client_class.return_value.__enter__.return_value
        client.get.return_value = response
        with pytest.raises(RuntimeError, match="forge unavailable"):
            sync.put_file("INDEX.md", "local\n", "update")

    client.put.assert_not_called()


def test_scaffold_counts_only_writes_and_detects_url_changes() -> None:
    with patch("adhd_hub.forge.scaffold.WikiForgeSync") as sync_class:
        put = sync_class.return_value.put_file_at_repo_root
        put.return_value = {"skipped": True, "reason": "unchanged"}
        unchanged = push_primary_scaffold(_config(), hub_ui_url="https://hub.example")

        assert unchanged["uploaded"] == []
        assert unchanged["unchanged_files"] == ["README.md", "AGENTS.md", ".gitattributes"]
        assert unchanged["unchanged"] is True

        def url_change(rel: str, content: str, _message: str) -> dict:
            if rel in {"README.md", "AGENTS.md"}:
                assert "https://new.example/ui" in content
                return {"commit": {"sha": "new"}}
            return {"skipped": True, "reason": "unchanged"}

        put.side_effect = url_change
        changed = push_primary_scaffold(_config(), hub_ui_url="https://new.example")

    assert changed["uploaded"] == ["README.md", "AGENTS.md"]
    assert changed["unchanged_files"] == [".gitattributes"]
    assert changed["unchanged"] is False


def test_batch_change_detection_failure_uses_sequential_checks(tmp_path: Path) -> None:
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "INDEX.md").write_text("# Index\n", encoding="utf-8")
    sync = WikiForgeSync(_config())

    with (
        patch.object(sync, "_changed_files", side_effect=RuntimeError("read failed")),
        patch.object(
            sync,
            "put_file",
            return_value={"skipped": True, "reason": "unchanged", "path": "INDEX.md"},
        ) as put,
        patch("httpx.Client"),
    ):
        result = sync.push_wiki_tree(wiki_dir)

    put.assert_called_once()
    assert result["fallback_reason"] == "change_detection_failed"
    assert result["uploaded"] == []
    assert result["unchanged_files"] == ["INDEX.md"]
    assert result["unchanged"] is True


def test_batch_fallback_reports_individual_read_failure(tmp_path: Path) -> None:
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "INDEX.md").write_text("# Index\n", encoding="utf-8")
    sync = WikiForgeSync(_config())

    with (
        patch.object(sync, "_changed_files", side_effect=RuntimeError("batch read failed")),
        patch.object(sync, "put_file", side_effect=RuntimeError("file read failed")),
        patch("httpx.Client"),
    ):
        result = sync.push_wiki_tree(wiki_dir)

    assert result["uploaded"] == []
    assert result["unchanged_files"] == []
    assert result["errors"] == ["INDEX.md: file read failed"]
    assert result["unchanged"] is False


def test_failed_batch_commit_rechecks_files_before_counting_uploads(tmp_path: Path) -> None:
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    content = "# Index\n"
    (wiki_dir / "INDEX.md").write_text(content, encoding="utf-8")
    sync = WikiForgeSync(_config())

    with (
        patch.object(sync, "_changed_files", return_value=([("INDEX.md", content)], [])),
        patch.object(sync, "_commit_files_batch", side_effect=RuntimeError("commit failed")),
        patch.object(
            sync,
            "put_file",
            return_value={"skipped": True, "reason": "unchanged", "path": "INDEX.md"},
        ) as put,
        patch("httpx.Client"),
    ):
        result = sync.push_wiki_tree(wiki_dir)

    put.assert_called_once()
    assert result["fallback_reason"] == "batch_commit_failed"
    assert result["uploaded"] == []
    assert result["unchanged_files"] == ["INDEX.md"]
    assert result["unchanged"] is True


def test_move_does_not_count_unchanged_destination_as_uploaded() -> None:
    sync = WikiForgeSync(_config())
    with (
        patch.object(
            sync,
            "put_file",
            return_value={"skipped": True, "reason": "unchanged", "path": "new.md"},
        ),
        patch.object(sync, "delete_file", return_value={"deleted": True, "path": "old.md"}),
    ):
        result = sync.move_file("old.md", "new.md", "same\n")

    assert result["uploaded"] == []
    assert result["unchanged_files"] == ["new.md"]
    assert result["deleted"]["deleted"] is True
    assert result["unchanged"] is False


def _service_with_project(tmp_path: Path) -> HubService:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="token"))
    service.upsert_project(ProjectUpsert(title="Alpha", slug="alpha"))
    service.upsert_progress(
        ProgressUpsert(project_slug="alpha", content="## Next\n- finish", source_tool="test")
    )
    return service


def test_same_slug_rename_updates_title_without_remote_move(tmp_path: Path) -> None:
    service = _service_with_project(tmp_path)
    cfg = _config()
    push = {"uploaded": [], "unchanged_files": ["INDEX.md"], "errors": [], "unchanged": True}
    with (
        patch.object(service, "wiki_forge_config", return_value=cfg),
        patch("adhd_hub.service.WikiForgeSync") as sync_class,
    ):
        sync_class.return_value.push_wiki_tree.return_value = push
        result = service.rename_project("alpha", "alpha", title="Alpha renamed")

    sync_class.return_value.move_file.assert_not_called()
    sync_class.return_value.push_wiki_tree.assert_called_once()
    assert result["project"]["title"] == "Alpha renamed"
    assert result["forge"]["unchanged_files"] == ["INDEX.md"]
    assert result["forge"]["unchanged"] is True


def test_rename_aggregates_wiki_uploads_and_errors(tmp_path: Path) -> None:
    service = _service_with_project(tmp_path)
    cfg = _config()
    push = {
        "uploaded": ["INDEX.md"],
        "unchanged_files": ["projects/alpha-app/PROGRESS.md"],
        "errors": ["projects/other/PROGRESS.md: failed"],
        "unchanged": False,
    }
    move = {
        "uploaded": ["projects/alpha-app/PROGRESS.md"],
        "unchanged_files": [],
        "deleted": {"deleted": True},
    }
    with (
        patch.object(service, "wiki_forge_config", return_value=cfg),
        patch("adhd_hub.service.WikiForgeSync") as sync_class,
    ):
        sync_class.return_value.move_file.return_value = move
        sync_class.return_value.push_wiki_tree.return_value = push
        result = service.rename_project("alpha", "alpha-app")

    forge = result["forge"]
    assert forge["uploaded"] == ["projects/alpha-app/PROGRESS.md", "INDEX.md"]
    assert forge["deleted"] == ["projects/alpha/PROGRESS.md"]
    assert forge["unchanged_files"] == ["projects/alpha-app/PROGRESS.md"]
    assert forge["errors"] == ["projects/other/PROGRESS.md: failed"]
    assert forge["unchanged"] is False


def test_rebuild_index_preserves_bytes_when_only_timestamp_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wiki = Wiki(tmp_path / "wiki")
    monkeypatch.setattr(wiki, "_stamp", lambda: "first timestamp")
    path = wiki.rebuild_index([])
    original = path.read_bytes()

    monkeypatch.setattr(wiki, "_stamp", lambda: "second timestamp")
    wiki.rebuild_index([])

    assert path.read_bytes() == original
    assert b"first timestamp" in original
