from __future__ import annotations

from unittest.mock import MagicMock, patch

from adhd_hub.config import Settings
from adhd_hub.forge.board_sync import BoardForgeSync
from adhd_hub.forge.config import ForgeConfig, ForgeProvider, _parse_inbox_authors
from adhd_hub.models import ThreadUpsert
from adhd_hub.service import HubService


def _cfg(**kwargs) -> ForgeConfig:
    base = {
        "provider": ForgeProvider.github,
        "token": "tok",
        "owner": "o",
        "repo": "r",
        "board_enabled": True,
        "board_inbox_enabled": True,
        "issue_labels": ["adhd-hub"],
        "board_inbox_synced_label": "adhd-hub-synced",
        "board_inbox_authors": ["trusted-user"],
    }
    base.update(kwargs)
    return ForgeConfig(**base)


def test_parse_inbox_authors_from_env_string() -> None:
    assert _parse_inbox_authors("Alice, bob ;Carol") == ["Alice", "bob", "Carol"]
    assert _parse_inbox_authors(["x", " ", "y"]) == ["x", "y"]
    assert _parse_inbox_authors(None) == []


def test_list_inbox_issues_filters_synced_prs_and_authors() -> None:
    board = BoardForgeSync(_cfg(), lambda _k: None, lambda _k, _v: None)
    payload = [
        {
            "number": 1,
            "title": "[ADHD] Do the thing",
            "body": "Now: start",
            "user": {"login": "trusted-user"},
            "labels": [{"name": "adhd-hub"}],
            "html_url": "https://github.com/o/r/issues/1",
        },
        {
            "number": 2,
            "title": "[ADHD] Already synced",
            "user": {"login": "trusted-user"},
            "labels": [{"name": "adhd-hub"}, {"name": "adhd-hub-synced"}],
        },
        {
            "number": 3,
            "title": "PR",
            "user": {"login": "trusted-user"},
            "pull_request": {},
            "labels": [{"name": "adhd-hub"}],
        },
        {
            "number": 4,
            "title": "[ADHD] Random stranger",
            "user": {"login": "random-person"},
            "labels": [{"name": "adhd-hub"}],
        },
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.return_value = mock_resp
        issues = board.list_inbox_issues()
    assert len(issues) == 1
    assert issues[0]["number"] == 1


def test_list_inbox_issues_empty_allowlist_imports_nothing() -> None:
    board = BoardForgeSync(
        _cfg(board_inbox_authors=[]),
        lambda _k: None,
        lambda _k, _v: None,
    )
    with patch("httpx.Client") as client_cls:
        issues = board.list_inbox_issues()
    assert issues == []
    client_cls.assert_not_called()


def test_import_forge_inbox_creates_thread_and_closes(tmp_path) -> None:
    service = HubService(
        Settings(
            data_dir=tmp_path / "data",
            auth_token="t",
            forge_provider="github",
            forge_token="tok",
            forge_owner="o",
            forge_repo="r",
            forge_board_enabled=True,
            forge_board_inbox_enabled=True,
            forge_board_inbox_authors="trusted-user",
        )
    )
    issue = {
        "number": 42,
        "title": "[ADHD] Cloud handoff",
        "body": "## Now\n- wire inbox\n\n## Return cue\n- When I return, I will test.",
        "user": {"login": "trusted-user"},
        "labels": [
            {"name": "adhd-hub"},
            {"name": "project:adhd-hub"},
            {"name": "source:codex"},
        ],
        "html_url": "https://github.com/o/r/issues/42",
    }

    def fake_list(limit=50):
        return [issue]

    def fake_mark(number, *, thread_id):
        return {"closed": True, "number": number, "thread_id": thread_id}

    with (
        patch.object(BoardForgeSync, "list_inbox_issues", side_effect=fake_list),
        patch.object(BoardForgeSync, "mark_issue_imported", side_effect=fake_mark),
    ):
        out = service.import_forge_inbox()

    assert out["count"] == 1
    item = out["imported"][0]
    assert item["number"] == 42
    assert item["thread_id"]
    assert service.store.get_meta(f"forge_issue:{item['thread_id']}") == "42"
    thread = service.store.get_thread(item["thread_id"])
    assert thread is not None
    assert thread.summary == "Cloud handoff"
    assert thread.project_slug == "adhd-hub"
    assert thread.source_tool == "codex"


def test_import_forge_inbox_skips_when_disabled(tmp_path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    out = service.import_forge_inbox()
    assert out["skipped"] is True


def test_import_forge_inbox_requires_authors(tmp_path) -> None:
    service = HubService(
        Settings(
            data_dir=tmp_path / "data",
            auth_token="t",
            forge_provider="github",
            forge_token="tok",
            forge_owner="o",
            forge_repo="r",
            forge_board_enabled=True,
            forge_board_inbox_enabled=True,
            forge_board_inbox_authors="",
        )
    )
    out = service.import_forge_inbox()
    assert out["skipped"] is True
    assert out["reason"] == "board_inbox_authors_required"


def test_import_skips_already_mapped(tmp_path) -> None:
    service = HubService(
        Settings(
            data_dir=tmp_path / "data",
            auth_token="t",
            forge_provider="github",
            forge_token="tok",
            forge_owner="o",
            forge_repo="r",
            forge_board_enabled=True,
            forge_board_inbox_enabled=True,
            forge_board_inbox_authors="trusted-user",
        )
    )
    thread = service.upsert_thread(ThreadUpsert(summary="Existing", source_tool="cursor"))
    service.store.set_meta(f"forge_issue:{thread.id}", "7")
    issue = {
        "number": 7,
        "title": "[ADHD] Existing",
        "body": "",
        "user": {"login": "trusted-user"},
        "labels": [{"name": "adhd-hub"}],
    }
    with patch.object(BoardForgeSync, "list_inbox_issues", return_value=[issue]):
        out = service.import_forge_inbox()
    assert out["count"] == 0
    assert out["skipped_issues"][0]["reason"] == "already_mapped"


def test_import_same_title_different_issues_do_not_collide(tmp_path) -> None:
    service = HubService(
        Settings(
            data_dir=tmp_path / "data",
            auth_token="t",
            forge_provider="github",
            forge_token="tok",
            forge_owner="o",
            forge_repo="r",
            forge_board_enabled=True,
            forge_board_inbox_enabled=True,
            forge_board_inbox_authors="trusted-user",
        )
    )
    issues = [
        {
            "number": 10,
            "title": "[ADHD] Same title",
            "body": "first",
            "user": {"login": "trusted-user"},
            "labels": [{"name": "adhd-hub"}, {"name": "project:adhd-hub"}],
        },
        {
            "number": 11,
            "title": "[ADHD] Same title",
            "body": "second",
            "user": {"login": "trusted-user"},
            "labels": [{"name": "adhd-hub"}, {"name": "project:adhd-hub"}],
        },
    ]

    def fake_mark(number, *, thread_id):
        return {"closed": True, "number": number, "thread_id": thread_id}

    with (
        patch.object(BoardForgeSync, "list_inbox_issues", return_value=issues),
        patch.object(BoardForgeSync, "mark_issue_imported", side_effect=fake_mark),
    ):
        out = service.import_forge_inbox()

    assert out["count"] == 2
    ids = {item["thread_id"] for item in out["imported"]}
    assert len(ids) == 2
    assert service.store.get_meta(f"forge_issue:{out['imported'][0]['thread_id']}") == "10"
    assert service.store.get_meta(f"forge_issue:{out['imported'][1]['thread_id']}") == "11"


def test_mark_issue_imported_never_deletes() -> None:
    board = BoardForgeSync(_cfg(), lambda _k: None, lambda _k, _v: None)
    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.json.return_value = {"body": "hello", "labels": [{"name": "adhd-hub"}]}
    patch_resp = MagicMock()
    patch_resp.status_code = 200
    patch_resp.raise_for_status = MagicMock()
    label_get = MagicMock()
    label_get.status_code = 200
    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.side_effect = [label_get, get_resp]
        client.patch.return_value = patch_resp
        out = board.mark_issue_imported(9, thread_id="abc")
    assert out["closed"] is True
    payload = client.patch.call_args.kwargs["json"]
    assert payload["state"] == "closed"
    assert "adhd-hub-synced" in payload["labels"]
    assert "DELETE" not in str(client.mock_calls)
