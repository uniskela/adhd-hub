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
