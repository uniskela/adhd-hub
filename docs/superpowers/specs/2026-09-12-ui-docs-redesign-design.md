# UI and documentation redesign

Date: 2026-09-12
Branch: `feat/ui-docs-redesign`
Status: Approved design, implementation not started

## Goal

Redesign the ADHD Progress Hub dashboard (`/ui`) and public documentation/wiki so they feel deliberately designed, calm, information-first, and consistent with the product's ADHD-friendly purpose.

This is not a cosmetic reskin. The work changes visual hierarchy and presentation patterns while preserving existing product behaviour, API/MCP semantics, authentication, persistence, and Foundation B data-model work.

The redesign should remove the current card-heavy/glossy appearance, improve information density where scanning matters, reduce visual competition, and make the docs read like technical documentation rather than an application dashboard.

## Product principles

1. **Immediate work wins attention.** The UI should make the current task, next action, and resume cue easier to find than secondary metadata, rewards, or configuration.
2. **Progressive disclosure.** Show the smallest amount of information needed for the current decision. Keep history, technical metadata, long notes, and advanced configuration available without making them visually dominant.
3. **Whitespace before containers.** Use spacing, alignment, typography, and dividers before adding bordered cards or tinted surfaces.
4. **Calm, not sparse for its own sake.** Empty space should support focus, but large dead regions caused by unconstrained desktop layouts should be avoided.
5. **Dense where scanning matters.** Task lists should support quickly scanning many threads without turning every item into a mini-dashboard.
6. **No productivity shame.** Rewards and statistics are optional reflection tools, not the primary framing of progress.
7. **Accessible by default.** Keyboard focus, screen-reader semantics, reduced motion, touch targets, contrast, and responsive behaviour must remain first-class.
8. **One visual language, two contexts.** `/ui` and docs share tokens, typography, logo, and brand colour relationships, but the dashboard remains application-like while documentation remains editorial.

## Non-goals

- No changes to Thread/Project schemas, Foundation B source/authority fields, forge reconciliation, or MCP behaviour.
- No new statistics implementation from #72.
- No new event/SSE plumbing from #75.
- No rewrite of every documentation page.
- No framework migration for the dashboard.
- No React/Vue/Svelte introduction solely for this redesign.
- No generic "modern SaaS" treatment, glassmorphism, decorative gradients, or widespread blur effects.
- No removal of keyboard focus indicators.

## Current-state problems

### Dashboard

The current dashboard uses a repeated visual recipe across most top-level sections: translucent backgrounds, rounded borders, large radii, shadows, and blur. This makes unrelated pieces of content feel equally important and gives the product a generated-dashboard appearance.

The standalone Appearance strip above the main header creates two competing top-level bars. The content area also uses the full viewport width even when the useful content is narrow, which creates large empty regions on wide displays.

The three main screens have different information-density needs but currently share too much of the same card language:

- **Now** is conceptually simple but visually sits in a large left-aligned surface with excessive unused desktop space.
- **My Work** renders threads too prominently, making long task lists slow to scan.
- **Progress** gives rewards/gamification more visual weight than activity/reflection.
- **Settings** stretches form content too widely and wraps configuration in oversized surfaces.

The SPA navigation correctly moves focus to each screen heading, but the global focus-ring styling makes those programmatically focused headings look like large selected boxes. The focus movement should remain; the heading-specific visual treatment should improve.

### Documentation/wiki

The Zensical site has good structural foundations: searchable docs, navigation, light/dark palettes, code blocks, and repository integration. The custom stylesheet, however, intentionally uses a glossy treatment with gradients, glow, blur, wide viewport usage, and dashboard-like chrome.

This conflicts with the existing brand-guide direction that explicitly says to prefer whitespace/alignment/dividers before extra containers and not to add gradients, bevels, or glow to the identity.

Long-form documentation also benefits from a constrained reading measure; ordinary prose should not stretch across a large desktop viewport.

## Visual system

### Colour

Keep the existing Progress Hub identity and colour relationships:

- ivory / deep forest canvas
- white / forest surfaces
- ink / pale-sage text
- teal / mint primary accent
- gold used sparingly for milestone/achievement emphasis
- berry / rose for destructive actions

Accent colour should identify actions, selection, focus, and important state—not decorate every panel.

### Typography

Continue using the local system sans-serif stack. Strengthen hierarchy through size, weight, line height, and spacing rather than background treatments.

- Main page headings: clear but not oversized.
- Section headings: compact and consistent.
- Labels/metadata: visibly secondary.
- Long-form notes/docs: comfortable reading width and line height.
- Eyebrow/all-caps labels: rare landmarks only, not repeated decoration.

### Spacing and surfaces

Use the existing 4/8/12/16/24/32 spacing rhythm consistently.

Default surface radius should move toward roughly 8–10px for ordinary grouped content and controls. Larger soft corners may remain for the primary focus surface or dialogs where appropriate.

Shadows are reserved mainly for dialogs, popovers, and true elevation. Ordinary sections should use flat canvas/surface contrast, whitespace, or dividers.

Backdrop blur and decorative gradients should be removed from normal page surfaces.

## Application shell

Replace the current separate Appearance strip plus header with one clear application header.

Desktop header contents:

- Progress Hub brand/logo
- primary navigation: Now / My Work / Progress
- Save a thought
- Settings
- compact theme control at the far edge, or a compact theme shortcut that complements the full Appearance setting

The header should remain visually quiet and sticky only if it improves navigation without consuming excessive vertical space.

The main application content should use deliberate max-widths per screen rather than one global full-width presentation.

On wide displays:

- Now uses a narrower centred work column.
- My Work can use more width for project navigation + task list + details.
- Progress uses a medium-wide analytical/content column.
- Settings uses a constrained form column within a wider settings shell.

## Now screen

### Purpose

Answer only:

1. What am I doing?
2. What is the next useful action?
3. Where can I leave this so I can resume later?

### Empty state

Use a centred working area around 760–900px maximum width.

Primary content:

- "One thing at a time."
- concise helper copy such as "Choose one task. Everything else can wait."
- primary action: Choose a task
- secondary action: Help me choose

Avoid unrelated stats, rewards, project lists, and dashboard widgets.

### Active-work state

Show:

- project/source as quiet metadata
- task title
- prominent next step / resume cue
- Focus / Blocked / Resume context beneath it
- small coherent action group: Start/Resume, Pause here, Done
- focus timer controls available but visually secondary
- notes/history/details collapsed by default

The active task may use one intentional focus surface. This is one of the few places where a larger rounded container is justified.

## My Work screen

### Purpose

Support scanning, filtering, choosing, and inspecting many work items quickly.

### Desktop layout

Three conceptual regions:

1. **Projects/filter rail** — compact, quiet, scannable.
2. **Work list** — dense task rows.
3. **Selected-task details** — right-side panel when viewport width permits.

The list should not render every thread as a large card.

Default row content:

- task title
- project
- source/provider when relevant
- continuity/status state
- last-updated cue
- at most one secondary continuity line, such as current Focus or Resume cue

Rows use dividers/selection state instead of heavy card chrome.

Selecting a task opens its continuity/actions in the desktop detail pane. On smaller widths, details become an inline expansion or dedicated full-width detail view/sheet.

### Projects rail

Keep project navigation, but reduce button weight. "New project" is available without competing visually with actual work.

Archived projects remain progressively disclosed.

### Tabs/search

Open / Pick up later / Finished remain clear filters. Search should be prominent enough to use quickly but not consume a large vertical block.

## Progress screen

### Purpose

Answer "What progress have I made lately?" without framing inactivity as failure.

### Primary hierarchy

1. concise activity summary
2. activity history/chart
3. optional milestones/rewards

Existing useful summary metrics such as finished-this-week/open work may remain. The current 14-day activity view should be visually stronger than rewards when rewards are enabled.

The layout should be compatible with future #72 additions such as:

- contribution-style activity heatmap
- tracked focus time
- daily/weekly/monthly completions
- project breakdowns

without requiring another full structural redesign.

### Rewards

Rewards remain opt-in.

Replace oversized rank/badge presentation with a compact Milestones section:

- current rank/level/XP
- concise progress-to-next-rank indicator
- compact badge list/chips
- share action remains available

Rewards are one interpretation of progress, not the dominant screen identity.

## Settings

### Desktop structure

Keep category navigation because the underlying information architecture is sound.

Use a left settings navigation and a constrained main settings column of approximately 720–840px.

Categories continue to cover the existing settings areas, such as:

- Preferences
- Account
- Connections
- Forge
- Data

Within a category:

- normal section headings
- short consequence-oriented descriptions
- dividers/spacing instead of nested cards
- connection/provider status shown as compact labelled rows
- destructive/data actions clearly separated from ordinary preferences
- version/repository information in a quiet footer/meta region

Remove decorative copy that does not help configure the product.

### Appearance

The full System / Light / Dark setting remains in Settings. A compact header shortcut may remain for convenience, but the separate appearance strip above the application is removed.

## Dialogs

Dialogs are one of the few places where elevation/shadow is appropriate.

Standardise dialogs around:

- clear title
- concise explanation only where needed
- focused content
- logical action row
- one clear primary action per action group
- explicit destructive styling where appropriate
- visible close/cancel behaviour
- Escape handling and focus return preserved

Avoid explanatory sub-panels inside dialogs unless they materially reduce risk/confusion.

## Responsive/mobile behaviour

Mobile should be designed as its own composition rather than desktop compressed to fit.

### Navigation

On narrow screens, use durable mobile navigation for Now / My Work / Progress / Settings. A bottom navigation is preferred if it integrates cleanly with existing semantics and does not obscure content; otherwise use an equally clear compact top-navigation pattern.

### Now

- full-width work surface
- no horizontal action overflow
- focus timer controls collapse cleanly

### My Work

- projects become a filter/project drawer or compact picker
- work list remains dense and single-column
- selected-task details open as a full-width detail surface rather than a squeezed side pane

### Progress

- summary metrics stack/wrap cleanly
- charts remain readable
- future heatmap should use responsive cell sizing before horizontal scrolling
- rewards remain beneath activity

### Settings

- category list becomes a mobile settings index
- selected category opens as its own panel/page
- avoid horizontally scrolling tab bars where practical

## Accessibility

Preserve and improve:

- 44px minimum touch targets for interactive controls where applicable
- visible keyboard focus
- semantic current/selected state
- programmatic screen-heading focus after SPA navigation
- focus return after dialogs/settings
- reduced-motion support
- colour-independent status cues
- usable contrast in light/dark themes
- keyboard-operable settings navigation
- screen-reader-friendly labels/status messages

### Page-heading focus

Do not remove the existing focus transfer to the active screen heading. Instead, introduce heading-specific focus styling so a focused `h1[tabindex="-1"]` is clearly discoverable to keyboard/screen-reader users without looking like a giant selected form control.

## Documentation/wiki redesign

### Visual direction

The docs should feel like technical documentation, not a glossy dashboard.

Retain Zensical and the existing documentation content system.

Remove/reduce:

- glossy gradient header treatments
- glow effects
- backdrop blur
- decorative chrome
- unnecessarily full-width prose
- heavy active-state boxes

Use:

- flat header/navigation
- restrained use of brand teal/mint
- strong typography hierarchy
- constrained article measure around 70–80 characters for normal prose
- wider breakout treatment only for tables, diagrams, and code where needed
- clean code/admonition styles
- clear active navigation state
- generous but purposeful vertical rhythm

### Information architecture

Reorganise navigation conceptually as:

**Start here**
- What is ADHD Progress Hub?
- Installation
- Connect your coding agent
- First project / setup
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

The implementation does not need to rewrite every page. Navigation labels/placement and targeted landing-page copy can change where needed to support the new structure.

### Documentation homepage

Use a simple introduction rather than a marketing-card grid.

Recommended structure:

- product name
- one-sentence value proposition: preserving enough context to resume unfinished work without reconstructing the previous session
- primary links: Install / Connect an agent / GitHub
- concise compatibility/self-hosting line
- short "How it works" flow: Work → Save continuity → Leave → Come back → Resume

Avoid oversized hero gradients, decorative product cards, or dense feature walls.

## Brand-guide alignment

The redesign should make implementation match the existing brand principles more closely.

Where the current brand guide and implementation disagree, prefer these established guide principles:

- grounded, clear, welcoming identity
- no gradients/glow added to the logo/identity
- whitespace/alignment/dividers before extra containers
- restrained shadows
- calm collaborator voice
- Now screen focused on immediate work
- rewards kept on their own screen and optional

If implementation reveals that the brand guide itself needs a small wording update (for example, ordinary surface radius guidance), update it narrowly and explicitly rather than silently diverging.

## Implementation boundaries and likely files

Primary files:

- `src/adhd_hub/ui/index.html`
- `src/adhd_hub/ui/app.css`
- focused files under `src/adhd_hub/ui/js/` only where structural/responsive/accessibility behaviour requires changes
- `docs/stylesheets/extra.css`
- `zensical.toml`
- `docs/index.md`
- selected docs pages only when navigation/copy needs alignment
- `scripts/browser_smoke.py`
- UI/browser tests where selectors or responsive behaviour need coverage

Avoid unrelated backend/model changes.

## Compatibility requirements

The redesign must preserve existing user-visible capabilities, including:

- authentication/password/token flows
- theme persistence and System/Light/Dark options
- project selection/creation/editing
- thread filtering/search/selection
- Now task start/resume/pause/done flows
- reminders/capture
- Progress stats/rewards/share flows
- Settings categories and connection/configuration flows
- PWA behaviour unless explicitly tested and intentionally improved
- existing API/MCP contracts

Prefer preserving existing element IDs used by JavaScript and tests where doing so does not block the new information architecture. Where IDs/DOM structure must change, update tests and JS together rather than adding compatibility hacks.

## Testing and verification

### Automated

Run:

- `uv run pytest`
- `uv run ruff check src tests`
- `uv run --with playwright python scripts/browser_smoke.py`

Update browser-smoke coverage to verify the redesigned flows rather than merely keeping obsolete selectors alive.

### Responsive/browser coverage

At minimum verify screenshots/flows for:

- desktop light and dark
- mobile-width light and dark
- Now empty and active states
- My Work list + selected-task details
- Progress with rewards enabled and disabled
- Settings category navigation
- representative dialog
- docs homepage/article on desktop and mobile

### Accessibility checks

Verify:

- keyboard-only navigation
- heading focus after screen changes
- dialog focus trap/return behaviour where applicable
- settings keyboard navigation
- reduced motion
- no focus indicator clipping
- colour contrast and state labels

## Rollout / PR strategy

Use one dedicated redesign branch/PR so reviewers can evaluate `/ui` and docs as one coherent visual system while remaining isolated from Foundation B backend work.

The PR should explain that it intentionally changes presentation and information hierarchy but not backend semantics.

If implementation becomes too large to review safely, split the implementation commits internally by coherent layer (tokens/shell, screens, settings/mobile, docs, tests) while keeping one PR unless an actual dependency/review problem appears.

Do not merge unrelated Foundation B schema changes into this branch.

## Acceptance criteria

The redesign is complete when:

- `/ui` no longer presents most sections as glossy rounded cards.
- the standalone Appearance strip is removed.
- Now is a focused, intentionally constrained work surface.
- My Work supports dense scanning of many threads and provides a clear selected-task detail experience.
- Progress prioritises useful activity/reflection above optional rewards.
- Settings uses a constrained, readable configuration layout.
- mobile layouts are deliberate rather than compressed desktop layouts.
- SPA heading focus remains accessible without the current oversized heading focus box appearance.
- docs use a readable article width and restrained technical-documentation styling.
- docs navigation and homepage provide a clearer start path.
- light/dark/system themes remain functional.
- existing functional flows covered by browser smoke tests continue to pass.
- no backend/source-sync/MCP semantics are changed as part of the redesign.
