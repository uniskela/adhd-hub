from __future__ import annotations

from pathlib import Path

import pytest

from adhd_hub.config import Settings
from adhd_hub.models import ProgressUpsert, ReminderCreate, ReminderKind, ThreadUpsert
from adhd_hub.overlap import check_overlap, tokenize
from adhd_hub.service import HubService


@pytest.fixture
def service(tmp_path: Path) -> HubService:
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="test-token",
        stale_days=3,
        digest_limit=5,
        overlap_limit=5,
    )
    return HubService(settings)


def test_upsert_and_overlap(service: HubService) -> None:
    service.upsert_thread(
        ThreadUpsert(
            summary="Finish Proxmox LXC migration for openclaw",
            project_slug="openclaw-migration",
            workspace_path="/home/alex/portainer-stacks",
            source_tool="cursor",
        )
    )
    service.upsert_thread(
        ThreadUpsert(
            summary="Rewrite homepage widgets",
            project_slug="homepage",
            source_tool="codex",
        )
    )
    result = service.check_overlap("continue openclaw proxmox migration")
    assert result.hits
    assert "openclaw" in result.hits[0].thread.summary.lower()


def test_progress_creates_wiki(service: HubService) -> None:
    out = service.upsert_progress(
        ProgressUpsert(
            project_slug="homelab-dns",
            content="Moved CoreDNS to LXC 120; still need Tailscale ACL update.",
            title="CoreDNS migration",
            source_tool="cursor",
        )
    )
    assert out["thread_id"]
    path = Path(out["progress_path"])
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "CoreDNS" in text
    assert (service.settings.wiki_dir / "INDEX.md").is_file()


def test_mark_done(service: HubService) -> None:
    t = service.upsert_thread(ThreadUpsert(summary="Ship feature X", project_slug="feat-x"))
    done = service.mark_done(t.id, note="Shipped.")
    assert done and done.status.value == "done"
    assert service.list_open_threads() == []


def test_undo_mark_done_reopens(service: HubService) -> None:
    t = service.upsert_thread(ThreadUpsert(summary="Almost done", project_slug="demo"))
    service.mark_done(t.id, note="Marked done.")
    restored = service.undo_mark_done(t.id, note="Undone.")
    assert restored is not None
    assert restored.status.value == "open"
    assert restored.summary == "Almost done"
    with pytest.raises(ValueError, match="Only done"):
        service.undo_mark_done(t.id)


def test_undo_mark_done_fs_failure_leaves_done(service: HubService, monkeypatch) -> None:
    """B2b: failed projection write must not commit open (undo stays retryable)."""
    t = service.upsert_thread(ThreadUpsert(summary="Undo atomic", project_slug="undo-atom"))
    service.mark_done(t.id, note="Marked done.")
    slug = t.project_slug or "undo-atom"
    progress_before = service.wiki.read_progress(slug)
    index_path = service.settings.wiki_dir / "INDEX.md"
    index_before = index_path.read_text(encoding="utf-8") if index_path.is_file() else None

    def _boom(*_args, **_kwargs):
        raise OSError("simulated disk full")

    monkeypatch.setattr(service.wiki, "upsert_progress", _boom)
    with pytest.raises(OSError, match="simulated disk full"):
        service.undo_mark_done(t.id, note="Undone.")

    refreshed = service.store.get_thread(t.id)
    assert refreshed is not None
    assert refreshed.status.value == "done"
    assert service.wiki.read_progress(slug) == progress_before
    if index_before is None:
        assert not index_path.is_file()
    else:
        assert index_path.read_text(encoding="utf-8") == index_before

    monkeypatch.undo()
    # Guard still allows retry after a failed staging attempt.
    restored = service.undo_mark_done(t.id, note="Undone retry.")
    assert restored is not None
    assert restored.status.value == "open"


def test_undo_mark_done_index_failure_restores_progress(
    service: HubService, monkeypatch
) -> None:
    """If INDEX rewrite fails after PROGRESS write, roll both files back."""
    t = service.upsert_thread(
        ThreadUpsert(summary="Index fail undo", project_slug="undo-idx")
    )
    service.mark_done(t.id, note="Marked done.")
    slug = t.project_slug or "undo-idx"
    progress_before = service.wiki.read_progress(slug)
    index_path = service.settings.wiki_dir / "INDEX.md"
    index_before = index_path.read_text(encoding="utf-8") if index_path.is_file() else None

    def _boom(*_args, **_kwargs):
        raise OSError("index write failed")

    monkeypatch.setattr(service.wiki, "rebuild_index", _boom)
    with pytest.raises(OSError, match="index write failed"):
        service.undo_mark_done(t.id, note="Undone.")

    refreshed = service.store.get_thread(t.id)
    assert refreshed is not None
    assert refreshed.status.value == "done"
    assert service.wiki.read_progress(slug) == progress_before
    if index_before is None:
        assert not index_path.is_file()
    else:
        assert index_path.read_text(encoding="utf-8") == index_before


def test_session_digest_and_reminder(service: HubService) -> None:
    service.upsert_thread(ThreadUpsert(summary="Half-done Valkey upgrade", project_slug="valkey"))
    service.set_reminder(ReminderCreate(message="Stretch", kind=ReminderKind.session))
    digest = service.session_digest(query="valkey upgrade")
    assert digest.open_count == 1
    assert digest.items
    assert any(r.message == "Stretch" for r in digest.due_reminders)


def test_tokenize_filters_stopwords() -> None:
    tokens = tokenize("the migration for openclaw and the proxmox host")
    assert "migration" in tokens
    assert "openclaw" in tokens
    assert "the" not in tokens


def test_check_overlap_empty() -> None:
    result = check_overlap("anything", [])
    assert result.hits == []
