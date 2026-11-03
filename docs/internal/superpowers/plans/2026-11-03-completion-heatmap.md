# Completion calendar implementation plan

**Goal:** A review-ready PR combining the approved Progress styling with merged Slice A and an accessible completion calendar (#72 / #343).

**Design:** Keep the plain stats row with thin dividers. Add a collapsible calendar for 12 Monday-based weeks through today, using recorded completion events and the Hub timezone. Each day exposes its date/count by keyboard, tap, and hover; a table provides the same counts. Neutral empty days and four calm intensity levels carry no streak or productivity score. Remember collapse state using the existing browser preference helper. Focus time and separate progress-note metrics remain later slices.

**Approach:** Reuse `aggregate_insight_rows` and the existing overview response; add `insights.completion_days` without changing the 14-day chart contract. Fetch the bounded date window without a row limit so busy periods remain accurate. Use the existing Progress module, theme tokens, and native disclosure rather than a chart dependency or new API route.

## Tasks

- [x] Integrate merged main while preserving approved local Progress changes.
- [x] Cover the calendar window, quiet days, timezone/DST boundaries, and more than 20,000 events with aggregation tests.
- [x] Update `insights.py`, `store.py`, and `service.py` to provide complete daily counts while preserving period totals and the 14-day chart.
- [x] Update Progress markup, styles, renderer, boot preferences, and PWA cache; add keyboard/tap details, count table, empty copy, and persistent collapse state.
- [x] Extend browser smoke for populated/empty calendars, day details, storage-denied behavior, and collapse persistence; inspect light/dark desktop/mobile screenshots.
- [x] Run full Pytest, Ruff, browser smoke and UI polish checks; refresh Graphify; audit docs/wiki.
- [x] Update verified merged Slice A checklist items in #343; leave unmerged heatmap checks unchecked.
- [ ] Open a PR with validation results, linked checklist, and the remaining Slice B/C/D scope.

## Verification

- Full Pytest: 1,064 passed.
- Ruff and whitespace checks passed.
- Browser smoke passed, including calendar keyboard navigation, refresh focus, table, collapse persistence, and denied storage.
- UI polish passed across 24 screen/theme/viewport combinations; populated light/dark desktop/mobile screenshots inspected.
- Graphify refreshed using AST extraction. No `graphify-out/wiki/` exists; public dashboard and roadmap docs updated instead.
- Verification exposed missing lifecycle events from API thread upserts. The shared service now publishes them through the existing idempotent event helper; an API regression checks completion counts and retry behavior.

## Review focus

- Local midnight and DST transitions place each event on the correct day.
- Exactly 12 calendar weeks are represented; future days cannot record activity.
- Busy periods include every matching event; forge reconciliation events add no completions.
- Live refresh preserves disclosure choice, keyboard focus, and meaningful day details.
- Collapsed/empty calendars remain usable with denied browser storage and narrow screens.
