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
    assert "if (keyboardReorderBusy) return;" in work
    assert '{ key: "project-reorder" }' in work
    # Search mode leaves DnD unwired, so grips must not stay in the Tab order.
    assert 'grip.removeAttribute("tabindex")' in work
    assert "focus the grip and press Up or Down" in html


def test_thread_row_stays_highlighted_while_actions_menu_open():
    """A flipped-up Actions panel may overlap its own card; the row keeps context."""
    css = (UI / "app.css").read_text()
    assert '.thread:has(.notes-trigger[aria-expanded="true"]),\n.thread:has(.thread-utility[open]) {' in css


def _panel(html: str, panel_id: str) -> str:
    start = html.index(f'<section id="{panel_id}"')
    return html[start : html.index('<section id="settings-', start + 1)]


def test_ai_scan_lines_has_its_own_settings_tab():
    """AI config sits beside OpenClaw/Forge instead of inside Preferences."""
    html = (UI / "index.html").read_text()
    now = (UI / "js" / "now.js").read_text()
    work = (UI / "js" / "work.js").read_text()
    tab = re.search(r'<button[^>]*id="tab-ai"[^>]*>AI scan-lines</button>', html)
    assert tab is not None
    assert 'aria-controls="settings-ai"' in tab.group(0)
    assert 'data-settings-tab="ai"' in tab.group(0)
    assert html.index('id="tab-openclaw"') < html.index('id="tab-ai"') < html.index('id="tab-forge"')
    ai = _panel(html, "settings-ai")
    prefs = _panel(html, "settings-preferences")
    assert 'aria-labelledby="tab-ai"' in ai
    assert "<h2>AI scan-lines</h2>" in ai
    for control in ("ai_enabled", "ai_base_url", "ai_model", "btn-save-ai", "btn-load-ai-models"):
        assert f'id="{control}"' in ai
        assert f'id="{control}"' not in prefs
    assert '[data-settings-tab="ai"]' in now
    assert "Settings → Preferences" not in work


def test_quiet_check_in_banner_stacks_its_heading_above_the_item_list():
    """Pending-request banners (Quiet check-in, Reminders, Pending requests) render
    a heading + hint above a list of rows — they must not flex all of it into one
    wrapping row, which crammed the heading, hint, and first row's title together."""
    css = (UI / "app.css").read_text()
    banner = re.search(r"^\.pending-banner \{[^}]*\}", css, re.MULTILINE)
    assert banner is not None
    assert "display: block" in banner.group(0)
    # .setup-banner (a single description + one action, e.g. "Create password")
    # keeps its own row layout and must not be coupled to .pending-banner again.
    setup = re.search(r"^\.setup-banner \{[^}]*\}", css, re.MULTILINE)
    assert setup is not None
    assert "display: flex" in setup.group(0)
    assert ".pending-banner, .setup-banner" not in css


def test_quiet_check_in_rows_get_a_calm_card_not_a_bare_divider():
    """Quiet check-in rows read as distinct cards, matching the in-card
    .thread-triage treatment, instead of a hairline divider between rows."""
    css = (UI / "app.css").read_text()
    rows = re.search(r"^\.triage-banner \.pending-item \{[^}]*\}", css, re.MULTILINE)
    assert rows is not None
    assert "border-radius" in rows.group(0)
    assert "background: color-mix" in rows.group(0)
    title = re.search(r"^\.triage-title \{[^}]*\}", css, re.MULTILINE)
    assert title is not None
    assert "font-weight: 600" in title.group(0)
