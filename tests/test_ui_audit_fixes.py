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
    # Small non-zero days stay visible next to a busy day.
    bar = re.search(r"^\.chart \.bar \{[^}]*\}", css, re.MULTILINE)
    assert bar is not None and "min-height: 4px" in bar.group(0)
    # An all-zero fortnight shows the empty line instead of 14 stubs.
    assert "if (!series.length || !active)" in progress


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


def test_ai_helpers_has_its_own_settings_tab():
    """AI config sits under Connections as "AI helpers", not inside Appearance."""
    html = (UI / "index.html").read_text()
    now = (UI / "js" / "now.js").read_text()
    work = (UI / "js" / "work.js").read_text()
    tab = re.search(r'<button[^>]*id="tab-ai"[^>]*>AI helpers</button>', html)
    assert tab is not None
    assert 'aria-controls="settings-ai"' in tab.group(0)
    assert 'data-settings-tab="ai"' in tab.group(0)
    assert html.index('id="tab-openclaw"') < html.index('id="tab-forge"') < html.index('id="tab-ai"')
    ai = _panel(html, "settings-ai")
    prefs = _panel(html, "settings-preferences")
    assert 'aria-labelledby="tab-ai"' in ai
    assert "<h2>AI helpers</h2>" in ai
    for control in ("ai_enabled", "ai_base_url", "ai_model", "btn-save-ai", "btn-load-ai-models"):
        assert f'id="{control}"' in ai
        assert f'id="{control}"' not in prefs
    # Every AI switch is off until turned on, and lists still lead with where you left off.
    for switch in ("ai_enabled", "ai_auto_review_scan", "ai_auto_summarise_notes"):
        assert re.search(rf'<input type="checkbox" role="switch" id="{switch}"', ai)
        assert f'id="{switch}" checked' not in ai
    assert "where you left off" in ai
    assert '[data-settings-tab="ai"]' in now
    assert "Settings → Preferences" not in work
    assert "Settings → AI scan-lines" not in work


SETTINGS_SECTIONS = [
    ("You", "preferences", "Appearance"),
    ("You", "account", "Account"),
    ("Connections", "connections", "Coding agents"),
    ("Connections", "mcp", "Remote access"),
    ("Connections", "openclaw", "Phone alerts"),
    ("Connections", "forge", "Issue sync"),
    ("Connections", "ai", "AI helpers"),
    ("Data", "data", "Your data"),
]


def test_settings_sections_use_plain_names_grouped_you_connections_data():
    html = (UI / "index.html").read_text()
    nav = html[html.index('<nav class="settings-nav"') : html.index("</nav>", html.index('<nav class="settings-nav"'))]
    positions = []
    for group, key, name in SETTINGS_SECTIONS:
        tab = re.search(rf'<button[^>]*data-settings-tab="{key}"[^>]*>([^<]+)</button>', nav)
        assert tab is not None and tab.group(1) == name, key
        group_at = nav.index(f'<p class="settings-nav-group" aria-hidden="true">{group}</p>')
        assert group_at < tab.start()
        positions.append(tab.start())
        panel = _panel(html, f"settings-{key}") if key != "data" else html[html.index('<section id="settings-data"') :]
        assert f"<h2>{name}</h2>" in panel
    assert positions == sorted(positions)


def test_settings_rows_switches_and_advanced():
    """Label-left rows, real checkbox switches, rare fields folded under Advanced."""
    html = (UI / "index.html").read_text()
    css = (UI / "app.css").read_text()
    for switch in ("rewards-enabled", "oc_enabled", "wiki_enabled", "board_enabled", "board_inbox_enabled", "primary_memory_repo"):
        assert re.search(rf'<span class="switch"><input type="checkbox" role="switch" id="{switch}"', html), switch
        assert f'<label class="setting-label" for="{switch}">' in html
    assert ".switch > input:focus-visible + .switch-track { outline: 3px solid var(--accent);" in css
    advanced = {
        "settings-openclaw": ("oc_webhook_url", "oc_agent_url", "oc_token", "oc_cron", "oc_cooldown_days", "oc_digest_limit", "oc_clear_token"),
        "settings-forge": ("default_connection_profile_id", "board_inbox_authors", "wiki_path", "wiki_branch", "hub_public_url", "project_id"),
        "settings-ai": ("ai_base_url", "ai_timeout", "ai_clear_key"),
    }
    for panel_id, ids in advanced.items():
        panel = _panel(html, panel_id)
        details = panel[panel.index("<summary>Advanced</summary>") :]
        details = details[: details.index("</details>")]
        for control in ids:
            assert f'id="{control}"' in details, (panel_id, control)
    # Swatches and the custom picker meet the 44 px target.
    assert ".swatch { width: 44px; height: 44px;" in css
    assert "#accent-colour { width: 44px; height: 44px;" in css


def test_appearance_saves_on_its_own_and_secret_sections_keep_save():
    html = (UI / "index.html").read_text()
    boot = (UI / "js" / "boot.js").read_text()
    settings = (UI / "js" / "settings.js").read_text()
    assert 'id="btn-save-settings"' not in html
    assert '$("timezone").addEventListener("change", () => saveSettings());' in boot
    assert 'setMsg("Time zone saved.")' in settings
    for button in ("btn-save-openclaw", "btn-save-forge", "btn-save-ai", "btn-save-connect-agents"):
        assert f'id="{button}"' in html


def test_issue_sync_connections_fold_and_keep_open_cards():
    settings = (UI / "js" / "settings.js").read_text()
    assert '<details class="forge-profile-card"' in settings
    assert '${p._unsaved ? " open" : ""}' in settings
    assert 'querySelectorAll(".forge-profile-card[open]")' in settings
    assert "Save forge" not in settings


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



def test_sign_in_is_one_calm_column_with_help_below_the_card():
    html = (UI / "index.html").read_text()
    gate = html[html.index('<div id="login-gate"') : html.index('<div id="app-shell"')]
    assert 'class="login-column"' in gate
    assert '<h1 id="login-title">Welcome back</h1>' in gate
    assert "A fresh start" not in gate and "login-promise" not in gate
    # Help sits under the card, not inside the form.
    assert gate.index("</form>") < gate.index('class="login-help"')
    assert "Sessions last 12 hours on this browser." in gate
    auth = (UI / "js" / "auth.js").read_text()
    assert '"Use access token instead" : "Use password instead"' in auth


def test_every_dialog_has_a_title_row_with_a_close_button():
    html = (UI / "index.html").read_text()
    dialogs = re.findall(r'<dialog id="([\w-]+)".*?</dialog>', html, re.DOTALL)
    assert len(dialogs) == 9
    for block in re.findall(r"<dialog .*?</dialog>", html, re.DOTALL):
        assert 'class="dialog-head"' in block
        assert 'class="icon-button dialog-close"' in block
        assert 'aria-label="Close"' in block
        assert 'class="eyebrow"' not in block
    boot = (UI / "js" / "boot.js").read_text()
    assert '.closest?.("[data-dialog-close]")' in boot
    assert 'button.closest("dialog")?.close("cancel")' in boot


def test_confirm_dialog_forgets_the_last_answer():
    """Escape keeps returnValue, so an old "yes" must not confirm the next dialog."""
    dom = (UI / "js" / "dom.js").read_text()
    reset = dom.index('dlg.returnValue = "";')
    assert reset < dom.index("dlg.showModal();", reset)


def test_project_dialog_shows_basics_and_folds_the_rest():
    html = (UI / "index.html").read_text()
    block = html[html.index('<dialog id="project-dialog"') :]
    block = block[: block.index("</dialog>")]
    more = block.index('<details class="dialog-more" id="project-more">')
    for field in ("p_title", "p_desc", "p_tags", "p_repo_url", "p_org_norepo"):
        assert block.index(f'id="{field}"') < more
    for field in ("p_slug", "p_parent_slug", "p_forge_connection_profile_id", "p_path", "p_forge_owner"):
        assert block.index(f'id="{field}"') > more
    assert "Separate tags with commas." in block
    assert block.index('id="btn-save-project"') < block.index('id="btn-close-project"')
    assert block.index('class="dialog-danger-row"') < block.index('id="btn-delete-project"')


def test_field_tips_are_visible_targets_that_keep_the_field_labelled():
    help_js = (UI / "js" / "help.js").read_text()
    assert 'mark.className = "field-tip-mark"' in help_js
    assert '<span class="field-tip-mark" aria-hidden="true">?</span>' in help_js
    assert "label.htmlFor = control.id" in help_js
    css = (UI / "app.css").read_text()
    tip = css[css.index("button.field-tip,\n.field-tip {") :]
    tip = tip[: tip.index("}")]
    assert "width: 44px;" in tip and "height: 44px;" in tip


def test_field_tip_panel_is_opaque_and_stacks_above_siblings():
    """Open tips must not let later form fields paint through the panel."""
    css = (UI / "app.css").read_text()
    panel = css[css.index(".field-tip-panel {") :]
    panel = panel[: panel.index("\n.field-tip.open .field-tip-panel")]
    assert "background-color: var(--surface);" in panel
    assert "opacity: 1;" in panel
    assert "backdrop-filter: none;" in panel
    assert ".field-tip.open { z-index: 40; }" in css


def test_toasts_have_a_full_size_close_and_a_kind_dot():
    css = (UI / "app.css").read_text()
    close = css[css.index(".toast-close {") :]
    close = close[: close.index("}")]
    assert "width: 44px;" in close and "height: 44px;" in close
    assert ".toast-error::before { background: var(--danger); }" in css
    state = (UI / "js" / "state.js").read_text()
    assert 'close.setAttribute("aria-label", "Dismiss notification")' in state
