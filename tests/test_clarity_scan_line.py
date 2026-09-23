"""Tests for Wave 6 heuristic thread scan-lines."""

from __future__ import annotations

from datetime import UTC, datetime

from adhd_hub.clarity import (
    SCAN_LINE_MAX,
    SCAN_LINE_SOURCE_HEURISTIC,
    attach_scan_line,
    build_scan_line,
    scrub_scan_text,
)
from adhd_hub.models import Thread, ThreadStatus


def _thread(**kwargs) -> Thread:
    now = datetime.now(UTC)
    base = {
        "id": "t1",
        "summary": "Ship Wave 6 scan lines",
        "status": ThreadStatus.open,
        "project_slug": "demo",
        "created_at": now,
        "updated_at": now,
    }
    base.update(kwargs)
    return Thread(**base)


def test_scrub_redacts_secrets_paths_and_private_urls():
    assert scrub_scan_text("token=abc123 keep going") == "[redacted] keep going"
    assert scrub_scan_text("edit /tmp/hub.sqlite3 next") == "edit [path] next"
    assert scrub_scan_text("open http://127.0.0.1:8787/ui/") == "open [private-url]"
    assert scrub_scan_text("see https://example.com/docs") == "see [url]"
    assert scrub_scan_text("   ") is None


def test_scrub_handles_headers_quoted_secrets_and_markdown_paths():
    for value in (
        "Retry Authorization: Bearer example-sensitive-value next",
        'Retry password="example-sensitive-value with spaces" next',
        "Retry Bearer example-sensitive-value next",
        "Open `/home/example-sensitive-value/config` next",
        "Open (C:/Users/example-sensitive-value/config) next",
    ):
        assert "example-sensitive-value" not in (scrub_scan_text(value) or "")


def test_build_scan_line_priority_focus_over_resume_and_goal():
    thread = _thread(
        focus="Wire scan_line into My Work",
        resume_step="Ignore me",
        goal="Also ignore",
        next_steps=["First next"],
    )
    line, source = build_scan_line(thread, progress_snippet="snippet last")
    assert line == "Wire scan_line into My Work"
    assert source == SCAN_LINE_SOURCE_HEURISTIC


def test_build_scan_line_falls_through_to_next_and_snippet():
    thread = _thread(next_steps=["Ship the filter"])
    line, source = build_scan_line(thread)
    assert line == "Ship the filter"
    assert source == SCAN_LINE_SOURCE_HEURISTIC

    empty = _thread()
    line2, source2 = build_scan_line(empty, progress_snippet="Latest note body")
    assert line2 == "Latest note body"
    assert source2 == SCAN_LINE_SOURCE_HEURISTIC

    none_line, none_source = build_scan_line(_thread())
    assert none_line is None
    assert none_source is None


def test_build_scan_line_truncates_and_skips_unsafe_only_candidates():
    long_focus = "x" * (SCAN_LINE_MAX + 40)
    line, _ = build_scan_line(_thread(focus=long_focus))
    assert line is not None
    assert len(line) <= SCAN_LINE_MAX
    assert line.endswith("…")

    line2, source2 = build_scan_line(
        _thread(focus="token=leak", resume_step="Safe resume cue")
    )
    assert line2 == "Safe resume cue"
    assert source2 == SCAN_LINE_SOURCE_HEURISTIC


def test_attach_scan_line_on_public_dict():
    thread = _thread(focus="Attach to public payload")
    data = {"progress_snippet": "ignored because focus wins"}
    out = attach_scan_line(data, thread)
    assert out is data
    assert data["scan_line"] == "Attach to public payload"
    assert data["scan_line_source"] == SCAN_LINE_SOURCE_HEURISTIC


def test_thread_public_dict_includes_scan_line(tmp_path):
    from adhd_hub.config import Settings
    from adhd_hub.models import ThreadUpsert
    from adhd_hub.service import HubService

    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="test-token",
    )
    service = HubService(settings)
    created = service.upsert_thread(
        ThreadUpsert(
            summary="Title only",
            project_slug="demo",
            focus="Show heuristic scan line",
            source_tool="pytest",
        )
    )
    pub = service.thread_public_dict(created)
    assert pub["summary"] == "Title only"
    assert pub["scan_line"] == "Show heuristic scan line"
    assert pub["scan_line_source"] == SCAN_LINE_SOURCE_HEURISTIC

    # Project-wide progress can describe a different outcome. It remains in
    # Notes, but must never be presented as this thread's own scan line.
    monkeypatch_thread = created.model_copy(
        update={"focus": None, "goal": None, "resume_step": None, "next_steps": []}
    )
    from unittest.mock import patch

    with (
        patch.object(service.store, "list_progress_notes", return_value=[]),
        patch.object(service.wiki, "read_progress", return_value="Deploy unrelated billing work"),
    ):
        pub = service.thread_public_dict(monkeypatch_thread)
    assert pub["scan_line"] is None
