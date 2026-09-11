# ADHD Progress Hub — improvement roadmap (2026-09)

Approved planning snapshot for sequenced delivery after **v0.3.4**. This is the source of truth for upcoming waves; README “Roadmap” bullets should stay aligned with Wave status below.

## Current state (evidence)

Self-hosted FastAPI hub: SQLite + markdown wiki, MCP (`/mcp`), REST (`/api`), calm `/ui` (Now / My work / Progress), forge sync, OpenClaw nudges, rewards, backup/import, `adhd-hub setup` / `connect`, agent skills, coding companions, Pages docs.

Shipped through **0.4.1**: Waves 0–4, connect pairing + install wheel (0.4.0), coding companions + ADHD-friendly connect reports (0.4.1).

Largest complexity remains UI modules under `src/adhd_hub/ui/`, plus `service.py` / `store.py`. MCP is close to REST parity for core continuity tools. Browser sessions can be durable. Rewards prefs remain browser-local.

## Product principles (do not violate)

- Calm, resumable, non-punitive ADHD UX (brand guide + writing guide).
- Summaries only — never raw transcripts or secrets in hub payloads or generated docs.
- Public/committed artifacts never embed Hub URL, tokens, or machine paths.
- Soft defaults; destructive actions need explicit human confirmation (pending actions pattern).
- Opt-in for global side effects (skills, OpenClaw, forge, remote AI).

## Wave 0 — Client wire-up one-liner

**Status:** shipped in **0.3.5**.

Hub-backed `/install.sh` + `/install.ps1`, `adhd-hub connect` / `doctor`, MCP/rules/AGENTS merge, optional skills and OpenClaw skill install. See historical detail in git history if needed; operator docs live in [connect.md](../connect.md).

## Wave 1 — ADHD UX depth

**Status:** shipped in **0.3.6** (PR #22 / issue #16).

1. Reminders in `/ui` — due reminders beside pending actions; create/snooze from My work.
2. Soft-archive projects — hide without deleting threads/wiki; restore path.
3. Focus mode — timed Now session + drift policy (“only this project”); honour reduced-motion.
4. Quick capture → thread — Save a thought already exists; wire optional auto-thread create.
5. Pause/resume polish — surface `resume_step` more prominently after doctor-style “where was I?”.

## Wave 2 — Agent / MCP parity

**Status:** shipped in **0.3.6** (PR #24 / issue #17).

1. MCP tools: `pause_thread`, `dismiss_thread`, `list_reminders`, `get_overview` (read-only).
2. One-click workspace add from MCP — complements `connect --register`.
3. Richer OpenClaw memory round-trips (short digest in / short ack out; still no raw chats).
4. Keep skills/AGENTS aligned with new tools; skills.sh listing after publish.

## Wave 3 — Homelab ops & trust

**Status:** shipped in **0.3.7** (PR #26 / issue #18).

1. Durable browser sessions (sqlite/redis-backed) for multi-worker / restart survival.
2. Tailscale / reverse-proxy cookbook polish (trusted headers, HTTPS cookie Secure).
3. Forge legacy path cleanup helper (`adhd-hub/wiki/**` → root `projects/`).
4. Backup schedule docs + optional encrypted backup passphrase.
5. `doctor` remote checks: forge reachability, OpenClaw test hook, indexer last run.
6. Installable PWA for `/ui` (manifest + shell-only service worker).

## Wave 4 — Design system & maintainability

**Status:** shipped in **0.3.8** (PR #28 / issue #19).

1. Split `app.js` by screen (now / work / progress / settings / share).
2. Facades for forge/openclaw out of `HubService` without behaviour change.
3. A11y pass: focus order, live regions for save confirmations, chart alternatives.
4. Prefer calm motion only; no streak guilt or competitive UI.

## Wave 5 — Optional integrations (explicit opt-in)

**Status:** upcoming — issue [#20](https://github.com/uniskela/adhd-hub/issues/20). Only after core clarity work feels stable.

| Integration | Fit | Constraint |
|-------------|-----|------------|
| Slack / Discord | Gentle stale nudge parallel to OpenClaw | Same anti-nag policy |
| Linear / GitHub Projects already partial | Import issues as threads | Never auto-close remote |
| Calendar | Reminder due → calendar block | Local-first; no public calendars by default |
| Public leaderboard | See [rewards-roadmap.md](../rewards-roadmap.md) | Separate identity + ledger review |

## Wave 6 — AI clarity & project organisation

**Status:** next product focus — issue [#52](https://github.com/uniskela/adhd-hub/issues/52).

Reduce information overload without abandoning the wiki/thread source of truth.

### 6a — AI task / thread summaries

- Default thread/progress views show a short AI (or heuristic) summary: **Now / Done / Next / Waiting / Return cue**.
- Full description remains one expand/tap away — never delete detail.
- Agents and MCP should prefer posting structured short fields; Hub may compress verbose agent dumps into a summary + raw appendix.
- Provider: opt-in local LLM first (homelab); remote APIs only with explicit config. Offline/heuristic fallback when AI is off.
- Never put secrets, tokens, Hub URLs, or machine paths into generated summaries.

### 6b — Cleaner project list (tags / categories)

- Lighter project list density: title, one-line status, open-thread count, last touch.
- Manual **tags** and/or **categories** (e.g. Homelab, App, Docs, Parked) with filter chips.
- Soft-archive already exists — keep archive out of the default list.
- Search/filter by tag, stale age, and open vs idle.

### 6c — Optional AI sorter / organiser

- Suggest tags, categories, and “park vs active” groupings from titles + recent progress.
- Apply only after human confirmation (pending-actions pattern) — no surprise reorganisation.
- Optional “tidy suggestions” digest once per session, not a nag stream.

## Wave 7 — Continuity intelligence

**Status:** planned after Wave 6 — issue [#54](https://github.com/uniskela/adhd-hub/issues/54).

1. **Stale-thread triage** — soft “still relevant?” pass for old open threads; confirm or snooze; never auto-dismiss.
2. **Cross-project Next-up ranking** — one calm “what now?” across projects when focus mode is off; honour drift policy.
3. **Thread merge / dedupe cues** — surface `check_overlap` as UI suggestions; human merges only.
4. **Return-cue quality nudges** — advisory coaching toward concrete return cues; never blocking.

## Wave 8 — Find & capture

**Status:** planned after Wave 7 — issue [#55](https://github.com/uniskela/adhd-hub/issues/55).

1. **Progress wiki compaction** — rolling summary + older sections collapsed; full markdown recoverable.
2. **Global search** — find threads/projects/wiki snippets fast; local-first; no external index required.
3. **Capture share target / mobile PWA** — phone capture into quick thought → thread; keep offline-friendly.
4. **Energy / context modes** — short vs deep return views; prefs local; no gamified energy guilt.

## Wave 9 — Shared surfaces & discoverability

**Status:** planned after Waves 6–8 feel stable — issue [#56](https://github.com/uniskela/adhd-hub/issues/56).

1. **Related-work map** — optional light graph of overlapping projects/threads; list remains the default.
2. **Household multi-profile (soft)** — shared hub with separate Now surfaces; no public leaderboard by default.
3. **skills.sh listing** — discoverability after package publish (ops/marketing; not UX-critical).

Do **not** prioritise competitive social features, auto-closing remote issues, or dumping full chat transcripts into the hub.

## Verification per wave

- `uv run pytest` + `uv run ruff check src tests`
- `scripts/browser_smoke.py` for UI waves
- `scripts/probe_mcp.py` for MCP waves
- Manual: `curl …/install.sh` + `adhd-hub doctor` on a clean temp home

## Rollback

- Wire-up writes are idempotent and scoped; uninstall via `adhd-hub setup --uninstall` and documented MCP key removal.
- Feature flags / prefs stay opt-in; forge, OpenClaw, and AI providers remain disableable in Settings.

## Status

| Wave | Status |
|------|--------|
| 0 Client wire-up | Shipped in 0.3.5 |
| 1 ADHD UX depth | Shipped in 0.3.6 (PR #22 / issue #16) |
| 2 MCP parity | Shipped in 0.3.6 (PR #24 / issue #17) |
| 3 Homelab ops + PWA | Shipped in 0.3.7 (PR #26 / issue #18) |
| 4 Maintainability | Shipped in 0.3.8 (PR #28 / issue #19) |
| 5 Optional integrations | Upcoming / opt-in — issue #20 |
| 6 AI clarity + project list | Next — issue #52 |
| 7 Continuity intelligence | After Wave 6 — issue #54 |
| 8 Find & capture | After Wave 7 — issue #55 |
| 9 Shared surfaces & discoverability | After 6–8 stable — issue #56 |

Wave 1 + Wave 2 shipped together in **0.3.6**. Prefer Wave 6 → 7 → 8 (clarity and findability) before expanding Wave 5 integrations or Wave 9 shared surfaces, unless a specific need is urgent.
