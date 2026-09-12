#!/usr/bin/env python3
"""Apply the approved 2026-09-12 UI/docs redesign.

Temporary branch helper used because the chat sandbox cannot clone GitHub. The
script is deliberately idempotent so CI can apply, commit, then verify the
committed result on a second push. Remove this file before the PR is finalized.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    current = target.read_text(encoding="utf-8") if target.exists() else None
    if current != text:
        target.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"could not find expected {label}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Dashboard HTML
# ---------------------------------------------------------------------------
index_path = "src/adhd_hub/ui/index.html"
index = read(index_path)

if 'class="appearance-bar"' in index:
    start = index.index('  <div class="appearance-bar">')
    end = index.index('  <div id="login-gate"', start)
    index = index[:start] + index[end:]

if '<header class="app-header">' not in index:
    start = index.index('    <header class="top">')
    end = index.index('    </header>', start) + len('    </header>')
    header = '''    <header class="app-header">
      <div class="app-brand">
        <img class="brand-mark small" src="/ui/brand/icon.svg" alt="" width="32" height="32" />
        <span>Progress Hub</span>
      </div>
      <nav class="desktop-nav" aria-label="Main views">
        <button type="button" data-screen="now" aria-current="page">Now</button>
        <button type="button" data-screen="work">My work</button>
        <button type="button" data-screen="progress">Progress</button>
      </nav>
      <div class="app-header-actions">
        <button type="button" class="ghost" id="btn-capture" aria-haspopup="dialog">Save a thought</button>
        <button type="button" class="ghost" id="btn-settings">Settings</button>
        <details id="appearance-menu" class="appearance-menu">
          <summary aria-label="Appearance">Appearance</summary>
          <div class="appearance-popover">
            <span class="meta">Theme</span>
            <div class="theme-toggle theme-toggle-labeled" role="radiogroup" aria-label="Theme" data-theme-toggle>
              <button type="button" class="theme-option" role="radio" aria-checked="false" data-theme-value="system"><span>System</span></button>
              <button type="button" class="theme-option" role="radio" aria-checked="false" data-theme-value="light"><span>Light</span></button>
              <button type="button" class="theme-option" role="radio" aria-checked="false" data-theme-value="dark"><span>Dark</span></button>
            </div>
          </div>
        </details>
      </div>
    </header>'''
    index = index[:start] + header + index[end:]

index = index.replace(
    '<p>Choose a task to bring into Now.</p>',
    '<p>Scan your work. Open context only when you need it.</p>',
)
index = index.replace(
    '<details class="progress-numbers">',
    '<details class="progress-numbers" id="activity-section" open>',
    1,
)
index = index.replace(
    '<details class="activity-details">',
    '<details class="activity-details" open>',
    1,
)
index = index.replace(
    '<section id="rewards-panel" aria-labelledby="rewards-title" hidden>',
    '<section id="rewards-panel" class="milestones" aria-labelledby="rewards-title" hidden>',
    1,
)

old_settings_header = '''            <div class="settings-header">
              <div>
                <p class="eyebrow">MAKE YOURSELF AT HOME</p>
                <h1 id="settings-title">Settings</h1>
              </div>
            </div>'''
new_settings_header = '''            <div class="settings-header">
              <button type="button" class="text-button settings-index-back" id="btn-settings-index-back">← Back to settings</button>
              <div>
                <h1 id="settings-title">Settings</h1>
                <p class="hint">Preferences, connections and data — change only what you need.</p>
              </div>
            </div>'''
index = replace_once(index, old_settings_header, new_settings_header, label="settings header")

mobile_nav = '''    <nav class="mobile-nav" aria-label="Main views">
      <button type="button" data-screen="now">Now</button>
      <button type="button" data-screen="work">My work</button>
      <button type="button" data-screen="progress">Progress</button>
      <button type="button" id="btn-mobile-settings">Settings</button>
    </nav>
'''
if 'class="mobile-nav"' not in index:
    needle = '    </main>\n  </div>\n\n  <dialog id="project-dialog"'
    replacement = '    </main>\n' + mobile_nav + '  </div>\n\n  <dialog id="project-dialog"'
    index = replace_once(index, needle, replacement, label="mobile navigation insertion")

write(index_path, index)


# ---------------------------------------------------------------------------
# Minimal JS behaviour changes. Only touch modules already drifting on main.
# ---------------------------------------------------------------------------
boot_path = "src/adhd_hub/ui/js/boot.js"
boot = read(boot_path)
boot = boot.replace(
    'import { approveCliConnect, approveOpenClawPair, cancelOpenClawPair, copyOpenClawPrompt, exportBackup, importBackup, importForgeInbox, loadCliSessions, loadForge, loadOpenClaw, loadPrefs, offerPendingConnect, saveConnectAgents, saveForge, saveOpenClaw, saveSettings, scanForgeImport, selectSettingsTab, startOpenClawPair, syncForge, testOpenClaw } from \'./settings.js\';',
    'import { approveCliConnect, approveOpenClawPair, cancelOpenClawPair, copyOpenClawPrompt, exportBackup, importBackup, importForgeInbox, loadCliSessions, loadForge, loadOpenClaw, loadPrefs, offerPendingConnect, saveConnectAgents, saveForge, saveOpenClaw, saveSettings, scanForgeImport, selectSettingsTab, showSettingsIndex, startOpenClawPair, syncForge, testOpenClaw } from \'./settings.js\';',
)
if '$("btn-mobile-settings")?.addEventListener' not in boot:
    anchor = '$("btn-settings").addEventListener("click", () => {'
    pos = boot.index(anchor)
    block_end = boot.index('\n});', pos) + len('\n});')
    addition = '''
$("btn-mobile-settings")?.addEventListener("click", () => $("btn-settings").click());'''
    boot = boot[:block_end] + addition + boot[block_end:]

# Mobile Settings opens on the category index instead of forcing Preferences.
boot = boot.replace(
    '  selectSettingsTab("preferences");\n  $("mcp-url").value = location.origin + "/mcp";',
    '  if (matchMedia("(max-width: 760px)").matches) showSettingsIndex();\n  else selectSettingsTab("preferences");\n  $("mcp-url").value = location.origin + "/mcp";',
    1,
)
if '$("btn-settings-index-back")?.addEventListener' not in boot:
    boot = boot.replace(
        'document.querySelectorAll("[data-settings-tab]").forEach((tab) => {',
        '$("btn-settings-index-back")?.addEventListener("click", showSettingsIndex);\n'
        'document.querySelectorAll("[data-settings-tab]").forEach((tab) => {',
        1,
    )
write(boot_path, boot)

settings_path = "src/adhd_hub/ui/js/settings.js"
settings = read(settings_path)
if 'export function showSettingsIndex()' not in settings:
    settings = settings.replace(
        'export function selectSettingsTab(name, focus = false) {',
        '''export function showSettingsIndex() {
  const view = $("settings-view");
  if (!view) return;
  view.classList.add("settings-index-open");
  const heading = view.querySelector("h1");
  if (heading) {
    if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
    heading.focus({ preventScroll: true });
  }
}

export function selectSettingsTab(name, focus = false) {
  $("settings-view")?.classList.remove("settings-index-open");''',
        1,
    )
write(settings_path, settings)

screens_path = "src/adhd_hub/ui/js/screens.js"
screens = read(screens_path)
if 'const mobileSettingsBtn' not in screens:
    anchor = '''  const settingsBtn = $("btn-settings");
  if (settingsBtn) {
    if (next === "settings") settingsBtn.setAttribute("aria-current", "page");
    else settingsBtn.removeAttribute("aria-current");
  }
'''
    replacement = anchor + '''  const mobileSettingsBtn = $("btn-mobile-settings");
  if (mobileSettingsBtn) {
    if (next === "settings") mobileSettingsBtn.setAttribute("aria-current", "page");
    else mobileSettingsBtn.removeAttribute("aria-current");
  }
'''
    screens = replace_once(screens, anchor, replacement, label="mobile settings current state")
write(screens_path, screens)


# ---------------------------------------------------------------------------
# Dashboard CSS — append a final, idempotent redesign layer. This deliberately
# overrides legacy glossy selectors without rewriting unrelated functional CSS.
# ---------------------------------------------------------------------------
css_path = "src/adhd_hub/ui/app.css"
css = read(css_path)
marker = "/* --- 2026 calm redesign override --- */"
if marker not in css:
    css += r'''

/* --- 2026 calm redesign override --- */
:root {
  --bg: #f7f6f1;
  --card: #ffffff;
  --surface: #eff1ec;
  --ink: #20332c;
  --muted: #617069;
  --line: #d7ddd8;
  --accent: #176b60;
  --accent-ink: #ffffff;
  --accent-soft: #eff1ec;
  --ok: #176b60;
  --ok-soft: #eff1ec;
  --warn: #b18430;
  --danger: #ab3546;
  --gold: #b18430;
  --gold-soft: #f7f0dd;
  --gold-ink: #765815;
  --shadow: 0 18px 50px rgb(32 51 44 / 0.14);
  --radius: 10px;
  --shell-pad: clamp(1rem, 2.5vw, 2rem);
  --shell-max: 1600px;
}
:root[data-theme="dark"] {
  --bg: #0d1210;
  --card: #151d19;
  --surface: #172a24;
  --ink: #e7eeea;
  --muted: #98a89f;
  --line: #2a3731;
  --accent: #7acdb6;
  --accent-ink: #0d1210;
  --accent-soft: #172a24;
  --ok: #7acdb6;
  --ok-soft: #172a24;
  --warn: #ddbb68;
  --danger: #f08c99;
  --gold: #ddbb68;
  --gold-soft: #292617;
  --gold-ink: #ddbb68;
  --shadow: 0 18px 50px rgb(0 0 0 / 0.32);
}
:root[data-theme="dark"] body { background: var(--bg); }
body { background: var(--bg); color: var(--ink); }

/* One application shell, no permanent second toolbar. */
.shell { max-width: var(--shell-max); padding: 0 var(--shell-pad) 3rem; }
.app-header {
  min-height: 64px;
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto minmax(180px, 1fr);
  align-items: center;
  gap: 1.25rem;
  margin-bottom: 2rem;
  border-bottom: 1px solid var(--line);
  background: var(--bg);
}
.app-brand { display: flex; align-items: center; gap: .7rem; font-weight: 720; letter-spacing: -.025em; }
.desktop-nav { display: flex; align-items: center; gap: .2rem; }
.desktop-nav button { background: transparent; color: var(--muted); border: 0; border-radius: 8px; padding-inline: .8rem; }
.desktop-nav button[aria-current="page"] { color: var(--ink); background: var(--accent-soft); }
.app-header-actions { justify-self: end; display: flex; align-items: center; gap: .4rem; }
.appearance-menu { position: relative; }
.appearance-menu > summary {
  list-style: none;
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  padding: .45rem .75rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  color: var(--muted);
  font-size: .85rem;
  font-weight: 600;
}
.appearance-menu > summary::-webkit-details-marker { display: none; }
.appearance-popover {
  position: absolute;
  z-index: 60;
  top: calc(100% + .45rem);
  right: 0;
  width: 230px;
  padding: .8rem;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: color-mix(in srgb, var(--card) 96%, var(--bg));
  box-shadow: var(--shadow);
}
.theme-toggle { background: transparent; box-shadow: none; border-radius: 8px; }
.theme-option { border-radius: 7px; }
.theme-option.is-active, .theme-option[aria-checked="true"] { box-shadow: none; }
.mobile-nav { display: none; }

/* Focus remains obvious without turning page headings into giant boxes. */
.view-heading h1[tabindex="-1"]:focus,
.settings-header h1[tabindex="-1"]:focus {
  outline: 0;
  box-shadow: inset 3px 0 0 var(--accent);
  padding-left: .75rem;
}

/* Now is intentionally narrow and centred. */
.now-view { width: min(100%, 840px); max-width: 840px; margin: 2.5rem auto 0; }
.now-view .view-heading { max-width: 700px; }
.now-view .focus {
  padding: clamp(1.25rem, 3vw, 2rem);
  border: 1px solid var(--line);
  border-top: 1px solid var(--line);
  border-radius: 16px;
  background: var(--card);
  box-shadow: none;
  backdrop-filter: none;
}
.now-view .next-card { min-height: 145px; }
.next-card, .resume-step-prominent { border-radius: 8px; }
.resume-step { border-radius: 0 8px 8px 0; }

/* My Work: dense scanning first, context on demand. */
#work-view { width: min(100%, 1500px); margin: 0 auto; }
#work-view .layout { grid-template-columns: 210px minmax(0, 1fr); gap: 1.5rem; }
#work-view .rail {
  position: sticky;
  top: 1rem;
  padding: .25rem 1rem .5rem 0;
  border-right: 1px solid var(--line);
}
#work-view .rail-head { margin-bottom: .5rem; }
#work-view .rail-head .primary { background: transparent; color: var(--accent); border-color: var(--line); }
.proj { margin: 0; padding: .6rem .65rem; border-radius: 7px; }
.proj.active { color: var(--ink); background: var(--accent-soft); }
.work-heading { padding-bottom: .8rem; margin-bottom: 0; border-bottom: 1px solid var(--line); }
.threads-panel { padding-top: .75rem; }
.tabs { margin-bottom: .65rem; padding-bottom: .65rem; }
#thread-search { max-width: 560px; }
#thread-count { margin: .55rem 0; }
#threads { display: grid; gap: 0; border-top: 1px solid var(--line); }
.thread {
  border: 0;
  border-bottom: 1px solid var(--line);
  border-left: 0;
  border-radius: 0;
  padding: .85rem .35rem;
  background: transparent;
}
.thread:hover { background: color-mix(in srgb, var(--accent-soft) 55%, transparent); }
.thread.chosen { background: var(--accent-soft); border-color: var(--line); }
.thread-number { display: none; }
.thread-topline { gap: .65rem; }
.thread-project { color: var(--muted); font-size: .68rem; }
.thread-status { background: transparent; border: 1px solid var(--line); color: var(--muted); }
.thread h3 { margin: .38rem 0 .25rem; font-size: .98rem; font-weight: 620; }
.thread-meta { font-size: .72rem; }
.thread .actions { margin-top: .45rem; }
.thread .progress-details { margin-top: .35rem; border-top: 0; padding-top: 0; }
.thread .progress-details > summary { min-height: 32px; padding: .25rem 0; }
.thread:has(.progress-details[open]) { background: var(--accent-soft); }
@media (min-width: 1100px) {
  .thread .progress-details[open] {
    position: fixed;
    z-index: 45;
    top: 88px;
    right: max(24px, calc((100vw - 1600px) / 2 + 24px));
    width: min(390px, 31vw);
    max-height: calc(100dvh - 116px);
    overflow: auto;
    padding: 1rem 1.1rem;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: color-mix(in srgb, var(--card) 97%, var(--bg));
    box-shadow: var(--shadow);
  }
  .thread .progress-details[open] > summary { position: sticky; top: 0; background: inherit; color: var(--accent); }
}

/* Progress: reflection first, rewards second. */
.progress-view { width: min(100%, 980px); max-width: 980px; margin: 2.5rem auto; }
#activity-section { margin: 0 0 2rem; }
#activity-section > summary, #activity-section > .activity-details > summary { display: none; }
#activity-section .stats { display: grid; grid-template-columns: repeat(2, minmax(0, 180px)); gap: 1rem; padding: 0 0 1.25rem; }
#activity-section .stat { text-align: left; padding-right: 1rem; }
#activity-section .stat strong { font-size: 1.8rem; }
#activity-section .activity-details { margin-top: 0; padding-top: 1rem; border-top: 1px solid var(--line); }
#activity-section .chart { height: 150px; gap: 5px; }
.milestones { margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid var(--line); }
.milestones .rank-hero { padding: 0 0 1rem; border: 0; border-radius: 0; background: transparent; }
.milestones .rank-hero h2 { font-size: clamp(1.5rem, 4vw, 2rem); }
.milestones .rank-emblem { width: 48px; height: 48px; border: 0; border-radius: 12px; }
.milestones .reward-daily { padding: 1rem 0; }
.milestones .badges-section { margin: 1rem 0; }
.milestones .badge-grid { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .5rem; }
.milestones .badge { padding: .75rem; border: 1px solid var(--line); border-radius: 8px; background: transparent; }
.milestones .badge.earned { background: var(--gold-soft); border-color: color-mix(in srgb, var(--gold) 30%, var(--line)); }
.milestones .badge-symbol { width: 24px; height: 24px; }

/* Settings: preferences layout, not a giant card. */
.settings-view { width: min(100%, 1180px); margin: 0 auto; }
.settings-page { grid-template-columns: 210px minmax(0, 840px); justify-content: center; gap: 2rem; min-height: 0; }
.settings-nav {
  position: sticky;
  top: 1rem;
  padding: 0 1rem 0 0;
  border: 0;
  border-right: 1px solid var(--line);
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
}
.settings-nav-item { border-radius: 7px; }
.settings-nav-item[aria-selected="true"] { color: var(--ink); border-color: transparent; background: var(--accent-soft); }
.settings-main {
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
  overflow: visible;
}
.settings-header { display: grid; gap: .35rem; padding: 0 0 1rem; border-bottom: 1px solid var(--line); }
.settings-header h1 { font-size: clamp(1.7rem, 3vw, 2.1rem); }
.settings-header .hint { margin: .35rem 0 0; }
.settings-index-back { display: none; }
.settings-content { overflow: visible; padding: 1.25rem 0 2rem; max-width: 840px; scrollbar-gutter: auto; }
#settings-msg:not(:empty) { margin: .75rem 0 0; border-radius: 8px; }
.settings-content .setup-banner { border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }
.settings-footer { padding: .8rem 0; }

/* Dialogs/popovers are where elevation belongs. */
dialog { border-radius: 12px; background: var(--card); box-shadow: var(--shadow); }
dialog::backdrop { background: rgb(5 8 7 / .66); backdrop-filter: none; }
.dialog-card { padding: 1.5rem; }
.login-card { border-radius: 14px; background: var(--card); backdrop-filter: none; box-shadow: none; }

@media (max-width: 900px) {
  #work-view .layout { grid-template-columns: 180px minmax(0, 1fr); }
  .settings-page { grid-template-columns: 190px minmax(0, 1fr); gap: 1.25rem; }
}

@media (max-width: 760px) {
  .shell { padding: 0 1rem calc(86px + env(safe-area-inset-bottom)); }
  .app-header { min-height: 56px; grid-template-columns: 1fr auto; margin-bottom: 1.25rem; }
  .desktop-nav, #appearance-menu, .app-header-actions #btn-settings { display: none; }
  .app-header-actions { justify-self: end; }
  .app-header-actions #btn-capture { padding: .45rem .65rem; }
  .mobile-nav {
    position: fixed;
    z-index: 80;
    left: 0;
    right: 0;
    bottom: 0;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    padding: .35rem .5rem calc(.35rem + env(safe-area-inset-bottom));
    border-top: 1px solid var(--line);
    background: color-mix(in srgb, var(--bg) 96%, transparent);
  }
  .mobile-nav button { min-height: 48px; padding: .35rem .2rem; background: transparent; border: 0; color: var(--muted); font-size: .78rem; }
  .mobile-nav button[aria-current="page"] { color: var(--accent); background: var(--accent-soft); }
  .now-view { margin-top: 1.5rem; }
  .now-view .focus { padding: 1.15rem; border-radius: 12px; }
  .focus-toolbar { align-items: flex-start; }
  .focus-toolbar-actions { flex-wrap: wrap; justify-content: flex-end; }
  #work-view .layout { grid-template-columns: 1fr; }
  #work-view .rail { position: static; padding: 0 0 .75rem; border-right: 0; border-bottom: 1px solid var(--line); }
  #project-list { display: flex; gap: .3rem; overflow-x: auto; max-height: none; padding-bottom: .2rem; }
  #project-list .proj { flex: 0 0 auto; width: auto; min-width: 130px; }
  .work-heading-row { align-items: center; }
  .thread .progress-details[open] {
    position: fixed;
    z-index: 90;
    inset: 56px 0 calc(64px + env(safe-area-inset-bottom));
    overflow: auto;
    margin: 0;
    padding: 1rem;
    border: 0;
    border-radius: 0;
    background: var(--bg);
  }
  .thread .progress-details[open] > summary { color: var(--accent); font-size: .9rem; }
  .thread .progress-details[open] > summary::before { content: "← "; }
  #activity-section .stats { grid-template-columns: 1fr 1fr; }
  #activity-section .chart { height: 110px; }
  .milestones .rank-hero { align-items: flex-start; }
  .settings-page { display: block; }
  .settings-nav { position: static; padding: 0; border: 0; }
  .settings-nav-title, .settings-nav-group { width: 100%; }
  .settings-nav-item { width: 100%; justify-content: space-between; border-bottom: 1px solid var(--line); border-radius: 0; }
  .settings-index-open .settings-main { display: none; }
  .settings-view:not(.settings-index-open) .settings-nav { display: none; }
  .settings-view:not(.settings-index-open) .settings-main { display: block; }
  .settings-index-back { display: inline-flex; justify-self: start; }
  .settings-header { padding-top: .2rem; }
  .settings-content { padding-top: 1rem; }
  .rank-hero, .reward-daily, .share-row { flex-wrap: wrap; }
  .badge-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  input, select, textarea { font-size: 16px; }
}

@media (prefers-reduced-motion: reduce) {
  .view { animation: none; }
}
'''
write(css_path, css)


# ---------------------------------------------------------------------------
# Documentation theme and navigation
# ---------------------------------------------------------------------------
docs_css = r'''/* Progress Hub documentation — calm, flat, information-first. */
:root > * {
  --hub-light-canvas: #f7f6f1;
  --hub-light-surface: #ffffff;
  --hub-light-subtle: #eff1ec;
  --hub-light-text: #20332c;
  --hub-light-muted: #617069;
  --hub-light-line: #d7ddd8;
  --hub-light-accent: #176b60;
  --hub-dark-canvas: #0d1210;
  --hub-dark-chrome: #101613;
  --hub-dark-surface: #151d19;
  --hub-dark-elevated: #1b2520;
  --hub-dark-text: #e7eeea;
  --hub-dark-muted: #98a89f;
  --hub-dark-line: #2a3731;
  --hub-dark-accent: #7acdb6;
  --hub-gold: #ddbb68;
  --md-accent-fg-color: var(--hub-light-accent);
  --md-typeset-a-color: var(--hub-light-accent);
}
[data-md-color-scheme="default"] {
  --md-default-bg-color: var(--hub-light-canvas);
  --md-default-fg-color: var(--hub-light-text);
  --md-default-fg-color--light: var(--hub-light-muted);
  --md-primary-fg-color: var(--hub-light-surface);
  --md-primary-fg-color--light: var(--hub-light-subtle);
  --md-primary-fg-color--dark: var(--hub-light-surface);
  --md-accent-fg-color: var(--hub-light-accent);
  --md-typeset-a-color: var(--hub-light-accent);
  --md-code-bg-color: var(--hub-light-subtle);
}
[data-md-color-scheme="slate"] {
  --md-hue: 160;
  --md-default-bg-color: var(--hub-dark-canvas);
  --md-default-bg-color--light: var(--hub-dark-surface);
  --md-default-bg-color--lighter: var(--hub-dark-elevated);
  --md-default-fg-color: var(--hub-dark-text);
  --md-default-fg-color--light: var(--hub-dark-muted);
  --md-default-fg-color--lighter: #708079;
  --md-primary-fg-color: var(--hub-dark-chrome);
  --md-primary-fg-color--light: var(--hub-dark-surface);
  --md-primary-fg-color--dark: #090d0b;
  --md-accent-fg-color: var(--hub-dark-accent);
  --md-typeset-a-color: var(--hub-dark-accent);
  --md-code-bg-color: var(--hub-dark-surface);
  --md-footer-bg-color: #090d0b;
  --md-footer-bg-color--dark: #070a08;
}
.md-grid { max-width: 1180px; }
.md-header { box-shadow: none; border-bottom: 1px solid color-mix(in srgb, currentColor 12%, transparent); }
[data-md-color-scheme="default"] .md-header { color: var(--hub-light-text); background: var(--hub-light-surface); }
[data-md-color-scheme="slate"] .md-header { color: var(--hub-dark-text); background: var(--hub-dark-chrome); }
.md-tabs { box-shadow: none; backdrop-filter: none; border-bottom: 1px solid color-mix(in srgb, currentColor 10%, transparent); }
[data-md-color-scheme="default"] .md-tabs { background: var(--hub-light-surface); }
[data-md-color-scheme="slate"] .md-tabs { background: var(--hub-dark-chrome); }
.md-search__form { border: 1px solid color-mix(in srgb, currentColor 15%, transparent); border-radius: 8px; box-shadow: none; }
.md-content__inner { max-width: 72ch; margin-inline: auto; }
.md-typeset { line-height: 1.68; }
.md-typeset h1 { font-weight: 650; letter-spacing: -.035em; }
.md-typeset h2, .md-typeset h3 { letter-spacing: -.025em; }
.md-nav__link { border-radius: 6px; }
.md-nav__link--active, .md-nav__item .md-nav__link--active { font-weight: 650; border-left: 2px solid currentColor; padding-left: .6rem; }
[data-md-color-scheme="default"] .md-nav__link--active { color: var(--hub-light-accent); background: var(--hub-light-subtle); }
[data-md-color-scheme="slate"] .md-nav__link--active { color: var(--hub-dark-accent); background: color-mix(in srgb, var(--hub-dark-accent) 8%, transparent); }
.md-typeset pre > code { border-radius: 8px; }
.md-typeset pre { border: 1px solid color-mix(in srgb, currentColor 12%, transparent); border-radius: 8px; box-shadow: none; }
.md-typeset table:not([class]) { border: 1px solid color-mix(in srgb, currentColor 12%, transparent); }
.md-typeset .admonition, .md-typeset details { border-radius: 8px; box-shadow: none; }
.md-typeset a:focus-visible, .md-nav__link:focus-visible, .md-search__input:focus-visible, .md-header__button:focus-visible { outline: 3px solid var(--hub-gold); outline-offset: 2px; }
.md-header__button.md-logo img, .md-header__button.md-logo svg { height: 1.7rem; width: auto; }
@media screen and (min-width: 76.25em) {
  .md-sidebar--primary { width: 14rem; }
  .md-sidebar--secondary { width: 12rem; }
}
@media screen and (max-width: 59.984375em) {
  .md-content__inner { max-width: 72ch; }
}
'''
write("docs/stylesheets/extra.css", docs_css)

zensical = '''[project]
site_name = "ADHD Progress Hub"
site_description = "A calm source of truth for unfinished work."
site_url = "https://uniskela.github.io/adhd-hub/"
docs_dir = "docs"
site_dir = "site"
repo_url = "https://github.com/uniskela/adhd-hub"
repo_name = "uniskela/adhd-hub"
copyright = "ADHD Progress Hub documentation — rendered from reviewed Markdown in the repository."

extra_css = ["stylesheets/extra.css"]

nav = [
  { "Start here" = [
    { "What is ADHD Progress Hub?" = "index.md" },
    { "Installation" = "installation.md" },
    { "Connect an agent" = "connect.md" },
    { "Project agent setup" = "project-agent-setup.md" },
    { "Personal setup" = "setup.md" },
    { "Writing & continuity" = "writing.md" },
  ]},
  { "Using the Hub" = [
    { "Dashboard" = "dashboard.md" },
    { "Coding companions" = "coding-companions.md" },
    { "OpenClaw" = "openclaw.md" },
    { "Forge issue inbox" = "forge-issue-inbox.md" },
    { "Indexer schedule" = "indexer-schedule.md" },
    { "Rewards roadmap" = "rewards-roadmap.md" },
  ]},
  { "Deploy & configure" = [
    { "Homelab deployment" = "deploy-homelab.md" },
    { "Authentication" = "authentication.md" },
    { "Environment variables" = "environment-variables.md" },
    { "Forge permissions" = "forge-permissions.md" },
  ]},
  { "Project" = [
    { "Brand guide" = "brand-guide.md" },
    { "Review improvements" = "review-improvements.md" },
    { "Improvement roadmap" = "plans/improvement-roadmap.md" },
    { "Next waves" = "plans/next-waves.md" },
    { "ADHD Hub foundation" = "plans/adhd-hub-foundation.md" },
    { "Projects CRUD revamp" = "plans/projects-crud-ui-revamp.md" },
    { "Thread outcome model" = "plans/thread-outcome-model.md" },
  ]},
]

[project.theme]
language = "en"
logo = "assets/icon.svg"
favicon = "assets/icon.svg"
features = [
  "content.code.copy",
  "content.footnote.tooltips",
  "content.tooltips",
  "navigation.footer",
  "navigation.indexes",
  "navigation.instant",
  "navigation.path",
  "navigation.sections",
  "navigation.top",
  "navigation.tracking",
  "search.highlight",
  "toc.follow",
]

[[project.theme.palette]]
media = "(prefers-color-scheme)"
primary = "custom"
accent = "custom"
toggle.icon = "lucide/sun-moon"
toggle.name = "Switch to light mode"

[[project.theme.palette]]
media = "(prefers-color-scheme: light)"
scheme = "default"
primary = "custom"
accent = "custom"
toggle.icon = "lucide/sun"
toggle.name = "Switch to dark mode"

[[project.theme.palette]]
media = "(prefers-color-scheme: dark)"
scheme = "slate"
primary = "custom"
accent = "custom"
toggle.icon = "lucide/moon"
toggle.name = "Switch to system preference"

[[project.extra.social]]
icon = "fontawesome/brands/github"
link = "https://github.com/uniskela/adhd-hub"

[project.markdown_extensions]
abbr = {}
admonition = {}
attr_list = {}
def_list = {}
footnotes = {}
md_in_html = {}
toc.permalink = true
pymdownx.betterem = {}
pymdownx.caret = {}
pymdownx.details = {}
pymdownx.emoji.emoji_generator = "zensical.extensions.emoji.to_svg"
pymdownx.emoji.emoji_index = "zensical.extensions.emoji.twemoji"
pymdownx.highlight.anchor_linenums = true
pymdownx.highlight.line_spans = "__span"
pymdownx.highlight.pygments_lang_class = true
pymdownx.inlinehilite = {}
pymdownx.keys = {}
pymdownx.magiclink = {}
pymdownx.mark = {}
pymdownx.superfences.custom_fences = [
  { name = "mermaid", class = "mermaid", format = "pymdownx.superfences.fence_code_format" },
]
pymdownx.tabbed.alternate_style = true
pymdownx.tasklist.custom_checkbox = true
pymdownx.tilde = {}
'''
write("zensical.toml", zensical)

index_md = '''# ADHD Progress Hub

Keep enough context to resume unfinished work without reconstructing your last session.

[Install](installation.md) · [Connect an agent](connect.md) · [View on GitHub](https://github.com/uniskela/adhd-hub)

**Self-hosted · MCP + REST · Cursor / Codex / Claude Code · GitHub/Gitea optional**

## The loop

**Work → Save continuity → Leave → Come back → Resume**

The Hub keeps the parts that matter when you return: what you were trying to do, what matters now, what is blocking you, and the next concrete place to continue.

## Start here

1. [Install the Hub](installation.md).
2. [Connect your coding agent](connect.md).
3. [Set up project continuity](project-agent-setup.md) for substantial work.
4. Open the [dashboard](dashboard.md) when you want to choose, pause, or resume work visually.

For a practical day-to-day routine, see [Personal setup](setup.md). For concise Goal / Focus / Next / Blocked / Resume notes, see [Writing & continuity](writing.md).

## What belongs here?

Repository work can be linked to GitHub/Gitea while the Hub keeps local continuity around it. Non-repository work — homelab changes, migrations, research, admin, or a PC setup — can stay entirely local to the Hub.

The project is designed to be useful without streaks, competitive pressure, or a requirement to keep every task in one system.

## Deploy and configure

- [Homelab deployment](deploy-homelab.md)
- [Authentication](authentication.md)
- [Environment variables](environment-variables.md)
- [Forge permissions](forge-permissions.md)
- [OpenClaw](openclaw.md)

## Project

The [roadmap](plans/improvement-roadmap.md), [next waves](plans/next-waves.md), [brand guide](brand-guide.md), and public repository document how the Hub is evolving.
'''
write("docs/index.md", index_md)

# Narrow brand-guide update: approved semantic palette and flatter surface guidance.
brand_path = "docs/brand-guide.md"
brand = read(brand_path)
brand = re.sub(
    r"\| Role \| Light \| Dark \| Use \|\n\| --- \| --- \| --- \| --- \|\n(?:\|.*\n){11}",
    '''| Role | Light | Dark | Use |\n| --- | --- | --- | --- |\n| Canvas | `#F7F6F1` | `#0D1210` | Page background |\n| Header / navigation | White `#FFFFFF` | `#101613` | Primary chrome |\n| Primary surface | White `#FFFFFF` | `#151D19` | Intentional grouped content |\n| Elevated surface | White `#FFFFFF` | `#1B2520` | Dialogs and popovers |\n| Text | `#20332C` | `#E7EEEA` | Headings and body |\n| Secondary text | `#617069` | `#98A89F` | Supporting text |\n| Primary action | Teal `#176B60` | Mint `#7ACDB6` | Action, focus and selection |\n| Selected subtle background | `#EFF1EC` | `#172A24` | Selected rows/tabs |\n| Divider | `#D7DDD8` | `#2A3731` | Thin boundaries |\n| Achievement accent | `#B18430` | `#DDBB68` | Milestones only |\n| Destructive action | `#AB3546` | `#F08C99` | Delete and irreversible actions |\n''',
    brand,
    count=1,
)
brand = brand.replace(
    'Dialog and focus-surface corners are 18–20 px; controls use 10 px corners. Shadows are subtle and never needed to understand a control.',
    'Ordinary grouped surfaces and controls use roughly 8–10 px corners. The Now focus surface and dialogs may use slightly larger soft corners when that distinction helps. Normal page regions stay flat; reserve shadows for dialogs, popovers, and real elevation.',
)
write(brand_path, brand)

# Dashboard docs: match the redesigned screen-based Settings and compact header.
dashboard_path = "docs/dashboard.md"
dashboard = read(dashboard_path)
dashboard = dashboard.replace(
    'Choose **Appearance → System, Light, or Dark** at the top of the page. The preference is saved in this browser, works on the sign-in page, and follows operating-system changes when set to System. If browser storage is blocked, the dashboard still works and preferences last for the current page visit.',
    'On desktop, use the compact **Appearance** menu in the app header for System, Light, or Dark. The same control is available under **Settings → Preferences**; on mobile, use Settings. The preference is saved in this browser and follows operating-system changes when set to System. If browser storage is blocked, the dashboard still works and preferences last for the current page visit.',
)
dashboard = dashboard.replace(
    'Settings has a fixed **Close settings** button and four sections: **Preferences**, **Account**, **Connections**, and **Data**. Arrow keys, Home, and End move between tabs; Escape closes the dialog. Appearance and rewards save automatically in this browser; timezone uses **Save**. Password controls are under Account. Assistant setup, encrypted OpenClaw connection settings, alert controls, and optional forge configuration live under Connections.',
    'Settings is a full application destination with categories for **Preferences**, **Account**, **Connections**, **Windows / MCP**, **OpenClaw**, **Forge**, and **Data**. Desktop uses the left category navigation; mobile opens a simple Settings index and each category has a Back to settings action. Appearance and rewards save automatically in this browser; timezone uses **Save**. Password controls are under Account.',
)
write(dashboard_path, dashboard)

# Documentation nav tests should lock the new group structure without inventing pages.
test_docs_path = "tests/test_documentation.py"
test_docs = read(test_docs_path)
if 'test_docs_navigation_has_calm_information_architecture' not in test_docs:
    test_docs += '''\n\ndef test_docs_navigation_has_calm_information_architecture() -> None:\n    nav = (REPO_ROOT / "zensical.toml").read_text(encoding="utf-8")\n    for group in ["Start here", "Using the Hub", "Deploy & configure", "Project"]:\n        assert f'{{ "{group}" = [' in nav\n    assert '{ "Connect an agent" = "connect.md" }' in nav\n    assert '{ "Dashboard" = "dashboard.md" }' in nav\n'''
write(test_docs_path, test_docs)

# Focused docs browser smoke: build happens before this script in CI.
docs_smoke_path = ROOT / "scripts/docs_browser_smoke.py"
if not docs_smoke_path.exists():
    docs_smoke = '''"""Smoke-test the built Zensical docs at desktop and mobile sizes."""\nfrom __future__ import annotations\n\nimport os\nimport socket\nimport subprocess\nimport sys\nimport time\nfrom pathlib import Path\n\nfrom playwright.sync_api import expect, sync_playwright\n\n\ndef main() -> None:\n    root = Path(__file__).resolve().parents[1]\n    site = root / "site"\n    if not (site / "index.html").exists():\n        raise SystemExit("Build docs first: uv run zensical build --clean")\n    shots = Path(os.environ.get("ADHD_HUB_DOCS_SCREENSHOT_DIR", "/tmp/adhd-hub-docs-preview"))\n    shots.mkdir(parents=True, exist_ok=True)\n    with socket.socket() as sock:\n        sock.bind(("127.0.0.1", 0))\n        port = sock.getsockname()[1]\n    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=site)\n    try:\n        time.sleep(0.7)\n        with sync_playwright() as pw:\n            browser = pw.chromium.launch(args=["--no-sandbox"])\n            page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")\n            page.goto(f"http://127.0.0.1:{port}/")\n            expect(page.get_by_role("heading", name="ADHD Progress Hub", exact=True)).to_be_visible()\n            expect(page.get_by_text("Work → Save continuity → Leave → Come back → Resume", exact=False)).to_be_visible()\n            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")\n            measure = page.locator(".md-content__inner").evaluate("el => el.getBoundingClientRect().width")\n            assert 500 <= measure <= 900, measure\n            page.screenshot(path=str(shots / "docs-home-desktop.png"), full_page=True, animations="disabled")\n            page.goto(f"http://127.0.0.1:{port}/dashboard/")\n            expect(page.get_by_role("heading", name="A calmer dashboard", exact=True)).to_be_visible()\n            page.screenshot(path=str(shots / "docs-dashboard-desktop.png"), full_page=True, animations="disabled")\n            page.set_viewport_size({"width": 390, "height": 844})\n            page.goto(f"http://127.0.0.1:{port}/")\n            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")\n            page.screenshot(path=str(shots / "docs-home-mobile.png"), full_page=True, animations="disabled")\n            browser.close()\n    finally:\n        server.terminate()\n        server.wait(timeout=10)\n\n\nif __name__ == "__main__":\n    main()\n'''
    write("scripts/docs_browser_smoke.py", docs_smoke)

# Existing browser smoke contains stale selectors predating the screen-based UI.
smoke_path = "scripts/browser_smoke.py"
smoke = read(smoke_path)
smoke = smoke.replace('page.locator("#theme-select").select_option("light")', 'page.evaluate("localStorage.setItem(\\\"adhd_hub_theme\\\", \\\"light\\\")"); page.reload()')
smoke = smoke.replace('page.locator("#theme-select").select_option("dark")', 'page.evaluate("localStorage.setItem(\\\"adhd_hub_theme\\\", \\\"dark\\\")"); page.reload()')
smoke = smoke.replace('page.locator("#theme-select").select_option("system")', 'page.evaluate("localStorage.setItem(\\\"adhd_hub_theme\\\", \\\"system\\\")"); page.reload()')
smoke = smoke.replace('blocked.locator("#theme-select").select_option("light")', 'blocked.locator("#appearance-menu").get_by_text("Appearance", exact=True).click(); blocked.locator("#appearance-menu [data-theme-value=\\\"light\\\"]").click()')
smoke = smoke.replace('page.locator("#settings-theme").select_option("light")', 'page.locator("#settings-preferences [data-theme-value=\\\"light\\\"]").click()')
smoke = smoke.replace('page.locator("#settings-theme").select_option("dark")', 'page.locator("#settings-preferences [data-theme-value=\\\"dark\\\"]").click()')
smoke = smoke.replace('page.locator("#settings-dialog").evaluate(', 'page.locator("#settings-view").evaluate(')
smoke = smoke.replace('expect(page.get_by_role("button", name="Close settings", exact=True)).to_be_in_viewport()', 'expect(page.locator("#settings-title")).to_be_visible()')
# Settings is now a screen: navigate back with Now instead of an obsolete close button.
smoke = smoke.replace('page.get_by_role("button", name="Close settings", exact=True).click()', 'page.get_by_role("button", name="Now", exact=True).click()')
smoke = smoke.replace('expect(page.get_by_role("button", name="Settings", exact=True)).to_be_focused()', 'expect(page.locator("#now-view")).to_be_visible()')
# Updated visual contract assertions.
if 'expect(page.locator(".app-header")).to_be_visible()' not in smoke:
    smoke = smoke.replace(
        'expect(page.locator("#app-shell")).to_be_visible()\n',
        'expect(page.locator("#app-shell")).to_be_visible()\n                expect(page.locator(".appearance-bar")).to_have_count(0)\n                expect(page.locator(".app-header")).to_be_visible()\n                expect(page.locator(".mobile-nav")).to_have_count(1)\n',
        1,
    )
smoke = smoke.replace('my-work-thread-cards.png', 'my-work-dense-list.png')
write(smoke_path, smoke)

print("UI/docs redesign applied.")
