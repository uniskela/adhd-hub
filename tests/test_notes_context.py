"""Notes & context HTML: continuity card, siblings, wiki, forge activity."""

from __future__ import annotations

from unittest.mock import patch

import httpx

from adhd_hub.config import Settings
from adhd_hub.forge.board_sync import BoardForgeSync
from adhd_hub.forge.config import ForgeConfig, ForgeProvider
from adhd_hub.forge.thread_refresh import parse_issue_body
from adhd_hub.models import ThreadStatus, ThreadUpsert
from adhd_hub.service import HubService


def _service(tmp_path) -> HubService:
    return HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))


def test_parse_issue_body_accepts_bare_resume() -> None:
    body = """## Goal
Ship notes

## Focus
Write the card

## Next
- [ ] Add CSS

## Resume
Open service.py and continue
"""
    assert parse_issue_body(body) == {
        "goal": "Ship notes",
        "focus": "Write the card",
        "next_steps": ["Add CSS"],
        "resume_step": "Open service.py and continue",
    }


def test_notes_html_has_overview_continuity_notes_siblings_and_closed_wiki(tmp_path) -> None:
    service = _service(tmp_path)
    primary = service.store.upsert_thread(
        ThreadUpsert(
            summary="Primary outcome",
            project_slug="demo",
            goal="Ship Notes UI",
            focus="Rewrite HTML",
            next_steps=["CSS", "Tests"],
            blocked_reason="Waiting on review",
            resume_step="Open notes reader",
        )
    )
    service.store.upsert_thread(
        ThreadUpsert(
            summary="Sibling outcome",
            project_slug="demo",
            goal="Other goal",
            focus="Sibling focus",
            next_steps=["One"],
            resume_step="Resume sibling",
        )
    )
    service.store.add_progress_note("demo", "## Thread note\n\nBody", thread_id=primary.id)
    service._sync_project_progress("demo", title="Demo")

    html = service.thread_notes_context_html(primary)

    assert 'class="notes-overview"' in html
    assert "demo" in html
    assert "2 active" in html
    assert 'class="notes-continuity-card"' in html
    assert "Ship Notes UI" in html
    assert "Rewrite HTML" in html
    assert "Waiting on review" in html
    assert "Open notes reader" in html
    assert 'class="notes-section-details notes-thread-notes" open' in html
    assert "<h2>Thread note</h2>" in html
    assert "Sibling outcome" in html
    assert html.count("notes-sibling-thread") == 1
    assert 'notes-sibling-thread" open' not in html
    assert "<summary>Full PROGRESS.md</summary>" in html
    assert 'notes-wiki-details" open' not in html
    assert "Project wiki / full progress" not in html
    assert "<summary>Forge activity</summary>" in html
    assert "No linked forge issue" in html


def test_notes_forge_activity_fails_soft_and_opens_when_comments_exist(tmp_path) -> None:
    service = _service(tmp_path)
    thread = service.store.upsert_thread(
        ThreadUpsert(summary="Linked", project_slug="demo", goal="G", focus="F")
    )
    service.store.set_meta(f"forge_issue:{thread.id}", "42")

    with (
        patch.object(
            BoardForgeSync,
            "list_issue_comments",
            side_effect=httpx.HTTPError("down"),
        ),
        patch.object(BoardForgeSync, "list_issue_timeline", return_value=[]),
    ):
        html = service.thread_notes_context_html(thread)
    assert "Activity unavailable" in html
    assert 'class="notes-continuity-card"' in html
    assert "G" in html and "F" in html

    with (
        patch.object(
            BoardForgeSync,
            "list_issue_comments",
            return_value=[
                {
                    "remote_id": "9",
                    "kind": "comment",
                    "author": "ops",
                    "body": "**Looks good**",
                    "created_at": "2026-09-22T10:00:00Z",
                }
            ],
        ),
        patch.object(
            BoardForgeSync,
            "list_issue_timeline",
            return_value=[
                {
                    "remote_id": "t1",
                    "kind": "timeline",
                    "author": "bot",
                    "body": "labeled",
                    "event": "labeled",
                    "created_at": "2026-09-22T09:00:00Z",
                }
            ],
        ),
    ):
        html = service.thread_notes_context_html(thread)

    assert 'class="notes-section-details notes-forge-activity" open' in html
    assert "<strong>Looks good</strong>" in html
    assert "ops" in html
    assert "labeled" in html


def test_board_list_issue_comments_github_and_gitea() -> None:
    real_client = httpx.Client

    def _comments(provider: ForgeProvider, base_url: str, payload: list[dict]) -> list[dict]:
        cfg = ForgeConfig(
            provider=provider,
            base_url=base_url,
            token="tok",
            owner="acme",
            repo="hub",
        )
        board = BoardForgeSync(cfg, lambda _k: None, lambda _k, _v: None)
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)
        )

        class _CM:
            def __init__(self, *args, **kwargs):
                self._client = real_client(transport=transport)

            def __enter__(self):
                return self._client

            def __exit__(self, *args):
                self._client.close()
                return False

        with patch("adhd_hub.forge.board_sync.httpx.Client", _CM):
            return board.list_issue_comments(7, limit=10)

    gh = _comments(
        ForgeProvider.github,
        "https://api.github.com",
        [
            {
                "id": 1,
                "body": "Hello",
                "user": {"login": "alice"},
                "created_at": "2026-09-22T12:00:00Z",
                "html_url": "https://github.com/acme/hub/issues/7#issuecomment-1",
            }
        ],
    )
    assert gh[0]["remote_id"] == "1"
    assert gh[0]["author"] == "alice"
    assert gh[0]["body"] == "Hello"

    gt = _comments(
        ForgeProvider.gitea,
        "https://git.example/api/v1",
        [
            {
                "id": 2,
                "body": "Gitea note",
                "user": {"username": "bob"},
                "created_at": "2026-09-21T12:00:00Z",
            }
        ],
    )
    assert gt[0]["author"] == "bob"
    assert gt[0]["remote_id"] == "2"


def test_sibling_details_closed_by_default(tmp_path) -> None:
    service = _service(tmp_path)
    a = service.store.upsert_thread(
        ThreadUpsert(summary="A", project_slug="p", status=ThreadStatus.open, goal="ga")
    )
    service.store.upsert_thread(
        ThreadUpsert(summary="B", project_slug="p", status=ThreadStatus.open, goal="gb")
    )
    html = service.thread_notes_context_html(a)
    assert html.count("notes-sibling-thread") == 1
    assert 'notes-sibling-thread" open' not in html
    assert "gb" in html
