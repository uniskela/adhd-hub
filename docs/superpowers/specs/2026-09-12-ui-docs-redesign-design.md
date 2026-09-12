# UI and documentation redesign

Date: 2026-09-12
Branch: `feat/ui-docs-redesign`
Status: Approved design, implementation not started

## Goal

Redesign the ADHD Progress Hub dashboard (`/ui`) and public documentation/wiki so they feel deliberately designed, calm, information-first, and consistent with the product's ADHD-friendly purpose.

This is not a cosmetic reskin. It changes visual hierarchy and presentation while preserving product behaviour, API/MCP semantics, authentication, persistence, and Foundation B data-model work.

The redesign should remove the current card-heavy/glossy appearance, improve information density where scanning matters, reduce visual competition, and make the docs read like technical documentation rather than an application dashboard.

## Product principles

1. **Immediate work wins attention.** Current task, next action, and resume cue are more prominent than secondary metadata, rewards, or configuration.
2. **Progressive disclosure.** Show the minimum information needed for the current decision. History, long notes, technical metadata, and advanced configuration stay available without dominating the default view.
3. **Whitespace before containers.** Prefer spacing, alignment, typography, and dividers before adding bordered/tinted surfaces.
4. **Calm, not empty.** Empty space should support focus; avoid large accidental dead regions on wide displays.
5. **Dense where scanning matters.** Work lists should support quickly scanning many threads without turning each one into a mini-dashboard.
6. **No productivity shame.** Rewards/statistics are optional reflection tools, not the primary framing of progress.
7. **Accessible by default.** Keyboard focus, screen-reader semantics, reduced motion, touch targets, contrast, and responsive behaviour remain first-class.
8. **One visual language, two contexts.** `/ui` and docs share tokens, typography, logo, and brand relationships, while the dashboard remains application-like and docs remain editorial.

## Non-goals

- No Thread/Project schema changes.
- No Foundation B source/authority, forge reconciliation, or MCP behaviour changes.
- No #72 statistics implementation.
- No #75 event/SSE implementation.
- No rewrite of every documentation page.
- No frontend framework migration.
- No React/Vue/Svelte introduction solely for the redesign.
- No generic glassmorphism, decorative gradients, or widespread blur effects.
- No removal of keyboard focus indicators.

## Current-state problems

### Dashboard

Most top-level sections use the same visual recipe: translucent background, rounded border, large radius, shadow, and blur. This makes unrelated content appear equally important and gives the product a generated-dashboard appearance.

The standalone Appearance strip above the application header creates two competing top-level bars. Content also uses the full viewport even where the useful content is narrow, producing large dead regions on wide screens.

The primary screens need different density:

- **Now** is conceptually simple but currently occupies a large left-aligned surface with excessive unused space.
- **My Work** renders thread items too prominently, making long lists slow to scan.
- **Progress** gives rewards/gamification more visual weight than activity/reflection.
- **Settings** stretches forms too widely and wraps configuration in oversized surfaces.

SPA navigation correctly moves focus to the new screen heading. The global focus styling then makes the focused `h1` look like a large selected box. Keep the focus movement; fix the heading-specific visual treatment.

### Documentation/wiki

Zensical already provides sound foundations: search, navigation, light/dark palettes, code rendering, and repository integration. The custom stylesheet pushes it toward glossy application chrome with gradients, glow, blur, and full-width prose.

That conflicts with the brand-guide direction to prefer whitespace/alignment/dividers before extra containers and to avoid gradients/glow in the identity.

Long-form documentation also needs a constrained reading measure.

## Visual system

### Colour

Keep the existing Progress Hub palette and relationships:

- ivory / deep forest canvas
- white / forest surfaces
- ink / pale-sage text
- teal / mint primary accent
- gold used sparingly for milestones
- berry / rose for destructive actions

Accent colour indicates action, selection, focus, or meaningful state. It is not general decoration.

### Typography

Keep the local system sans-serif stack. Build hierarchy using size, weight, line height, and spacing rather than background treatments.

- Page headings: clear, not oversized.
- Section headings: compact and consistent.
- Labels/metadata: visibly secondary.
- Long-form notes/docs: comfortable line length and line height.
- Eyebrow/all-caps labels: rare landmarks only.

### Spacing and surfaces

Use the established 4/8/12/16/24/32 spacing rhythm.

Ordinary grouped surfaces and controls use roughly 8–10px radii. The primary Now focus surface and dialogs may use larger soft corners where that distinction is useful.

Ordinary page sections should be flat. Use whitespace, subtle surface contrast, or dividers. Reserve shadows for dialogs, popovers, and actual elevation.

Remove backdrop blur and decorative gradients from normal dashboard/docs surfaces.

## Application shell

Replace the separate Appearance strip + header with a single application header.

Desktop header:

- Progress Hub brand/logo
- Now / My Work / Progress navigation
- Save a thought
- Settings
- one compact **Appearance button** at the far edge

The Appearance button opens a small three-option System / Light / Dark popover. The full Appearance setting also remains in Settings. This preserves quick switching without a second permanent toolbar.

On mobile, theme selection lives in Settings only; the compact header Appearance button is hidden to preserve space.

The main content uses screen-specific max widths rather than a single full-width layout:

- Now: narrow centred work column.
- My Work: wide workspace for project rail + work list + detail pane.
- Progress: medium-wide content/analysis column.
- Settings: wider shell with a constrained form column.

The application header is **not sticky** in this redesign. Avoid consuming persistent vertical space; revisit only if real usage demonstrates a need.

## Now screen

### Purpose

Answer only:

1. What am I doing?
2. What is the next useful action?
3. Where can I leave this so I can resume later?

### Empty state

Use a centred working area around 760–900px max width.

Show:

- `One thing at a time.`
- concise helper copy such as `Choose one task. Everything else can wait.`
- primary action: Choose a task
- secondary action: Help me choose

Do not show unrelated stats, rewards, project lists, or dashboard widgets.

### Active state

Show:

- project/source as quiet metadata
- task title
- prominent next step / resume cue
- Focus / Blocked / Resume context beneath
- compact action group: Start/Resume, Pause here, Done
- focus timer controls as secondary controls
- notes/history/details collapsed by default

The active task may use one intentional focus surface. It is one of the few places where a larger rounded container is justified.

## My Work screen

### Purpose

Support scanning, filtering, choosing, and inspecting many work items quickly.

### Desktop layout

Use three regions:

1. **Projects/filter rail** — compact and scannable.
2. **Work list** — dense task rows.
3. **Selected-task detail pane** — right side on sufficiently wide viewports.

Do not render every thread as a large card.

Default row content:

- task title
- project
- source/provider when relevant
- continuity/status state
- last-updated cue
- at most one secondary continuity line such as Focus or Resume

Rows use dividers and a restrained selected state, not heavy card chrome.

Selecting a row updates the right-side detail pane without navigating away from the list.

### Medium/mobile task details

When the desktop detail pane no longer fits, selecting a work item opens a **dedicated full-width task-detail view** with an explicit Back to work list action. Do not use inline expansion; it makes dense lists harder to scan and creates unstable vertical position.

### Projects rail

Keep project navigation but reduce button weight. `New project` remains available without competing visually with task content. Archived projects stay progressively disclosed.

### Tabs/search

Open / Pick up later / Finished remain clear filters. Search stays close to the work list and should not consume a large vertical panel.

## Progress screen

### Purpose

Answer: `What progress have I made lately?` without framing inactivity as failure.

### Primary hierarchy

1. concise activity summary
2. activity history/chart
3. optional milestones/rewards

Existing useful summary metrics such as finished-this-week/open work may remain. The existing 14-day activity view should have more visual weight than rewards when rewards are enabled.

Structure the screen so later #72 additions can fit naturally:

- activity heatmap
- tracked focus time
- daily/weekly/monthly completions
- project breakdowns

### Rewards

Rewards remain opt-in.

Replace oversized rank/badge presentation with a compact **Milestones** section:

- current rank/level/XP
- concise progress-to-next-rank indicator
- compact badge list/chips
- existing share action

Rewards are one interpretation of progress, not the screen's visual identity.

## Settings

### Desktop

Keep the existing category model but present it as a proper preferences layout.

Use a left settings navigation and a main settings column capped around 720–840px.

Categories continue to cover existing areas such as:

- Preferences
- Account
- Connections
- Forge
- Data

Within a category:

- normal section headings
- short consequence-oriented descriptions
- dividers/spacing instead of nested cards
- provider/connection status as compact labelled rows
- destructive/data actions clearly separated
- version/repository information in a quiet footer/meta region

Remove decorative copy that does not help configure the product.

### Appearance

System / Light / Dark remains a full setting here. The desktop header popover is only a convenience shortcut and writes the same preference.

## Dialogs

Dialogs are one of the few places where elevation/shadow is appropriate.

Standardise around:

- clear title
- concise explanation only when needed
- focused content
- logical action row
- one clear primary action per group
- explicit destructive styling
- visible close/cancel behaviour
- Escape handling and focus return preserved

Avoid explanatory sub-panels unless they materially reduce risk/confusion.

## Responsive/mobile behaviour

Mobile is a distinct composition, not compressed desktop.

### Navigation

On narrow screens use a fixed **bottom navigation** with four destinations:

- Now
- My Work
- Progress
- Settings

It must respect safe-area insets, preserve at least 44px touch targets, and add enough bottom content padding that it never obscures page controls/content.

The top mobile header becomes brand/context + Save thought/overflow actions rather than duplicating the primary destination navigation.

### Now

- full-width work surface
- no horizontal action overflow
- focus timer controls collapse/wrap cleanly

### My Work

- projects become a project/filter drawer or compact picker
- work list stays dense and single-column
- selected work item opens the dedicated full-width task-detail view described above

### Progress

- summary metrics stack/wrap cleanly
- charts remain readable
- future heatmap should prefer responsive cell sizing before horizontal scrolling
- rewards remain below activity

### Settings

Use a mobile settings index. Selecting a category opens that category as a full-width settings view with Back to settings. Do not use a horizontally scrolling tab bar.

## Accessibility

Preserve and improve:

- 44px minimum touch targets where applicable
- visible keyboard focus
- semantic current/selected state
- programmatic screen-heading focus after SPA navigation
- focus return after dialogs/settings
- reduced-motion support
- colour-independent state cues
- usable contrast in both themes
- keyboard-operable settings navigation
- screen-reader-friendly labels/status messages

### Page-heading focus

Keep focus transfer to `h1[tabindex="-1"]` after screen changes. Give those headings a dedicated focus presentation, for example a short accent underline/left marker plus outline-offset treatment that remains clearly visible but does not box the entire heading like a form control.

Do not suppress focus with `outline: none` without an equivalent visible replacement.

## Documentation/wiki redesign

### Visual direction

The docs should feel like technical documentation, not a glossy dashboard.

Retain Zensical and the existing content system.

Remove/reduce:

- glossy gradient headers
- glow
- backdrop blur
- decorative chrome
- unnecessarily full-width prose
- heavy active-state boxes

Use:

- flat header/navigation
- restrained brand teal/mint
- strong typography hierarchy
- article measure of approximately **72ch** for ordinary prose
- wider breakout treatment only for tables, diagrams, and code where genuinely useful
- clean code/admonition styling
- clear active navigation
- purposeful vertical rhythm

### Information architecture

Reorganise navigation as:

**Start here**
- What is ADHD Progress Hub?
- Installation
- Connect your coding agent
- First project / personal setup
- First continuity session

**Using the Hub**
- Dashboard
- Projects & threads
- MCP/agent workflow
- GitHub/Gitea
- Reminders
- OpenClaw
- Backups/data

**Deploy & configure**
- Docker/homelab
- Authentication
- Environment variables
- Reverse proxy/Tailscale
- Forge permissions

**Project**
- Architecture/plans
- Roadmap
- Contributing
- Brand/design

Do not rewrite every page. Change navigation labels/placement and targeted landing-page copy where needed for the new structure.

### Documentation homepage

Use a simple introduction rather than a marketing-card grid:

- product name
- one-sentence value proposition: keep enough context to resume unfinished work without reconstructing the previous session
- primary links: Install / Connect an agent / GitHub
- concise compatibility/self-hosting line
- short flow: Work → Save continuity → Leave → Come back → Resume

Avoid oversized hero gradients, decorative product cards, and dense feature walls.

## Brand-guide alignment

Make implementation match the established brand principles more closely:

- grounded, clear, welcoming
- no gradients/glow in logo/identity treatment
- whitespace/alignment/dividers before extra containers
- restrained shadows
- calm collaborator voice
- Now focused on immediate work
- rewards optional and kept on Progress

If the brand guide needs a small wording update (for example ordinary surface-radius guidance), change it narrowly and explicitly rather than silently diverging.

## Implementation boundaries and likely files

Primary files:

- `src/adhd_hub/ui/index.html`
- `src/adhd_hub/ui/app.css`
- focused files under `src/adhd_hub/ui/js/` only where structural/responsive/accessibility behaviour requires it
- `docs/stylesheets/extra.css`
- `zensical.toml`
- `docs/index.md`
- selected docs pages when navigation/copy needs alignment
- `scripts/browser_smoke.py`
- UI/browser tests where selectors/responsive behaviour need coverage

Avoid unrelated backend/model changes.

## Compatibility requirements

Preserve existing capabilities:

- authentication/password/token flows
- System/Light/Dark preference persistence
- project selection/creation/editing
- thread filtering/search/selection
- Now start/resume/pause/done flows
- reminders/capture
- Progress stats/rewards/share flows
- Settings categories and connection/configuration flows
- PWA behaviour unless explicitly tested and intentionally improved
- existing API/MCP contracts

Prefer preserving existing element IDs used by JavaScript/tests when they do not block the new information architecture. If IDs/DOM structure must change, update JS/tests together rather than adding compatibility hacks.

## Testing and verification

### Automated

Run:

- `uv run pytest`
- `uv run ruff check src tests`
- `uv run --with playwright python scripts/browser_smoke.py`

Update browser-smoke coverage to test the redesigned flows rather than preserving obsolete selectors.

### Responsive/browser coverage

At minimum verify screenshots/flows for:

- desktop light and dark
- mobile light and dark
- Now empty and active states
- My Work list + selected-task detail
- Progress with rewards enabled and disabled
- Settings navigation
- representative dialog
- docs homepage/article on desktop and mobile

### Accessibility

Verify:

- keyboard-only navigation
- screen-heading focus after navigation
- dialog focus/return behaviour
- settings keyboard navigation
- mobile bottom-nav semantics and safe-area spacing
- reduced motion
- no focus indicator clipping
- colour contrast and state labels

## Rollout / PR strategy

Use one dedicated redesign branch/PR so reviewers can evaluate `/ui` and docs as one coherent system while remaining isolated from Foundation B backend work.

The PR should state that presentation/information hierarchy changes intentionally, while backend semantics do not.

Use coherent commits where practical:

1. visual tokens + app shell
2. Now / My Work / Progress
3. Settings / dialogs / mobile
4. docs/wiki redesign
5. browser/accessibility test updates

If implementation becomes unsafe to review as one PR, split only when an actual dependency/review problem appears. Do not mix Foundation B schema changes into this branch.

## Acceptance criteria

The redesign is complete when:

- `/ui` no longer presents most sections as glossy rounded cards.
- the standalone Appearance strip is removed.
- desktop uses one compact theme popover; mobile theme selection lives in Settings.
- Now is a focused, intentionally constrained work surface.
- My Work supports dense scanning and a desktop selected-task detail pane.
- medium/mobile My Work uses a dedicated full-width task-detail view.
- Progress prioritises activity/reflection above optional rewards.
- Settings uses a constrained, readable configuration layout.
- mobile uses a four-destination bottom navigation without obscuring content.
- SPA heading focus remains accessible without the current oversized focus-box appearance.
- docs use a ~72ch prose measure and restrained documentation styling.
- docs navigation/homepage provide a clearer start path.
- light/dark/system themes remain functional.
- existing functional flows covered by browser smoke tests continue to pass.
- no backend/source-sync/MCP semantics change as part of this redesign.
