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
    """Zero-activity days keep a 2px stub on a shared axis line, not an empty gap."""
    css = (UI / "app.css").read_text()
    chart = re.search(r"^\.chart \{[^}]*\}", css, re.MULTILINE)
    assert chart is not None
    assert "border-bottom: 1px solid var(--control-line)" in chart.group(0)
    zero = re.search(r"^\.chart \.bar\.is-zero \{[^}]*\}", css, re.MULTILINE)
    assert zero is not None
    assert "height: 2px" in zero.group(0)
    progress = (UI / "js" / "progress.js").read_text()
    assert 'class="bar ${kind} is-zero"' in progress


def test_activity_chart_has_a_table_view_and_validated_colours():
    """The 14-day chart is never colour-only: legend, per-day labels and a table."""
    html = (UI / "index.html").read_text()
    css = (UI / "app.css").read_text()
    progress = (UI / "js" / "progress.js").read_text()
    assert "Show as a table" in html
    assert 'id="chart-table-body"' in html
    assert 'class="chart-legend"' in html
    assert "chart-table-body" in progress
    assert "A table version follows." in progress
    # Amber and teal pair validated for CVD separation in both themes.
    assert "--chart-added: #a9781c;" in css and "--chart-finished: #008a78;" in css
    assert "--chart-added: #b8892c;" in css and "--chart-finished: #1e9c87;" in css


def test_progress_share_lives_in_the_header_and_rewards_off_links_to_settings():
    html = (UI / "index.html").read_text()
    header = html[html.index('class="view-heading progress-header"') :]
    header = header[: header.index("</header>")]
    assert 'id="btn-share-progress"' in header
    off = html[html.index('id="rewards-off"') :]
    off = off[: off.index("</p>")]
    assert 'data-screen="settings"' in off
    boot = (UI / "js" / "boot.js").read_text()
    assert '$("rewards-off").querySelector("[data-screen]")' in boot
    assert 'selectSettingsTab("preferences")' in boot


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


def test_thread_row_stays_highlighted_while_its_notes_are_open():
    """The row that opened the reader keeps a tint so the list keeps its place."""
    css = (UI / "app.css").read_text()
    assert '#threads .thread[aria-expanded="true"] { background: var(--accent-tint); }' in css


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


def test_needs_you_is_one_summary_line_over_its_rows():
    """Approvals, imports and due reminders share one collapsible "Needs you"
    panel; .setup-banner keeps its own single-row layout."""
    css = (UI / "app.css").read_text()
    html = (UI / "index.html").read_text()
    for group in ("reminder-banner", "pending-banner", "import-banner"):
        assert f'<div id="{group}" class="need-group" hidden></div>' in html
    assert 'id="btn-toggle-needs" aria-expanded="false"' in html
    assert 'id="triage-banner"' not in html  # Still relevant lives on Now only.
    need = re.search(r"^\.need \{[^}]*\}", css, re.MULTILINE)
    assert need is not None and "flex-wrap: wrap" in need.group(0)
    setup = re.search(r"^\.setup-banner \{[^}]*\}", css, re.MULTILINE)
    assert setup is not None
    assert "display: flex" in setup.group(0)

