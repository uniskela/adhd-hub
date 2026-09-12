# UI and Documentation Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `/ui` and the public Zensical documentation into a calm, information-first, developer-tool-style experience while preserving all existing backend, API, MCP, authentication, persistence, PWA, and Foundation B semantics.

**Architecture:** Keep the existing server-rendered static dashboard (`index.html` + modular vanilla JS + CSS) and Zensical documentation stack. Reorganize the dashboard DOM around screen-specific layouts, preserve existing API-facing IDs where practical, add only small UI state for My Work details/mobile settings, and centralize both app/docs styling around the approved Progress Hub semantic palette. Browser smoke tests remain the behavioural safety net; documentation navigation/build checks cover the wiki redesign.

**Tech Stack:** Python, FastAPI-served static UI, vanilla ES modules, HTML/CSS, Playwright, pytest, Zensical.

**Spec:** `docs/superpowers/specs/2026-09-12-ui-docs-redesign-design.md`

**Palette addendum:** `docs/superpowers/specs/2026-09-12-ui-docs-redesign-palette-addendum.md`

## Global Constraints

- No Thread/Project schema changes.
- No Foundation B source/authority, forge reconciliation, or MCP behaviour changes.
- No #72 statistics implementation and no #75 event/SSE implementation.
- No frontend framework migration and no new React/Vue/Svelte dependency.
- Keep System as the default theme; light/dark preference persistence must remain compatible with `adhd_hub_theme`.
- Dark UI semantic colours: canvas `#0D1210`, chrome `#101613`, surface `#151D19`, elevated `#1B2520`, divider `#2A3731`, text `#E7EEEA`, muted `#98A89F`, accent `#7ACDB6`, strong teal `#2B8877`, selected `#172A24`, gold `#DDBB68`, danger `#F08C99`.
- Light UI semantic colours: canvas `#F7F6F1`, surface `#FFFFFF`, secondary `#EFF1EC`, text `#20332C`, muted `#617069`, teal `#176B60`, divider `#D7DDD8`, gold `#B18430`, danger `#AB3546`.
- No decorative page gradients, mint glows, widespread backdrop blur, or generic glassmorphism.
- Ordinary grouped content uses approximately 8–10px radii; reserve larger soft corners and shadow for the Now focus surface, dialogs, and real elevation.
- Preserve programmatic screen-heading focus, keyboard focus visibility, 44px touch targets where applicable, reduced-motion support, and colour-independent state cues.
- Preserve existing user-visible capabilities: auth/password/token, project CRUD, thread filters/search/select, Now start/resume/pause/done, capture/reminders, rewards/share, Settings/Connections/Forge/Data, and PWA behaviour.
- Keep the redesign branch free of Foundation B model/sync changes. Rebase/cherry-pick only presentation-safe main changes if required before merge.
- After meaningful code edits run `graphify update .` as required by `AGENTS.md`.

---

## File Map

### Dashboard shell and styling

- `src/adhd_hub/ui/index.html` — semantic screen/layout structure, header theme menu, mobile bottom nav, My Work detail pane, Settings mobile index/back affordance.
- `src/adhd_hub/ui/app.css` — semantic colour tokens, screen-specific widths/layouts, compact work rows, focus treatment, responsive/mobile rules, dialog/settings/docs-independent UI visuals.
- `src/adhd_hub/ui/js/theme.js` — existing shared theme preference behaviour; reuse its `[data-theme-toggle]` contract unless an implementation defect requires a focused fix.
- `src/adhd_hub/ui/js/screens.js` — destination current-state + heading focus only; no backend changes expected.
- `src/adhd_hub/ui/js/state.js` — minimal selected-work-detail UI state.
- `src/adhd_hub/ui/js/work.js` — dense list rendering, selected task detail rendering, Back-to-list behaviour.
- `src/adhd_hub/ui/js/settings.js` — desktop category selection plus mobile settings-index state.
- `src/adhd_hub/ui/js/boot.js` — event wiring for header/mobile navigation, detail, and settings controls.
- `src/adhd_hub/ui/js/progress.js` — preserve data calculations; compact milestone container/markup only.

### Documentation

- `docs/stylesheets/extra.css` — flat docs theme using the same semantic palette, ~72ch reading measure, restrained navigation/code/admonitions.
- `zensical.toml` — reorganized Start here / Using the Hub / Deploy & configure / Project navigation.
- `docs/index.md` — concise docs landing page and first-use flow.
- `docs/brand-guide.md` — narrow palette/radius wording update so implementation and brand guidance agree.
- `tests/test_documentation.py` — nav contract checks.

### Behaviour verification

- `scripts/browser_smoke.py` — dashboard desktop/mobile flows and screenshots.
- `scripts/docs_browser_smoke.py` — focused docs build/render/screenshot smoke check.

---

### Task 1: Establish the semantic palette, shell, theme menu, and focus treatment

**Files:**
- Modify: `src/adhd_hub/ui/index.html`
- Modify: `src/adhd_hub/ui/app.css`
- Modify: `src/adhd_hub/ui/js/boot.js`
- Modify: `scripts/browser_smoke.py`
- Modify: `docs/brand-guide.md`
- Read/verify only unless needed: `src/adhd_hub/ui/js/theme.js`

**Interfaces:**
- Consumes: existing `[data-theme-toggle]` / `[data-theme-value]` contract and `adhd_hub_theme` preference from `theme.js`.
- Produces: one `.app-header`, desktop `#appearance-menu`, `.mobile-nav`, screen-specific width classes, and heading-specific `h1[tabindex="-1"]:focus-visible` styling used by later tasks.

- [ ] **Step 1: Add failing browser-smoke assertions for the new shell contract**

In `scripts/browser_smoke.py`, after successful login and before navigating away from Now, add assertions that intentionally fail against the old UI:

```python
expect(page.locator(".appearance-bar")).to_have_count(0)
expect(page.locator(".app-header")).to_be_visible()
expect(page.locator("#appearance-menu")).to_be_visible()
expect(page.locator(".mobile-nav")).to_have_count(1)
expect(page.locator("#now-view h1")).to_be_focused()
```

Add a 390×844 mobile page later in the same smoke session and assert the desktop appearance shortcut is hidden while bottom navigation is visible:

```python
mobile = browser.new_page(
    viewport={"width": 390, "height": 844},
    reduced_motion="reduce",
)
mobile.goto(base + "/ui")
mobile.locator("#login-token").fill(password)
mobile.get_by_role("button", name="Sign in", exact=True).click()
expect(mobile.locator(".mobile-nav")).to_be_visible()
expect(mobile.locator("#appearance-menu")).to_be_hidden()
```

- [ ] **Step 2: Run the smoke test and confirm the shell assertions fail**

Run:

```bash
uv run --with playwright python scripts/browser_smoke.py
```

Expected: failure because `.appearance-bar` still exists and `.app-header`, `#appearance-menu`, and `.mobile-nav` do not yet exist.

- [ ] **Step 3: Replace the global colour/chrome tokens with the approved semantic palette**

At the top of `src/adhd_hub/ui/app.css`, replace the current glossy token set with semantic variables. Keep existing aliases temporarily where existing rules still reference them:

```css
:root {
  color-scheme: light;
  --canvas: #f7f6f1;
  --chrome: #ffffff;
  --surface: #ffffff;
  --surface-subtle: #eff1ec;
  --surface-elevated: #ffffff;
  --text: #20332c;
  --muted: #617069;
  --divider: #d7ddd8;
  --accent: #176b60;
  --accent-strong: #176b60;
  --accent-soft: #eff1ec;
  --gold: #b18430;
  --danger: #ab3546;
  --focus-ring: #176b60;
  --radius-control: 8px;
  --radius-surface: 10px;
  --radius-focus: 16px;
  --shadow-elevated: 0 18px 50px rgb(32 51 44 / 0.16);

  /* compatibility aliases while existing selectors are migrated */
  --bg: var(--canvas);
  --card: var(--surface);
  --ink: var(--text);
  --line: var(--divider);
  --warn: var(--gold);
}

:root[data-theme="dark"] {
  color-scheme: dark;
  --canvas: #0d1210;
  --chrome: #101613;
  --surface: #151d19;
  --surface-subtle: #172a24;
  --surface-elevated: #1b2520;
  --text: #e7eeea;
  --muted: #98a89f;
  --divider: #2a3731;
  --accent: #7acdb6;
  --accent-strong: #2b8877;
  --accent-soft: #172a24;
  --gold: #ddbb68;
  --danger: #f08c99;
  --focus-ring: #7acdb6;
  --shadow-elevated: 0 18px 50px rgb(0 0 0 / 0.35);
}

body {
  margin: 0;
  min-height: 100dvh;
  background: var(--canvas);
  color: var(--text);
  font: 15px/1.55 ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
```

Delete the dark-mode body radial gradients and ordinary-section `backdrop-filter` rules rather than recreating them with the new tokens.

- [ ] **Step 4: Replace the two-bar shell with one application header and a desktop theme popover**

In `index.html`, delete the top-level `.appearance-bar` block. Replace the app header with this structure while preserving the existing button IDs used by JS:

```html
<header class="app-header">
  <a class="app-brand" href="#main-content" aria-label="Progress Hub home">
    <img src="/ui/brand/icon.svg" alt="" width="32" height="32" />
    <span>Progress Hub</span>
  </a>

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
        <div class="theme-toggle" role="radiogroup" aria-label="Theme" data-theme-toggle>
          <button type="button" role="radio" aria-checked="false" data-theme-value="system">System</button>
          <button type="button" role="radio" aria-checked="false" data-theme-value="light">Light</button>
          <button type="button" role="radio" aria-checked="false" data-theme-value="dark">Dark</button>
        </div>
      </div>
    </details>
  </div>
</header>
```

Before the end of `#app-shell`, add the mobile destination nav. Use `data-screen` for all four buttons so the existing screen router can set `aria-current` consistently:

```html
<nav class="mobile-nav" aria-label="Main views">
  <button type="button" data-screen="now">Now</button>
  <button type="button" data-screen="work">My work</button>
  <button type="button" data-screen="progress">Progress</button>
  <button type="button" data-screen="settings">Settings</button>
</nav>
```

- [ ] **Step 5: Make the generic destination handler initialize Settings regardless of which Settings control is used**

Extract the current `#btn-settings` setup code in `boot.js` into one async initializer so both the desktop Settings button and mobile `data-screen="settings"` route get the same behaviour:

```js
async function prepareSettings() {
  await Promise.allSettled([
    loadForge(),
    loadOpenClawSecureStatus(),
    loadCliSessions(),
    loadPrefs(),
  ]);
  $("mcp-url").value = location.origin + "/mcp";
  $("install-cmd").value = 'curl -fsSL "' + location.origin + '/install.sh" | sh -s -- .';
  $("install-cmd-win").value = 'irm "' + location.origin + '/install.ps1" | iex';
  $("settings-msg").textContent = "";
  const agentsMsg = $("connect-agents-msg");
  if (agentsMsg) agentsMsg.textContent = "";
  api("/health").then((health) => {
    $("app-version").textContent = health.version ? `v${health.version}` : "Version unavailable";
  }).catch(() => { $("app-version").textContent = "Version unavailable"; });
}
```

Then, inside the existing `[data-screen]` click handler:

```js
if (state.activeScreen === "settings") {
  await prepareSettings();
  selectSettingsTab("preferences");
} else if (state.activeScreen === "work") {
  await selectProject(state.projectFilter);
} else if (state.activeScreen === "now") {
  await loadChosenThread();
} else if (state.activeScreen === "progress") {
  await loadOverview();
}
```

Keep `#btn-settings` for the desktop header, but make its listener call `showScreen("settings")`, `prepareSettings()`, and `selectSettingsTab("preferences")` rather than duplicating setup code.

- [ ] **Step 6: Add flat shell, responsive nav, popover, and heading-focus CSS**

Add/replace the shell rules with concrete behaviour:

```css
.shell {
  width: min(100%, 1600px);
  margin: 0 auto;
  padding: 0 clamp(16px, 2vw, 32px) 48px;
}

.app-header {
  min-height: 64px;
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto minmax(180px, 1fr);
  align-items: center;
  gap: 20px;
  border-bottom: 1px solid var(--divider);
  background: var(--canvas);
}

.app-header-actions {
  justify-self: end;
  display: flex;
  align-items: center;
  gap: 8px;
}

.appearance-menu { position: relative; }
.appearance-menu > summary {
  list-style: none;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  padding: 0 12px;
  border-radius: var(--radius-control);
  cursor: pointer;
}
.appearance-menu > summary::-webkit-details-marker { display: none; }
.appearance-popover {
  position: absolute;
  z-index: 30;
  top: calc(100% + 8px);
  right: 0;
  width: 220px;
  padding: 12px;
  background: var(--surface-elevated);
  border: 1px solid var(--divider);
  border-radius: var(--radius-surface);
  box-shadow: var(--shadow-elevated);
}

.view > .view-heading h1[tabindex="-1"]:focus-visible {
  outline: 0;
  box-shadow: inset 3px 0 0 var(--focus-ring);
  padding-left: 12px;
}

.mobile-nav { display: none; }

@media (max-width: 760px) {
  .shell { padding: 0 16px calc(88px + env(safe-area-inset-bottom)); }
  .desktop-nav, #appearance-menu { display: none; }
  .app-header {
    min-height: 56px;
    grid-template-columns: 1fr auto;
  }
  .app-header-actions #btn-settings { display: none; }
  .mobile-nav {
    position: fixed;
    z-index: 40;
    left: 0;
    right: 0;
    bottom: 0;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    padding: 6px 8px calc(6px + env(safe-area-inset-bottom));
    border-top: 1px solid var(--divider);
    background: var(--chrome);
  }
  .mobile-nav button { min-height: 48px; }
}
```

- [ ] **Step 7: Narrowly align `docs/brand-guide.md` with the approved palette/radius guidance**

Update the colour table and surface guidance so it no longer instructs implementation to use the old dark values or 18–20px ordinary surface corners. Keep the logo rules and voice rules intact. Add this sentence under spacing/surfaces:

```markdown
Ordinary grouped surfaces use 8–10 px corners. Reserve larger soft corners for the primary Now focus surface, dialogs, and genuinely elevated content; prefer dividers and spacing over creating another card.
```

Use the exact palette values from the palette addendum rather than introducing another near-duplicate forest/teal set.

- [ ] **Step 8: Run shell/theme tests and commit**

Run:

```bash
graphify update .
uv run pytest
uv run ruff check src tests scripts
uv run --with playwright python scripts/browser_smoke.py
```

Expected: all existing flows plus the new shell assertions pass.

Commit:

```bash
git add src/adhd_hub/ui/index.html src/adhd_hub/ui/app.css src/adhd_hub/ui/js/boot.js scripts/browser_smoke.py docs/brand-guide.md
git commit -m "feat: establish calm ui shell and palette"
```

---

### Task 2: Redesign Now and My Work around focus + dense scanning

**Files:**
- Modify: `src/adhd_hub/ui/index.html`
- Modify: `src/adhd_hub/ui/app.css`
- Modify: `src/adhd_hub/ui/js/state.js`
- Modify: `src/adhd_hub/ui/js/work.js`
- Modify: `src/adhd_hub/ui/js/boot.js`
- Modify: `scripts/browser_smoke.py`

**Interfaces:**
- Consumes: existing thread payloads (`resume_step`, `focus`, `progress_snippet`, forge URL/number), `chooseThread(thread_id)`, `copyReference(thread_id)`, `wireNotes(root)`, `formatWhen()`.
- Produces: `state.inspectedThreadId`, `inspectThread(threadId)`, `closeThreadDetail()`, `renderThreadDetail(thread)`, and one `#work-detail-pane` that is a right pane on desktop and a full-width work detail view below the responsive breakpoint.

- [ ] **Step 1: Add failing smoke assertions for compact list/detail behaviour**

After navigating to My Work, assert that old `.thread` cards are gone and the new list/detail contract exists:

```python
page.get_by_role("button", name="My work", exact=True).click()
expect(page.locator("#threads .thread-row")).to_have_count(4)
expect(page.locator("#threads article.thread")).to_have_count(0)
expect(page.locator("#work-detail-pane")).to_be_visible()
expect(page.locator("#work-detail-empty")).to_be_visible()

page.locator("#threads .thread-row").first.click()
expect(page.locator("#work-detail-content")).to_be_visible()
expect(page.get_by_role("button", name="Bring to Now", exact=True)).to_be_visible()
```

Place this assertion before the smoke test creates the extra quick-capture thread so the seeded open-thread count remains four.

For the mobile page created in Task 1:

```python
mobile.get_by_role("button", name="My work", exact=True).click()
mobile.locator("#threads .thread-row").first.click()
expect(mobile.locator("#work-view")).to_have_class(re.compile(r"detail-open"))
expect(mobile.get_by_role("button", name="Back to work list", exact=True)).to_be_visible()
```

- [ ] **Step 2: Run browser smoke and verify the new My Work assertions fail**

Run:

```bash
uv run --with playwright python scripts/browser_smoke.py
```

Expected: failure because `.thread-row`, `#work-detail-pane`, and `.detail-open` do not exist.

- [ ] **Step 3: Recompose Now into a narrow focused work column without changing its data IDs**

Keep `#focus-panel`, `#focus-title`, `#next-card`, `#focus-session`, and focus-action IDs intact, but wrap the Now heading + focus panel in a `.now-column` and remove unrelated dashboard-style containers. Target structure:

```html
<section id="now-view" class="view now-view" aria-label="Now">
  <div class="now-column">
    <div class="view-heading now-heading">
      <h1>One thing at a time.</h1>
      <p>Choose one task. Everything else can wait.</p>
    </div>
    <section class="focus-surface" id="focus-panel" aria-labelledby="focus-title">
      <!-- move the existing focus toolbar/title/session/next-card controls here unchanged -->
    </section>
    <section id="now-reminders" class="reminder-strip" hidden></section>
  </div>
</section>
```

Use CSS:

```css
.now-view { padding-top: clamp(40px, 8vh, 88px); }
.now-column { width: min(100%, 840px); margin: 0 auto; }
.now-heading { margin-bottom: 24px; }
.focus-surface {
  padding: clamp(20px, 4vw, 32px);
  background: var(--surface);
  border: 1px solid var(--divider);
  border-radius: var(--radius-focus);
}
```

Do not add stats/rewards/project navigation to this screen.

- [ ] **Step 4: Add minimal inspected-thread UI state**

In `state.js`, add one field to the exported `state` object:

```js
inspectedThreadId: null,
```

Do not persist this to localStorage; a detail selection is transient UI state.

- [ ] **Step 5: Replace card rendering with dense task rows**

In `work.js`, keep the current filtering, project/source helpers, and thread count. Replace each large `<article class="thread">` with one scannable row button:

```js
const rowMarkup = (t) => {
  const isChosen = t.id === state.chosenId;
  const isInspected = t.id === state.inspectedThreadId;
  const statusLabel = t.status === "done"
    ? "Finished"
    : state.currentView === "stale" ? "Waiting" : "Ready";
  const continuity = t.resume_step || t.focus || t.progress_snippet || "";

  return `<button type="button"
      class="thread-row${isInspected ? " is-selected" : ""}"
      data-inspect="${escapeHtml(t.id)}"
      aria-pressed="${String(isInspected)}">
    <span class="thread-row-main">
      <strong>${escapeHtml(t.summary)}</strong>
      ${continuity ? `<span class="thread-row-context">${escapeHtml(continuity)}</span>` : ""}
    </span>
    <span class="thread-row-meta">
      <span>${escapeHtml(projectName(t.project_slug))}</span>
      <span>${escapeHtml(sourceName(t.source_tool || t.origin))}</span>
      <span>Updated ${escapeHtml(formatWhen(t.updated_at))}</span>
      <span class="status-label">${escapeHtml(statusLabel)}${isChosen ? " · In Now" : ""}</span>
    </span>
  </button>`;
};
```

Bind `[data-inspect]` to `inspectThread()` rather than immediately choosing the thread.

- [ ] **Step 6: Add one reusable detail pane instead of duplicating desktop/mobile details**

In `index.html`, make `.work-content` contain a list column plus one sibling detail pane:

```html
<div class="work-browser">
  <section class="work-list-pane" aria-label="Work list">
    <!-- keep the existing filters/search/count/#threads inside this pane -->
  </section>

  <aside id="work-detail-pane" class="work-detail-pane" aria-label="Selected work" tabindex="-1">
    <button type="button" class="text-button work-detail-back" id="btn-work-detail-back">Back to work list</button>
    <div id="work-detail-empty" class="work-detail-empty">
      <h2>Select a task</h2>
      <p class="hint">Its next step and context will appear here.</p>
    </div>
    <div id="work-detail-content" hidden></div>
  </aside>
</div>
```

Desktop CSS uses `grid-template-columns: minmax(0, 1fr) minmax(300px, 380px)`. At `max-width: 960px`, `.detail-open` hides the project/list regions and makes the same detail pane full width.

- [ ] **Step 7: Implement detail rendering and mobile Back behaviour**

Add these functions to `work.js`:

```js
export function renderThreadDetail(thread) {
  const empty = $("work-detail-empty");
  const content = $("work-detail-content");
  if (!thread) {
    empty.hidden = false;
    content.hidden = true;
    content.replaceChildren();
    return;
  }

  empty.hidden = true;
  content.hidden = false;
  const issue = thread.forge_issue_url
    ? `<a class="btn ghost compact" href="${safeLink(thread.forge_issue_url)}" target="_blank" rel="noopener">Open issue #${escapeHtml(thread.forge_issue_number)}</a>`
    : "";

  content.innerHTML = `
    <div class="work-detail-heading">
      <p class="meta">${escapeHtml(thread.project_slug || "Inbox")} · Updated ${escapeHtml(formatWhen(thread.updated_at))}</p>
      <h2>${escapeHtml(thread.summary)}</h2>
    </div>
    ${thread.focus ? `<section><h3>Focus</h3><p>${escapeHtml(thread.focus)}</p></section>` : ""}
    ${thread.blocked_reason ? `<section><h3>Blocked</h3><p>${escapeHtml(thread.blocked_reason)}</p></section>` : ""}
    ${thread.resume_step ? `<section><h3>Resume here</h3><p>${escapeHtml(thread.resume_step)}</p></section>` : ""}
    <details class="progress-details" data-notes="${escapeHtml(thread.id)}">
      <summary>Notes &amp; context</summary>
      <div class="markdown-body"></div>
    </details>
    <div class="actions">
      ${thread.status !== "done" ? `<button type="button" class="primary" data-detail-choose="${escapeHtml(thread.id)}">Bring to Now</button>` : ""}
      ${issue}
      <button type="button" class="ghost" data-detail-copy="${escapeHtml(thread.id)}">Copy link</button>
    </div>`;

  wireNotes(content);
  content.querySelector("[data-detail-choose]")?.addEventListener("click", () => chooseThread(thread.id));
  content.querySelector("[data-detail-copy]")?.addEventListener("click", () => copyReference(thread.id));
}

export function inspectThread(threadId) {
  state.inspectedThreadId = threadId;
  const thread = state.threadsCache.find((item) => item.id === threadId) || null;
  renderThreads(state.threadsCache);
  renderThreadDetail(thread);
  $("work-view").classList.add("detail-open");
  if (matchMedia("(max-width: 960px)").matches) {
    $("work-detail-pane").focus({ preventScroll: true });
  }
}

export function closeThreadDetail() {
  $("work-view").classList.remove("detail-open");
  const selected = state.inspectedThreadId;
  if (selected) {
    document.querySelector(`[data-inspect="${CSS.escape(selected)}"]`)?.focus();
  }
}
```

When project/filter changes, clear `state.inspectedThreadId`, remove `.detail-open`, and call `renderThreadDetail(null)`.

- [ ] **Step 8: Wire Back to list and ensure row selection survives list re-rendering**

In `boot.js` import `closeThreadDetail` and bind:

```js
$("btn-work-detail-back").addEventListener("click", closeThreadDetail);
```

In `renderThreads()`, after replacing row markup, re-apply selected state from `state.inspectedThreadId` and call `renderThreadDetail()` with the cached selected thread if it still exists. If search/filtering removes the selected thread, clear `state.inspectedThreadId`, remove `.detail-open`, and render the empty detail state.

- [ ] **Step 9: Add dense work-browser CSS**

Use flat rows with dividers, not cards:

```css
.work-browser {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 380px);
  gap: 24px;
  min-width: 0;
}

#threads { border-top: 1px solid var(--divider); }
.thread-row {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  min-height: 72px;
  padding: 14px 4px;
  text-align: left;
  color: var(--text);
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--divider);
  border-radius: 0;
}
.thread-row:hover { background: color-mix(in srgb, var(--surface-subtle) 65%, transparent); }
.thread-row.is-selected { background: var(--surface-subtle); }
.thread-row-main, .thread-row-meta { display: flex; flex-direction: column; gap: 4px; }
.thread-row-context, .thread-row-meta { color: var(--muted); font-size: .82rem; }
.work-detail-pane {
  align-self: start;
  padding-left: 24px;
  border-left: 1px solid var(--divider);
}
.work-detail-back { display: none; }

@media (max-width: 960px) {
  .work-browser { display: block; }
  .work-detail-pane { display: none; border-left: 0; padding-left: 0; }
  .work-view.detail-open .rail,
  .work-view.detail-open .work-list-pane,
  .work-view.detail-open .work-heading-row { display: none; }
  .work-view.detail-open .work-detail-pane { display: block; }
  .work-view.detail-open .work-detail-back { display: inline-flex; }
}
```

At the same `960px` breakpoint, replace the persistent project rail with a compact project/filter control using the existing project buttons inside a collapsible/drawer-style region; do not duplicate project state or add another project API.

- [ ] **Step 10: Run Now/My Work tests and commit**

Run:

```bash
graphify update .
uv run pytest
uv run ruff check src tests scripts
uv run --with playwright python scripts/browser_smoke.py
```

Commit:

```bash
git add src/adhd_hub/ui/index.html src/adhd_hub/ui/app.css src/adhd_hub/ui/js/state.js src/adhd_hub/ui/js/work.js src/adhd_hub/ui/js/boot.js scripts/browser_smoke.py
git commit -m "feat: redesign now and work browsing"
```

---

### Task 3: Rebalance Progress around activity and compact milestones

**Files:**
- Modify: `src/adhd_hub/ui/index.html`
- Modify: `src/adhd_hub/ui/app.css`
- Modify: `src/adhd_hub/ui/js/progress.js`
- Modify: `scripts/browser_smoke.py`

**Interfaces:**
- Consumes: current overview payload, `renderStats()`, `renderRewards()`, and share-card dialog/control IDs.
- Produces: activity-first Progress DOM, compact `#milestones` presentation, unchanged reward preference/share behaviour.

- [ ] **Step 1: Add failing smoke assertions for Progress hierarchy**

After enabling rewards and opening Progress, assert:

```python
expect(page.locator("#progress-summary")).to_be_visible()
expect(page.locator("#chart-wrap")).to_be_visible()
expect(page.locator("#milestones")).to_be_visible()
expect(page.locator("#rank-name")).to_be_visible()
expect(page.locator("#badges .badge").first).to_be_visible()
```

Also verify activity precedes milestones in DOM order:

```python
assert page.evaluate("""
  () => {
    const activity = document.querySelector('#activity-section');
    const milestones = document.querySelector('#milestones');
    return Boolean(activity && milestones && (activity.compareDocumentPosition(milestones) & Node.DOCUMENT_POSITION_FOLLOWING));
  }
""")
```

- [ ] **Step 2: Run browser smoke and confirm Progress assertions fail**

Run:

```bash
uv run --with playwright python scripts/browser_smoke.py
```

Expected: failure because the new section IDs do not exist.

- [ ] **Step 3: Recompose Progress HTML without changing data-control IDs**

Use this hierarchy:

```html
<section id="progress-view" class="view progress-view" aria-label="Progress" hidden>
  <div class="view-heading progress-heading">
    <h1>Progress, at your pace.</h1>
    <p>See what moved forward. Quiet days count too.</p>
  </div>

  <section id="progress-summary" class="progress-summary" aria-label="Progress summary">
    <div class="stats" id="stats"></div>
  </section>

  <section id="activity-section" class="progress-section" aria-labelledby="activity-title">
    <div class="section-heading">
      <h2 id="activity-title">Recent activity</h2>
      <p class="hint">Added and finished work over the last 14 days.</p>
    </div>
    <div class="chart-wrap" id="chart-wrap" hidden>
      <p id="chart-summary" class="visually-hidden"></p>
      <div class="chart" id="chart"></div>
    </div>
  </section>

  <section id="milestones" class="progress-section milestones" aria-labelledby="rewards-title" hidden>
    <!-- move the existing rank/goal/badge/share controls here and retain
         rank-name, reward-level, rank-next, rank-progress, goal-count,
         daily-progress, badge-count, badges, btn-share-progress and
         rewards-caption IDs -->
  </section>
  <p id="rewards-off" class="hint"></p>
</section>
```

Keep all IDs referenced by `progress.js` so calculations/preferences/share behaviour stay intact.

- [ ] **Step 4: Update `renderRewards()` and every old `#rewards-panel` reference consistently**

Rename the container lookup from `rewards-panel` to `milestones`; do not change the XP/badge model:

```js
export function renderRewards() {
  const enabled = $("rewards-enabled").checked;
  $("milestones").hidden = !enabled;
  $("rewards-off").hidden = enabled;
  $("daily-goal").disabled = !enabled;
  // keep the existing total/today/goal/rewards calculations below this point
}
```

Then search the branch for `rewards-panel` and update all remaining presentation/test references in this task, including:

- `scripts/browser_smoke.py` hidden/visible assertions
- `src/adhd_hub/ui/app.css` focus-mode selectors or legacy reward selectors
- `src/adhd_hub/ui/index.html`

Do not leave a compatibility duplicate `id="rewards-panel"`; one canonical container is easier to reason about.

Keep `openSharePreview()` and its privacy constraints intact. Do not redesign share-card data semantics in this PR.

- [ ] **Step 5: Style Progress as flat analytical content with compact badges**

```css
.progress-view { width: min(100%, 1040px); margin: 0 auto; }
.progress-summary {
  padding: 20px 0 24px;
  border-bottom: 1px solid var(--divider);
}
.progress-section { padding: 28px 0; border-bottom: 1px solid var(--divider); }
.progress-section:last-child { border-bottom: 0; }
.stats { display: flex; flex-wrap: wrap; gap: 28px; }
.stat { min-width: 120px; text-align: left; }
.stat strong { display: block; font-size: clamp(1.5rem, 3vw, 2rem); color: var(--text); }
.milestones .rank-hero { display: grid; grid-template-columns: 1fr auto; gap: 20px; }
#badges { display: flex; flex-wrap: wrap; gap: 8px; padding: 0; list-style: none; }
.badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--divider);
  border-radius: 999px;
  background: transparent;
}
.badge:not(.earned) { color: var(--muted); }
.badge.earned { color: var(--gold); }
```

On mobile, stack summary metrics and milestone rank content without horizontal overflow.

- [ ] **Step 6: Run Progress flow + full tests and commit**

Run:

```bash
graphify update .
uv run pytest
uv run ruff check src tests scripts
uv run --with playwright python scripts/browser_smoke.py
```

Commit:

```bash
git add src/adhd_hub/ui/index.html src/adhd_hub/ui/app.css src/adhd_hub/ui/js/progress.js scripts/browser_smoke.py
git commit -m "feat: make progress activity first"
```

---

### Task 4: Redesign Settings, dialogs, and mobile Settings navigation

**Files:**
- Modify: `src/adhd_hub/ui/index.html`
- Modify: `src/adhd_hub/ui/app.css`
- Modify: `src/adhd_hub/ui/js/settings.js`
- Modify: `src/adhd_hub/ui/js/boot.js`
- Modify: `scripts/browser_smoke.py`

**Interfaces:**
- Consumes: existing `[data-settings-tab]`, `aria-controls`, panel IDs, settings save/load functions, and dialog IDs.
- Produces: `showSettingsIndex()`, mobile Back-to-settings behaviour, constrained settings content column, unchanged desktop keyboard tab semantics.

- [ ] **Step 1: Add failing browser-smoke assertions for the new Settings structure**

On desktop:

```python
page.get_by_role("button", name="Settings", exact=True).click()
expect(page.locator(".settings-shell")).to_be_visible()
expect(page.locator(".settings-content-inner")).to_be_visible()
expect(page.locator(".settings-content-inner")).to_have_css("max-width", "840px")
```

On mobile:

```python
mobile.get_by_role("button", name="Settings", exact=True).click()
expect(mobile.locator("#settings-view")).to_have_class(re.compile(r"settings-index-open"))
expect(mobile.get_by_role("button", name="Preferences", exact=True)).to_be_visible()
mobile.get_by_role("button", name="Preferences", exact=True).click()
expect(mobile.get_by_role("button", name="Back to settings", exact=True)).to_be_visible()
```

- [ ] **Step 2: Run browser smoke and confirm Settings assertions fail**

Run:

```bash
uv run --with playwright python scripts/browser_smoke.py
```

Expected: failure because `.settings-shell`, `.settings-content-inner`, and the mobile settings index state do not yet exist.

- [ ] **Step 3: Recompose Settings HTML while preserving existing panel/control IDs**

Use this shell:

```html
<section id="settings-view" class="view settings-view" aria-label="Settings" hidden>
  <div class="view-heading settings-heading">
    <h1>Settings</h1>
    <button type="button" class="ghost" id="btn-close-settings">Close</button>
  </div>

  <div class="settings-shell">
    <nav class="settings-nav" aria-label="Settings categories" role="tablist" aria-orientation="vertical">
      <!-- move the existing data-settings-tab buttons / aria-controls here unchanged -->
    </nav>

    <div class="settings-content">
      <button type="button" class="text-button settings-mobile-back" id="btn-settings-index-back">Back to settings</button>
      <div class="settings-content-inner">
        <!-- move the existing settings panels here unchanged -->
      </div>
    </div>
  </div>
</section>
```

Remove decorative settings eyebrow/hero copy that does not explain a setting. Keep descriptions that explain consequences/security.

- [ ] **Step 4: Add mobile settings-index state without breaking desktop tab keyboard behaviour**

In `settings.js` add:

```js
export function showSettingsIndex() {
  const view = $("settings-view");
  view.classList.add("settings-index-open");
  document.querySelector("#settings-view h1")?.focus({ preventScroll: true });
}
```

Keep the existing `selectSettingsTab()` selection/panel logic, but add this line once a valid tab is chosen:

```js
$("settings-view")?.classList.remove("settings-index-open");
```

When Settings opens, use the index only at mobile width:

```js
if (matchMedia("(max-width: 760px)").matches) showSettingsIndex();
else selectSettingsTab("preferences");
```

Bind `#btn-settings-index-back` to `showSettingsIndex()`.

- [ ] **Step 5: Preserve Settings keyboard navigation on desktop**

Keep the existing ArrowUp/ArrowDown/ArrowLeft/ArrowRight/Home/End handler. Add a mobile guard before the arrow-key logic:

```js
if (matchMedia("(max-width: 760px)").matches && event.key.startsWith("Arrow")) return;
```

On mobile, normal Tab/Enter activation is enough; do not create a horizontally scrolling tab pattern.

- [ ] **Step 6: Add constrained Settings + mobile CSS**

```css
.settings-view { width: min(100%, 1180px); margin: 0 auto; }
.settings-shell {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 40px;
}
.settings-nav {
  align-self: start;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.settings-content-inner { max-width: 840px; }
.settings-panel { padding: 0; background: transparent; border: 0; box-shadow: none; }
.settings-panel > section { padding: 20px 0; border-bottom: 1px solid var(--divider); }
.settings-mobile-back { display: none; }

@media (max-width: 760px) {
  .settings-shell { display: block; }
  .settings-nav { display: none; }
  .settings-content { display: block; }
  .settings-view.settings-index-open .settings-nav { display: flex; }
  .settings-view.settings-index-open .settings-content { display: none; }
  .settings-mobile-back { display: inline-flex; margin-bottom: 16px; }
  .settings-nav [role="tab"] { width: 100%; justify-content: space-between; min-height: 48px; }
}
```

- [ ] **Step 7: Standardize dialog visual treatment without changing dialog behaviour**

Use one shared dialog rule in `app.css`:

```css
dialog {
  width: min(calc(100vw - 32px), 560px);
  max-height: min(86dvh, 760px);
  padding: 0;
  color: var(--text);
  background: var(--surface-elevated);
  border: 1px solid var(--divider);
  border-radius: 14px;
  box-shadow: var(--shadow-elevated);
}
dialog::backdrop { background: rgb(0 0 0 / .48); }
.dialog-body { padding: 24px; }
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 24px;
  border-top: 1px solid var(--divider);
}
```

Adapt existing dialog wrappers/classes to `.dialog-body` / `.dialog-actions` where the markup already has a clear content/action split. Keep all current submit/cancel IDs and focus-return code.

- [ ] **Step 8: Run Settings/dialog/mobile tests and commit**

Run:

```bash
graphify update .
uv run pytest
uv run ruff check src tests scripts
uv run --with playwright python scripts/browser_smoke.py
```

Commit:

```bash
git add src/adhd_hub/ui/index.html src/adhd_hub/ui/app.css src/adhd_hub/ui/js/settings.js src/adhd_hub/ui/js/boot.js scripts/browser_smoke.py
git commit -m "feat: redesign settings and mobile navigation"
```

---

### Task 5: Redesign Zensical docs navigation, homepage, and visual system

**Files:**
- Modify: `tests/test_documentation.py`
- Modify: `zensical.toml`
- Modify: `docs/index.md`
- Modify: `docs/stylesheets/extra.css`
- Create: `scripts/docs_browser_smoke.py`

**Interfaces:**
- Consumes: current Zensical config and existing docs pages.
- Produces: four-category docs IA, ~72ch prose measure, flat shared palette, automated docs render smoke screenshots.

- [ ] **Step 1: Add failing documentation navigation tests**

Extend `tests/test_documentation.py`:

```python
def test_docs_nav_uses_reader_focused_sections() -> None:
    nav = (REPO_ROOT / "zensical.toml").read_text(encoding="utf-8")
    for heading in ["Start here", "Using the Hub", "Deploy & configure", "Project"]:
        assert f'"{heading}"' in nav
    assert '"Guides"' not in nav
    assert '"Plans"' not in nav


def test_docs_homepage_has_direct_start_actions() -> None:
    text = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    assert "[Install](installation.md)" in text
    assert "[Connect an agent](connect.md)" in text
    assert "Work → Save continuity → Leave → Come back → Resume" in text
```

- [ ] **Step 2: Run documentation tests and confirm they fail**

Run:

```bash
uv run pytest tests/test_documentation.py -v
```

Expected: new IA/homepage assertions fail.

- [ ] **Step 3: Reorganize `zensical.toml` navigation without inventing nonexistent docs**

Use only current pages. Map them into the agreed IA:

```toml
nav = [
  { "Start here" = [
    { "What is ADHD Progress Hub?" = "index.md" },
    { "Installation" = "installation.md" },
    { "Connect your coding agent" = "connect.md" },
    { "First project / personal setup" = "setup.md" },
    { "First continuity session" = "project-agent-setup.md" },
    { "Writing and planning" = "writing.md" },
    { "Coding companions" = "coding-companions.md" },
  ]},
  { "Using the Hub" = [
    { "Dashboard" = "dashboard.md" },
    { "GitHub / Gitea" = "forge-issue-inbox.md" },
    { "OpenClaw" = "openclaw.md" },
    { "Rewards" = "rewards-roadmap.md" },
  ]},
  { "Deploy & configure" = [
    { "Homelab / Docker" = "deploy-homelab.md" },
    { "Authentication" = "authentication.md" },
    { "Environment variables" = "environment-variables.md" },
    { "Forge permissions" = "forge-permissions.md" },
    { "Indexer schedule" = "indexer-schedule.md" },
  ]},
  { "Project" = [
    { "Improvement roadmap" = "plans/improvement-roadmap.md" },
    { "ADHD Hub foundation" = "plans/adhd-hub-foundation.md" },
    { "Projects CRUD revamp" = "plans/projects-crud-ui-revamp.md" },
    { "Brand guide" = "brand-guide.md" },
    { "Review improvements" = "review-improvements.md" },
  ]},
]
```

Do not create placeholder docs such as `reminders.md` solely to satisfy the conceptual IA. Existing functionality can be linked from Dashboard/Connect until a dedicated guide actually exists.

- [ ] **Step 4: Rewrite `docs/index.md` into a concise start page**

Use this exact content structure and keep wording short:

```markdown
# ADHD Progress Hub

Keep enough context to resume unfinished work without reconstructing your last session.

[Install](installation.md) · [Connect an agent](connect.md) · [View GitHub](https://github.com/uniskela/adhd-hub)

Self-hosted · MCP + REST · Cursor, Codex, Claude Code and other MCP clients · GitHub/Gitea optional

## How it works

**Work → Save continuity → Leave → Come back → Resume**

1. Start or resume one finishable outcome.
2. Save the current focus, next steps, blockers, and one concrete return cue.
3. Step away without keeping the whole session in your head.
4. Let your next coding agent/session read the compact continuity summary before it starts more work.

## Start here

- [Install the Hub](installation.md)
- [Connect an agent](connect.md)
- [Set up your first project](setup.md)
- [Add project continuity guidance](project-agent-setup.md)
- [Use the dashboard](dashboard.md)

## Run it your way

Use Docker/Compose, `uv`, or a homelab deployment. Keep it local, behind Tailscale, or behind your own authenticated reverse proxy.

- [Homelab deployment](deploy-homelab.md)
- [Authentication](authentication.md)
- [Environment variables](environment-variables.md)
```

- [ ] **Step 5: Replace glossy docs CSS with the shared semantic palette and constrained reading width**

Start `docs/stylesheets/extra.css` with the approved tokens:

```css
:root > * {
  --hub-canvas: #f7f6f1;
  --hub-surface: #ffffff;
  --hub-subtle: #eff1ec;
  --hub-text: #20332c;
  --hub-muted: #617069;
  --hub-divider: #d7ddd8;
  --hub-accent: #176b60;
  --hub-gold: #b18430;
  --md-primary-fg-color: #ffffff;
  --md-accent-fg-color: var(--hub-accent);
  --md-typeset-a-color: var(--hub-accent);
}

[data-md-color-scheme="slate"] {
  --hub-canvas: #0d1210;
  --hub-surface: #151d19;
  --hub-subtle: #172a24;
  --hub-text: #e7eeea;
  --hub-muted: #98a89f;
  --hub-divider: #2a3731;
  --hub-accent: #7acdb6;
  --hub-gold: #ddbb68;
  --md-default-bg-color: var(--hub-canvas);
  --md-default-fg-color: var(--hub-text);
  --md-default-fg-color--light: var(--hub-muted);
  --md-accent-fg-color: var(--hub-accent);
  --md-typeset-a-color: var(--hub-accent);
}
```

Use a normal documentation grid and constrain prose rather than forcing the whole site full width:

```css
.md-grid { max-width: 1440px; }
.md-content__inner { max-width: 72ch; margin-inline: auto; }
.md-typeset table,
.md-typeset .highlight,
.md-typeset pre,
.md-typeset .mermaid { max-width: min(100%, 1100px); }

.md-header {
  background: var(--hub-canvas);
  color: var(--hub-text);
  border-bottom: 1px solid var(--hub-divider);
  box-shadow: none;
}
.md-tabs { background: var(--hub-canvas); border-bottom: 1px solid var(--hub-divider); backdrop-filter: none; }
.md-nav__link--active { color: var(--hub-accent); font-weight: 650; }
[data-md-color-scheme="slate"] .md-nav__link--active {
  background: transparent;
  box-shadow: inset 2px 0 0 var(--hub-accent);
  border-radius: 0;
  padding-left: .65rem;
}
```

Delete the current glossy header gradients, glow, `backdrop-filter`, and full-viewport `.md-grid` override.

- [ ] **Step 6: Add a focused Playwright docs smoke script**

Create `scripts/docs_browser_smoke.py` that builds docs, serves `site/`, and captures desktop/mobile screenshots:

```python
from __future__ import annotations

import http.server
import os
from pathlib import Path
import socket
import subprocess
import threading

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SCREENSHOTS = Path(os.environ.get("ADHD_HUB_DOCS_SCREENSHOT_DIR", "/tmp/adhd-hub-docs-preview"))


def main() -> None:
    subprocess.run(["uv", "run", "zensical", "build"], cwd=ROOT, check=True)
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    def handler(*args, **kwargs):
        return http.server.SimpleHTTPRequestHandler(*args, directory=str(SITE), **kwargs)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox"])
            desktop = browser.new_page(viewport={"width": 1440, "height": 1000})
            desktop.goto(f"http://127.0.0.1:{port}/")
            expect(desktop.get_by_role("heading", name="ADHD Progress Hub", exact=True)).to_be_visible()
            expect(desktop.get_by_role("link", name="Install", exact=True)).to_be_visible()
            desktop.screenshot(path=str(SCREENSHOTS / "docs-home-desktop.png"), full_page=True)

            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            mobile.goto(f"http://127.0.0.1:{port}/")
            expect(mobile.get_by_role("heading", name="ADHD Progress Hub", exact=True)).to_be_visible()
            mobile.screenshot(path=str(SCREENSHOTS / "docs-home-mobile.png"), full_page=True)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run docs tests/build/smoke and commit**

Run:

```bash
graphify update .
uv run pytest tests/test_documentation.py -v
uv run zensical build
uv run --with playwright python scripts/docs_browser_smoke.py
uv run ruff check src tests scripts
```

Commit:

```bash
git add tests/test_documentation.py zensical.toml docs/index.md docs/stylesheets/extra.css scripts/docs_browser_smoke.py
git commit -m "feat: redesign documentation experience"
```

---

### Task 6: Final responsive/accessibility verification and PR polish

**Files:**
- Modify: `scripts/browser_smoke.py`
- Modify only for verified defects: `src/adhd_hub/ui/app.css`
- Modify only for verified defects: `src/adhd_hub/ui/index.html`
- Modify only for verified defects: focused files under `src/adhd_hub/ui/js/`
- Modify only for verified defects: `docs/stylesheets/extra.css`

**Interfaces:**
- Consumes: all completed redesign surfaces.
- Produces: final screenshot matrix, keyboard/mobile assertions, clean full test suite, PR-ready branch.

- [ ] **Step 1: Expand dashboard smoke coverage to the required screenshot matrix**

Capture deterministic screenshots with reduced motion:

```python
page.emulate_media(color_scheme="dark", reduced_motion="reduce")
page.screenshot(path=str(screenshots / "now-dark-desktop.png"), full_page=True, animations="disabled")

page.get_by_role("button", name="My work", exact=True).click()
page.locator("#threads .thread-row").first.click()
page.screenshot(path=str(screenshots / "work-detail-dark-desktop.png"), full_page=True, animations="disabled")

page.get_by_role("button", name="Progress", exact=True).click()
page.screenshot(path=str(screenshots / "progress-dark-desktop.png"), full_page=True, animations="disabled")

page.get_by_role("button", name="Settings", exact=True).click()
page.screenshot(path=str(screenshots / "settings-dark-desktop.png"), full_page=True, animations="disabled")
```

Repeat representative Now/My Work/Settings screenshots on the 390×844 mobile page in both light and dark modes. Do not add screenshot files to git; they remain test artifacts under `/tmp` unless the repository already has a documented snapshot policy.

- [ ] **Step 2: Add explicit keyboard/focus assertions**

Verify destination heading focus after navigation:

```python
page.get_by_role("button", name="Progress", exact=True).click()
expect(page.locator("#progress-view h1")).to_be_focused()
```

Verify the visual focus treatment is not a giant generic outline by checking computed style:

```python
focus_style = page.locator("#progress-view h1").evaluate("""
  (el) => ({
    outline: getComputedStyle(el).outlineStyle,
    boxShadow: getComputedStyle(el).boxShadow,
  })
""")
assert focus_style["outline"] == "none"
assert focus_style["boxShadow"] != "none"
```

Verify dialogs still return focus to their opener using the existing share/capture/settings assertions.

- [ ] **Step 3: Add explicit mobile-nav content-spacing assertion**

On mobile, verify the final page content is not hidden beneath the fixed nav:

```python
assert mobile.evaluate("""
  () => {
    const nav = document.querySelector('.mobile-nav').getBoundingClientRect();
    const shell = document.querySelector('.shell');
    const paddingBottom = parseFloat(getComputedStyle(shell).paddingBottom);
    return paddingBottom >= nav.height;
  }
""")
```

If this fails, fix only the bottom padding/safe-area rule; do not redesign navigation again.

- [ ] **Step 4: Run the entire verification suite**

Run in this order:

```bash
graphify update .
uv run pytest
uv run ruff check src tests scripts
uv run zensical build
uv run --with playwright python scripts/browser_smoke.py
uv run --with playwright python scripts/docs_browser_smoke.py
```

Expected: all commands exit 0.

- [ ] **Step 5: Inspect generated screenshots manually for the acceptance criteria**

Check at minimum:

- no permanent Appearance strip above the header
- no decorative page gradients/glow/blur
- Now is centred and intentional rather than floating left in dead space
- My Work shows dense rows and a stable detail pane on desktop
- mobile My Work uses a full-width detail state with Back to work list
- Progress activity appears before Milestones
- Settings content does not stretch past ~840px
- mobile bottom nav does not cover content
- focused page headings show a small accent marker rather than a full mint rectangle
- docs prose is approximately 72ch and side navigation/header remain visually restrained
- light theme remains warm/ivory rather than a generic stark-white GitHub clone

If a screenshot violates one of these, make the smallest CSS/markup correction and rerun the affected smoke test.

- [ ] **Step 6: Compare the branch against main and verify scope isolation**

Run:

```bash
git diff --stat origin/main...HEAD
git diff --name-only origin/main...HEAD
```

Expected changed areas are limited to:

```text
src/adhd_hub/ui/
docs/
zensical.toml
scripts/browser_smoke.py
scripts/docs_browser_smoke.py
tests/test_documentation.py
```

The design/plan files under `docs/superpowers/` are also expected. Any model/store/forge/MCP/backend changes require removal or explicit explanation before PR creation.

- [ ] **Step 7: Run repository review tooling and create the PR**

Run the repository's required review flow (including `/review-bugbot` where available) and fix only findings relevant to this redesign.

Create a PR from `feat/ui-docs-redesign` to `main` with a title such as:

```text
feat: redesign dashboard and documentation UX
```

PR body:

```markdown
## Summary
- replaces the glossy/card-heavy dashboard shell with a flatter Progress Hub design system
- redesigns Now, My Work, Progress, Settings, dialogs, and responsive/mobile navigation
- makes My Work dense/scannable with a selected-task detail experience
- rebalances Progress toward activity before optional rewards
- redesigns the Zensical docs around a restrained ~72ch technical-reading layout and clearer navigation

## Behaviour preserved
- no backend, schema, forge, source-sync, MCP, auth, persistence, or PWA contract changes
- existing project/thread/Now/reward/settings flows remain supported

## Verification
- `uv run pytest`
- `uv run ruff check src tests scripts`
- `uv run zensical build`
- `uv run --with playwright python scripts/browser_smoke.py`
- `uv run --with playwright python scripts/docs_browser_smoke.py`

## Screenshots
Attach representative dark desktop + mobile screenshots for Now, My Work, Progress, Settings, and docs before merge.
```

Do not close Foundation B issues from this PR.

---

## Final Self-Review Checklist

Before calling the implementation complete:

- Every design-spec requirement maps to one of Tasks 1–6.
- The palette addendum is represented in both app and docs semantic tokens.
- No placeholder/new backend work was introduced.
- My Work detail selection is UI-only state and does not mutate a thread until the user explicitly chooses/acts.
- Mobile Settings and My Work each have an explicit Back path.
- Existing screen heading focus movement remains intact.
- Every former `#rewards-panel` reference is migrated to the canonical `#milestones` container.
- The full suite, dashboard smoke, docs build, and docs smoke all pass.
- Generated screenshots were visually inspected rather than trusting CSS assertions alone.
