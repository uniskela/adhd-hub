"""Markers for the September 2026 UI/UX audit fixes."""

from __future__ import annotations

import re
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "src" / "adhd_hub" / "ui"


def _mobile_notes_reader_block(css: str) -> str:
    start = css.index("@media (max-width: 1099px) {\n  body.notes-reader-open")
    block = css[start:]
    rule = block.index("  .notes-reader {")
    return block[rule : block.index("}", rule)]


def test_mobile_notes_reader_resets_desktop_max_height():
    """Full-screen reader must not stay capped at the docked calc(100dvh - 7rem)."""
    css = (UI / "app.css").read_text()
    assert "max-height: var(--notes-reader-height, calc(100dvh - 7rem));" in css
    rule = _mobile_notes_reader_block(css)
    assert "height: 100dvh !important;" in rule
    assert "max-height: 100dvh !important;" in rule


def test_aria_current_only_marks_navigation_items():
    """Now-screen shortcut cards share data-screen but are not navigation state."""
    screens = (UI / "js" / "screens.js").read_text()
    assert '".desktop-nav [data-screen], .mobile-nav [data-screen]"' in screens
    assert 'querySelectorAll("[data-screen]")' not in screens


def test_activity_chart_days_have_a_visible_baseline():
    """Zero-activity days render no bars, so each column keeps a baseline mark."""
    css = (UI / "app.css").read_text()
    col = re.search(r"^\.chart \.col \{[^}]*\}", css, re.MULTILINE)
    assert col is not None
    assert "border-bottom: 2px solid var(--line)" in col.group(0)


def test_project_grips_support_keyboard_reorder():
    """Sibling reorder must not be drag-only; grips take Up/Down and keep focus."""
    work = (UI / "js" / "work.js").read_text()
    html = (UI / "index.html").read_text()
    handle = work[work.index('<span class="proj-drag-handle"') :]
    handle = handle[: handle.index(">")]
    assert 'tabindex="0"' in handle
    assert 'role="button"' in handle
    assert 'aria-keyshortcuts="ArrowUp ArrowDown"' in handle
    assert "keyboardReorderTarget" in work
    assert 'event.key !== "ArrowUp" && event.key !== "ArrowDown"' in work
    assert "siblings[index + 2]?.slug || null" in work
    assert 'proj-drag-handle[data-drag-slug="${CSS.escape(slug)}"]' in work
    assert "focus the grip and press Up or Down" in html
