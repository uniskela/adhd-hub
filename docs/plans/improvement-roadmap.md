# ADHD Progress Hub — improvement roadmap (2026-09)

Current product roadmap for ADHD Progress Hub. GitHub issue [#15](https://github.com/uniskela/adhd-hub/issues/15) is the tracking parent; [`next-waves.md`](next-waves.md) is the compact sequence.

Reviewed against **current `main` on 2026-09-14** (package version v0.10.0; v0.10.1 fixes are merged but not yet released).

## Current state

ADHD Hub is a self-hosted FastAPI application with SQLite + markdown wiki storage, MCP (`/mcp`), REST (`/api`), the `/ui` dashboard, GitHub/Gitea integration, OpenClaw integration, backup/import, project guidance, coding companions, OAuth-enabled MCP auth, and Pages documentation.

Shipped foundations now include:

- Waves 0–4;
- the one-thread-one-outcome continuity model (Foundation A / PR #65);
- source-aware local/external work identity (Foundation B1 / #73);
- repo-primary GitHub/Gitea reconciliation (Foundation B2 / #74);
- later v0.9.x/v0.10.0 reliability and forge operational improvements, including queued/running/done/failed Forge job visibility.

**The current product focus is Foundation B3 (#75), not Wave 6 yet.** B3 adds the durable event/history and live-state layer that later features should consume rather than recreating independently.

## Product principles

- Calm, resumable, non-punitive ADHD UX.
- Summaries only — never raw transcripts or secrets in Hub payloads or generated docs.
- Public/committed artifacts never embed private Hub URLs, tokens, or machine-specific paths.
- Soft defaults; destructive actions require explicit human confirmation.
- Opt-in for global side effects such as skills, OpenClaw, forge writes, and remote AI.
- Local/non-repo work remains first-class and must not require a forge.
- Repo-backed task fields are forge-authoritative; Hub continuity fields are Hub-authoritative.
- Do not use generic last-write-wins or silently publish private continuity to public issues.

## Shipped waves

### Wave 0 — client wire-up ✅

Shipped in v0.3.5: Hub-backed `/install.sh` + `/install.ps1`, `adhd-hub connect` / `doctor`, MCP/rules/AGENTS merge, optional skills and OpenClaw skill install.

### Wave 1 — ADHD UX depth ✅

Shipped in v0.3.6 via #16 / PR #22: reminders, soft archive, focus mode, quick capture and resume polish.

### Wave 2 — Agent / MCP parity ✅

Shipped in v0.3.6 via #17 / PR #24: pause/dismiss/reminder/overview MCP parity, workspace registration and richer OpenClaw continuity support.

### Wave 3 — homelab ops & trust ✅

Shipped in v0.3.7 via #18 / PR #26: durable browser sessions, reverse-proxy guidance, wiki-path migration tooling, encrypted backup support, doctor remote checks and installable PWA.

### Wave 4 — design system & maintainability ✅

Shipped in v0.3.8 via #19 / PR #28: split UI modules, service facades, accessibility improvements and calmer motion defaults.

## Foundation A — deterministic continuity ✅

PR #65 established one thread = one independently finishable outcome, explicit thread targeting, structured Goal / Focus / Next / Blocked / Resume state, thread-scoped history, guidance drift detection and thread-scoped forge status.

This foundation is complete. Later waves build on it; they must not reimplement it.

## Foundation B — source-aware work sync, live state & reconciliation

Tracking umbrella: [#71](https://github.com/uniskela/adhd-hub/issues/71).

### B1 — source-aware work identity & authority ✅

[#73](https://github.com/uniskela/adhd-hub/issues/73), shipped in v0.8.0 via PR #76.

- Local work remains Hub-owned.
- Repo-backed work has durable provider/host/repository/issue identity.
- External task state is distinct from Hub continuity status.
- Project default source plus per-thread override/linking is supported.
- Legacy forge mappings migrate fail-safe without inventing uncertain links.

### B2 — repo-primary issue sync & reconciliation ✅

[#74](https://github.com/uniskela/adhd-hub/issues/74), shipped in v0.8.0 via PRs #79 and #80.

- Ordinary GitHub/Gitea issues can remain canonical repo-backed tasks.
- Import scope is configurable and pull requests are excluded.
- Remote close/reopen reconciles without overwriting Hub continuity state.
- Explicit Hub close/reopen actions are remote-first.
- Local Hub work can be deliberately promoted/linked without dumping private continuity into the issue.
- Scheduled reconciliation is the correctness fallback and avoids overlapping runs.

### B3 — activity ledger, live UI & sync health 🔄 **NOW**

[#75](https://github.com/uniskela/adhd-hub/issues/75).

The v0.10.0 Forge job queue is useful operational state, but it is not the durable history model required here.

Scope:

1. **Durable structured event ledger**
   - meaningful thread/work/session/forge events;
   - publish only after the underlying mutation is committed/confirmed;
   - no raw transcripts or secrets;
   - idempotency/dedupe for reconciliation echoes.
2. **Live UI invalidation**
   - authenticated same-origin SSE first;
   - small invalidation hints, not full private payloads;
   - normal API refetch remains displayed truth;
   - safe reconnect/catch-up and ordinary request-driven fallback.
3. **Sync/connection health**
   - last success/failure;
   - provider/configured-source status;
   - Needs review conflicts;
   - useful current Forge job state where relevant;
   - compact human-readable change history.
4. **History substrate for statistics**
   - provide trustworthy events/session data for #72 rather than reconstructing history from current rows or commit timestamps.

Foundation B is complete only when B3 is shipped and the UI can show current sync/history state without reading server logs.

## Wave 5 — optional integrations

[#20](https://github.com/uniskela/adhd-hub/issues/20) — **deferred / opt-in**.

Potential scoped integrations: Slack/Discord nudges, private calendar reminder blocks, and later sharing/leaderboard work only after separate privacy/identity review.

Do not make this the default next wave. Pull a single integration forward only when a concrete need justifies it.

## Wave 6 — AI clarity & project organisation

[#52](https://github.com/uniskela/adhd-hub/issues/52) — **next after B3**.

1. Short AI or heuristic task/thread summaries using structured continuity.
2. Cleaner project list with tags/categories, filters, open count and last-touch cues.
3. Optional AI sorter/organiser that only applies suggestions after human confirmation.

Remote AI remains explicit opt-in; local/heuristic fallback is required. Generated summaries must not contain secrets, private Hub URLs, machine paths or raw transcripts.

## Wave 7 — continuity intelligence

[#54](https://github.com/uniskela/adhd-hub/issues/54) — after Wave 6.

1. Soft stale-thread triage.
2. Calm cross-project Next-up ranking.
3. Merge/dedupe suggestions based on overlap; human merges only.
4. Advisory return-cue quality nudges.

Reuse #75 history/events where useful; do not create parallel telemetry.

## Wave 8 — find & capture

[#55](https://github.com/uniskela/adhd-hub/issues/55) — after Wave 7.

1. Reversible progress-wiki compaction.
2. Local-first global search across projects/threads/wiki snippets.
3. Mobile/share capture into quick thought → thread.
4. Energy/context modes without productivity guilt.

## Activity insights & statistics

[#72](https://github.com/uniskela/adhd-hub/issues/72) — after the core clarity/findability work, before or alongside later Wave 9 work.

Build on #75 durable history plus persisted focus sessions:

- daily/weekly/monthly completions and activity;
- trustworthy tracked focus time;
- project/activity trends;
- optional contribution-style heatmap;
- timezone-correct aggregation;
- neutral treatment of zero-activity days.

This is reflection tooling, not employee surveillance or productivity scoring. Do not infer coding hours from Git commit timestamps.

## Wave 9 — shared surfaces & discoverability

[#56](https://github.com/uniskela/adhd-hub/issues/56) — later, after Waves 6–8 are stable.

1. Optional related-work map; list remains the default.
2. Soft household multi-profile with separate Now surfaces.
3. skills.sh discoverability after packaging/distribution is ready.

Do not prioritise competitive social features, auto-closing remote issues, or transcript-sharing surfaces.

## Independent repository maintenance

Security and CI maintenance may land whenever needed without changing the product-wave order:

- [#101](https://github.com/uniskela/adhd-hub/issues/101) — Gitleaks, Node-24-era GitHub Actions audit, pinned Action dependency upkeep.
- [#102](https://github.com/uniskela/adhd-hub/issues/102) — restore a clean full pytest/Ruff baseline and add a normal read-only PR quality gate.

## Verification per wave

- `uv run pytest`
- `uv run ruff check src tests`
- UI work: `scripts/browser_smoke.py`
- MCP work: `scripts/probe_mcp.py`
- Installation changes: streamed install regression tests plus clean-temp-home/manual smoke where appropriate

## Rollback and safety

- Setup/connect writes stay scoped and reversible.
- Feature flags/preferences remain opt-in where they cause external side effects.
- Forge, OpenClaw and remote AI providers remain disableable.
- Live UI/events must degrade safely to normal API-driven behaviour.

## Current sequence summary

| Priority | Work | Status |
|---|---|---|
| Done | Waves 0–4 | Shipped |
| Done | Foundation A | Shipped |
| Done | Foundation B1 #73 | Shipped in v0.8.0 |
| Done | Foundation B2 #74 | Shipped in v0.8.0 |
| **Now** | **Foundation B3 #75** | Event ledger / live UI / sync health |
| Next | Wave 6 #52 | AI clarity + project organisation |
| Then | Wave 7 #54 | Continuity intelligence |
| Then | Wave 8 #55 | Find & capture |
| Later | Activity insights #72 | Uses #75 history |
| Later | Wave 9 #56 | Shared surfaces/discoverability |
| Opt-in | Wave 5 #20 | Integrations only when justified |
