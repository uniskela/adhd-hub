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
