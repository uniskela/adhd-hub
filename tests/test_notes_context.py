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
    assert "Updated <time" in html
    assert 'datetime="' in html
    assert 'class="notes-entry-meta"' in html
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
    assert 'datetime="2026-09-22T10:00:00Z"' in html
    assert 'datetime="2026-09-22T09:00:00Z"' in html
    assert "labeled" in html


def test_notes_overview_emits_time_datetime_not_bare_iso_slice(tmp_path) -> None:
    service = _service(tmp_path)
    thread = service.store.upsert_thread(
        ThreadUpsert(summary="Stamp check", project_slug="demo", goal="G")
    )
    html = service.thread_notes_context_html(thread)
    iso = thread.updated_at.isoformat()
    assert f'datetime="{iso}"' in html
    assert "Updated <time" in html
    # Must not leave the old truncated bare text without a datetime attribute.
    assert f"<span>Updated {iso[:19]}</span>" not in html
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


def test_empty_forge_activity_is_ttl_cached(tmp_path) -> None:
    service = _service(tmp_path)
    thread = service.store.upsert_thread(
        ThreadUpsert(summary="Linked", project_slug="demo", goal="G")
    )
    service.store.set_meta(f"forge_issue:{thread.id}", "42")
    calls = {"n": 0}

    def _comments(*_a, **_k):
        calls["n"] += 1
        return []

    with (
        patch.object(BoardForgeSync, "list_issue_comments", side_effect=_comments),
        patch.object(BoardForgeSync, "list_issue_timeline", return_value=[]),
    ):
        service.thread_notes_context_html(thread)
        service.thread_notes_context_html(thread)
    assert calls["n"] == 1
    assert service.store.forge_activity_fetched_at(thread.id)


def test_notes_overview_rejects_javascript_repo_url(tmp_path) -> None:
    service = _service(tmp_path)
    thread = service.store.upsert_thread(
        ThreadUpsert(summary="Safe", project_slug="demo", goal="G")
    )
    project = service.store.ensure_project_for_slug("demo", title="Demo")
    poisoned = project.model_copy(update={"repo_url": None})
    # Simulate a bad URL reaching HTML without going through Project validators.
    with patch.object(
        type(service.store),
        "get_project",
        return_value=poisoned.model_construct(
            **{**poisoned.model_dump(), "repo_url": "javascript:alert(1)"}
        ),
    ):
        html = service.thread_notes_context_html(thread)
    assert "javascript:" not in html
    assert "Repository" not in html


def test_board_list_issue_comments_uses_last_pages() -> None:
    real_client = httpx.Client
    cfg = ForgeConfig(
        provider=ForgeProvider.github,
        base_url="https://api.github.com",
        token="tok",
        owner="acme",
        repo="hub",
    )
    board = BoardForgeSync(cfg, lambda _k: None, lambda _k, _v: None)
    pages: dict[int, list[dict]] = {
        1: [
            {
                "id": 1,
                "body": "old",
                "user": {"login": "a"},
                "created_at": "2026-01-01T00:00:00Z",
            }
        ],
        2: [
            {
                "id": 2,
                "body": "new",
                "user": {"login": "b"},
                "created_at": "2026-09-22T00:00:00Z",
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page") or "1")
        headers = {}
        if page == 1:
            headers["Link"] = (
                '<https://api.github.com/repos/acme/hub/issues/7/comments?page=2>; rel="last"'
            )
        return httpx.Response(200, json=pages[page], headers=headers)

    transport = httpx.MockTransport(handler)

    class _CM:
        def __init__(self, *args, **kwargs):
            self._client = real_client(transport=transport)

        def __enter__(self):
            return self._client

        def __exit__(self, *args):
            self._client.close()
            return False

    with patch("adhd_hub.forge.board_sync.httpx.Client", _CM):
        rows = board.list_issue_comments(7, limit=1)
    assert rows[0]["remote_id"] == "2"
    assert rows[0]["body"] == "new"


def test_sibling_details_closed_by_default(tmp_path) -> None:
    service = _service(tmp_path)
    a = service.store.upsert_thread(
        ThreadUpsert(summary="A", project_slug="p", status=ThreadStatus.open, goal="ga")
    )
    service.store.upsert_thread(
        ThreadUpsert(summary="B legacy title only", project_slug="p", status=ThreadStatus.open)
    )
    html = service.thread_notes_context_html(a)
    assert html.count("notes-sibling-thread") == 1
    assert 'notes-sibling-thread" open' not in html
    assert 'data-choose="' in html
    assert "Choose this step" in html
    assert "B legacy title only" in html
    assert "Older forge imports" in html


def test_notes_coalesce_milestones_and_show_older(tmp_path) -> None:
    service = _service(tmp_path)
    thread = service.store.upsert_thread(
        ThreadUpsert(summary="Compact", project_slug="demo", goal="G", focus="F")
    )
    # Oldest first: a milestone run, then several human notes so the feed has
    # more than NOTES_VISIBLE_ITEMS after coalescing.
    for i in range(5):
        service.store.add_progress_note(
            "demo",
            f"Focus → step {i} — Thread upserted from codex: Task {i}",
            thread_id=thread.id,
        )
    for i in range(6):
        service.store.add_progress_note(
            "demo",
            f"## Human note {i}\n\nKeep continuity card primary {i}.",
            thread_id=thread.id,
        )
    html = service.thread_notes_context_html(thread)
    assert "notes-coalesce" in html
    assert "checkpoints · last:" in html
    assert "notes-change-chip" in html
    assert "Show older" in html
    assert "notes-entry-human" in html
    assert "Keep continuity card primary" in html
    # Continuity card remains outside / above Thread notes.
    cont = html.index('class="notes-continuity-card"')
    notes = html.index("notes-thread-notes")
    assert cont < notes


def test_coalesce_groups_present_when_thread_notes_default_open(tmp_path) -> None:
    """Open Thread notes must not bypass ritual coalescing (open only adds `open`)."""
    service = _service(tmp_path)
    thread = service.store.upsert_thread(
        ThreadUpsert(summary="Open coalesce", project_slug="demo", goal="G", focus="F")
    )
    # Ritual wall (Codex multi-em-dash) plus enough human notes to default-open.
    for i in range(4):
        service.store.add_progress_note(
            "demo",
            (
                f"Thread upserted from codex: Task {i} — Deterministic email — "
                "Prove outbound mail under retry"
            ),
            thread_id=thread.id,
        )
    for i in range(3):
        service.store.add_progress_note(
            "demo",
            f"## Human {i}\n\nKeep the coalesce group even when notes stay open.",
            thread_id=thread.id,
        )
    html = service.thread_notes_context_html(thread)
    assert 'class="notes-section-details notes-thread-notes" open' in html
    assert 'class="notes-coalesce"' in html
    assert html.count('class="notes-coalesce"') == 1
    assert "checkpoints · last:" in html
    # Coalesce groups themselves stay closed; only Thread notes accordion is open.
    assert 'class="notes-coalesce" open' not in html
    assert "notes-entry-human" in html
    assert "Keep the coalesce group" in html
    # Human notes stay distinct; ritual wall is one coalesce group, not 4 human entries.
    assert html.count('class="notes-entry notes-entry-human"') == 3


def test_chipless_milestone_uses_muted_summary_not_markdown_body(tmp_path) -> None:
    service = _service(tmp_path)
    thread = service.store.upsert_thread(
        ThreadUpsert(summary="Single ritual", project_slug="demo", goal="G")
    )
    service.store.add_progress_note(
        "demo",
        "Thread upserted from codex: Task 1 — Title only — Description bit",
        thread_id=thread.id,
    )
    html = service.thread_notes_context_html(thread)
    assert "notes-entry-milestone" in html
    assert "notes-milestone-summary" in html
    # Chip-less ritual must not dump a full markdown-body wall entry.
    entry_start = html.index("notes-entry-milestone")
    entry_chunk = html[entry_start : entry_start + 500]
    assert "markdown-body" not in entry_chunk


def test_notes_default_closed_for_milestone_wall(tmp_path) -> None:
    service = _service(tmp_path)
    thread = service.store.upsert_thread(
        ThreadUpsert(summary="Wall", project_slug="demo", goal="G", focus="F")
    )
    for i in range(10):
        service.store.add_progress_note(
            "demo", f"Focus → noise {i}", thread_id=thread.id
        )
    html = service.thread_notes_context_html(thread)
    assert 'class="notes-section-details notes-thread-notes"' in html
    assert 'class="notes-section-details notes-thread-notes" open' not in html
    assert 'class="notes-continuity-card"' in html


def test_upsert_progress_scrubs_ritual_and_dedups(tmp_path) -> None:
    from adhd_hub.models import ProgressUpsert

    service = _service(tmp_path)
    first = service.upsert_progress(
        ProgressUpsert(
            project_slug="demo",
            title="Notes compaction",
            goal="Ship compaction",
            focus="Write helpers",
            resume_step="Open notes_compaction.py",
            content="Thread upserted from codex: Task 1",
        )
    )
    tid = first["thread_id"]
    notes = service.store.list_progress_notes("demo", limit=20, thread_id=tid)
    assert notes
    assert all("Thread upserted from" not in (n["content"] or "") for n in notes)

    service.upsert_progress(
        ProgressUpsert(
            project_slug="demo",
            thread_id=tid,
            focus="Write helpers",
            content="Thread upserted from codex: Task 2",
        )
    )
    mid = service.store.list_progress_notes("demo", limit=20, thread_id=tid)
    assert len(mid) == len(notes)  # near-dup / scrubbed ritual did not grow wall

    service.upsert_progress(
        ProgressUpsert(
            project_slug="demo",
            thread_id=tid,
            focus="Add tests",
            resume_step="Run pytest tests/test_notes_compaction.py",
        )
    )
    after = service.store.list_progress_notes("demo", limit=20, thread_id=tid)
    assert len(after) == len(mid) + 1
    assert "Focus → Add tests" in after[0]["content"]
