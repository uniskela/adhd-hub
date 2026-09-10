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


def _issue(
    number: int,
    title: str,
    *,
    login: str = "trusted-user",
    labels: list[str] | None = None,
    **extra,
) -> dict:
    payload = {
        "number": number,
        "title": title,
        "user": {"login": login},
        "labels": [{"name": name} for name in (labels or [])],
    }
    payload.update(extra)
    return payload


def _ok_response(payload: list[dict]) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_parse_inbox_authors_from_env_string() -> None:
    assert _parse_inbox_authors("Alice, bob ;Carol") == ["Alice", "bob", "Carol"]
    assert _parse_inbox_authors(["x", " ", "y"]) == ["x", "y"]
    assert _parse_inbox_authors(None) == []


def test_title_matches_inbox_prefix_case_and_whitespace() -> None:
    assert BoardForgeSync.title_matches_inbox_prefix("[ADHD] Do the thing")
    assert BoardForgeSync.title_matches_inbox_prefix("[adhd] lowercase")
    assert BoardForgeSync.title_matches_inbox_prefix("[AdHd] mixed")
    assert BoardForgeSync.title_matches_inbox_prefix("[ADHD]no-space")
    assert BoardForgeSync.title_matches_inbox_prefix("[ADHD]  extra space")
    assert not BoardForgeSync.title_matches_inbox_prefix("Do the thing")
    assert not BoardForgeSync.title_matches_inbox_prefix("prefix [ADHD] later")
    assert not BoardForgeSync.title_matches_inbox_prefix("[ADHD-HUB] different tag")
    assert not BoardForgeSync.title_matches_inbox_prefix(None)


def test_list_inbox_issues_label_or_title_prefix() -> None:
    board = BoardForgeSync(_cfg(), lambda _k: None, lambda _k, _v: None)
    payload = [
        _issue(
            1,
            "[ADHD] Do the thing",
            labels=["adhd-hub"],
            html_url="https://github.com/o/r/issues/1",
        ),
        _issue(2, "[ADHD] Already synced", labels=["adhd-hub", "adhd-hub-synced"]),
        _issue(3, "PR", labels=["adhd-hub"], pull_request={}),
        _issue(4, "[ADHD] Random stranger", login="random-person", labels=["adhd-hub"]),
        _issue(5, "[ADHD] Title only without hub label", labels=[], pull_request=None),
        _issue(6, "Unlabeled and no prefix", labels=[]),
        _issue(7, "Label only without title prefix", labels=["adhd-hub"]),
        _issue(8, "[adhd] lowercase title only", labels=[]),
        _issue(9, "[ADHD] Wrong author title only", login="random-person", labels=[]),
    ]
    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.return_value = _ok_response(payload)
        issues = board.list_inbox_issues()
    params = client.get.call_args.kwargs["params"]
    assert "labels" not in params
    assert params["per_page"] == 100
    assert [issue["number"] for issue in issues] == [1, 5, 7, 8]


def test_list_inbox_issues_gitea_same_or_logic() -> None:
    board = BoardForgeSync(
        _cfg(provider=ForgeProvider.gitea, base_url="https://git.example/api/v1"),
        lambda _k: None,
        lambda _k, _v: None,
    )
    payload = [
        _issue(1, "[ADHD] Title only", labels=[], pull_request=None),
        _issue(2, "Noise", labels=[], pull_request=None),
        {
            "number": 3,
            "title": "Label only",
            "user": {"username": "trusted-user"},
            "labels": [{"name": "adhd-hub"}],
            "pull_request": None,
        },
        _issue(4, "[ADHD] Gitea PR", labels=["adhd-hub"], pull_request={"merged": False}),
    ]
    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.return_value = _ok_response(payload)
        issues = board.list_inbox_issues()
    params = client.get.call_args.kwargs["params"]
    assert "labels" not in params
    assert params["limit"] == 50
    assert params["type"] == "issues"
    assert [issue["number"] for issue in issues] == [1, 3]


def test_list_inbox_issues_paginates_past_unrelated_open_issues() -> None:
    board = BoardForgeSync(_cfg(), lambda _k: None, lambda _k, _v: None)
    page1 = [_issue(i, f"Unrelated {i}") for i in range(1, 101)]
    page2 = [_issue(101, "[ADHD] Buried title-only", labels=[])]
    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.side_effect = [_ok_response(page1), _ok_response(page2)]
        issues = board.list_inbox_issues()
    assert client.get.call_count == 2
    assert client.get.call_args_list[1].kwargs["params"]["page"] == 2
    assert [issue["number"] for issue in issues] == [101]


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


def test_import_forge_inbox_title_only_without_hub_label(tmp_path) -> None:
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
        "number": 88,
        "title": "[adhd] Cloud agent without labels",
        "body": "Now: import me",
        "user": {"login": "trusted-user"},
        "labels": [],
        "html_url": "https://github.com/o/r/issues/88",
    }

    def fake_mark(number, *, thread_id):
        return {"closed": True, "number": number, "thread_id": thread_id}

    with (
        patch.object(BoardForgeSync, "list_inbox_issues", return_value=[issue]),
        patch.object(BoardForgeSync, "mark_issue_imported", side_effect=fake_mark),
    ):
        out = service.import_forge_inbox()

    assert out["count"] == 1
    thread = service.store.get_thread(out["imported"][0]["thread_id"])
    assert thread is not None
    assert thread.summary == "Cloud agent without labels"
    assert service.store.get_meta(f"forge_issue:{thread.id}") == "88"


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
