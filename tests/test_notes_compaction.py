"""Unit tests for notes feed compaction helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from adhd_hub.notes_compaction import (
    coalesce_notes_feed,
    default_open_thread_notes,
    is_boilerplate_freeform,
    is_boilerplate_progress_snippet,
    is_milestone_note,
    milestone_field_chips,
    scrub_progress_content,
    should_skip_duplicate_note,
    structural_core,
)


def test_scrub_ritual_content() -> None:
    assert scrub_progress_content("Thread upserted from codex: Task 3") is None
    assert scrub_progress_content("Checkpoint from cursor") is None
    assert scrub_progress_content("Decided to ship CSS first") == "Decided to ship CSS first"
    assert is_boilerplate_freeform("Thread upserted from codex: Task 1")


def test_milestone_detection_and_chips() -> None:
    line = "Goal → Ship Notes — Focus → Rewrite HTML — Thread upserted from codex: Task 2"
    assert is_milestone_note(line)
    assert milestone_field_chips(line) == ["Goal", "Focus"]
    assert structural_core(line) == "Goal → Ship Notes — Focus → Rewrite HTML"
    assert not is_milestone_note("## Human decision\n\nWe picked chips over prose.")


def test_coalesce_consecutive_milestones() -> None:
    notes = [
        {"content": "Focus → A", "created_at": "2026-09-22T12:00:00+00:00"},
        {"content": "Focus → B", "created_at": "2026-09-22T11:59:00+00:00"},
        {"content": "Focus → C", "created_at": "2026-09-22T11:58:00+00:00"},
        {"content": "Human note about a decision", "created_at": "2026-09-22T11:00:00+00:00"},
        {"content": "Goal → X", "created_at": "2026-09-22T10:00:00+00:00"},
    ]
    items = coalesce_notes_feed(notes)
    assert items[0]["kind"] == "group"
    assert items[0]["count"] == 3
    assert items[1]["kind"] == "single"
    assert items[1]["milestone"] is False
    assert items[2]["kind"] == "single"
    assert items[2]["milestone"] is True


def test_default_open_closed_heuristics() -> None:
    human = [{"content": "Ship decision recorded"}]
    assert default_open_thread_notes(human) is True

    few_mixed = [
        {"content": "Focus → A"},
        {"content": "Wrote the CSS handoff"},
    ]
    assert default_open_thread_notes(few_mixed) is True

    wall = [{"content": f"Focus → step {i}"} for i in range(10)]
    assert default_open_thread_notes(wall) is False

    mostly_ms = [{"content": f"Focus → {i}"} for i in range(5)]
    assert default_open_thread_notes(mostly_ms) is False


def test_should_skip_near_duplicate_within_window() -> None:
    now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    recent = [
        {
            "content": "Focus → Rewrite HTML — Thread upserted from codex: Task 1",
            "created_at": (now - timedelta(seconds=30)).isoformat(),
        }
    ]
    near = "Focus → Rewrite HTML — Thread upserted from codex: Task 2"
    assert should_skip_duplicate_note(near, recent, now=now) is True

    distinct = "Goal → Ship Notes UI — Focus → Rewrite HTML"
    assert should_skip_duplicate_note(distinct, recent, now=now) is False

    human = "Chose collapse-by-default for milestone walls"
    assert should_skip_duplicate_note(human, recent, now=now) is False


def test_boilerplate_progress_snippet() -> None:
    assert is_boilerplate_progress_snippet("Focus → Rewrite — Goal → Ship")
    assert is_boilerplate_progress_snippet("Thread upserted from codex: Task 9")
    assert not is_boilerplate_progress_snippet("Merged PR after green CI.")
