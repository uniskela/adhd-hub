# Next waves (post forge-inbox + connect)

Tracking plan for ADHD Progress Hub after the connect one-liner (PR #13) and forge issue inbox (PR #14). Detailed wave notes live in [`improvement-roadmap.md`](improvement-roadmap.md).

## GitHub tracking

| Item | Issue |
|------|-------|
| Parent epic | [#15](https://github.com/uniskela/adhd-hub/issues/15) |
| Wave 1 — UX | [#16](https://github.com/uniskela/adhd-hub/issues/16) |
| Wave 2 — MCP | [#17](https://github.com/uniskela/adhd-hub/issues/17) |
| Wave 3 — Ops | [#18](https://github.com/uniskela/adhd-hub/issues/18) |
| Wave 4 — Maintainability | [#19](https://github.com/uniskela/adhd-hub/issues/19) |
| Wave 5 — Integrations | [#20](https://github.com/uniskela/adhd-hub/issues/20) |
| Wave 6 — AI clarity | [#52](https://github.com/uniskela/adhd-hub/issues/52) |
| Wave 7 — Continuity intelligence | [#54](https://github.com/uniskela/adhd-hub/issues/54) |
| Wave 8 — Find & capture | [#55](https://github.com/uniskela/adhd-hub/issues/55) |
| Wave 9 — Shared surfaces | [#56](https://github.com/uniskela/adhd-hub/issues/56) |

## Security note (forge inbox)

Inbox sync imports **only** issues authored by usernames in `board_inbox_authors` / `ADHD_HUB_FORGE_BOARD_INBOX_AUTHORS`. Empty allowlist ⇒ import nothing. See [forge-issue-inbox.md](../forge-issue-inbox.md).

## Suggested order

| Priority | Wave | Focus |
|----------|------|--------|
| Done | Inbox harden | Author allowlist (0.3.5) |
| Done | Wave 1 | ADHD UX depth in `/ui` (#16 / PR #22) — shipped in 0.3.6 |
| Done | Wave 2 | MCP parity + OpenClaw memory (#17 / PR #24) — shipped in 0.3.6 |
| Done | Wave 3 | Homelab ops, trust, PWA (#18) — shipped in 0.3.7 |
| Done | Wave 4 | Split `app.js` / facades / a11y (#19) — shipped in 0.3.8 |
| Now | Wave 6 | AI thread summaries + project list tags/categories + optional AI organiser (#52) |
| Next | Wave 7 | Stale triage, cross-project Next-up, merge/dedupe cues, return-cue nudges (#54) |
| Next | Wave 8 | Wiki compaction, global search, mobile capture, energy/context modes (#55) |
| Later | Wave 9 | Related-work map, household multi-profile, skills.sh listing (#56) |
| Opt-in | Wave 5 | Slack/Discord, calendar; leaderboard only with identity review (#20) |

Prefer **Wave 6 → 7 → 8** (clarity and findability) before Wave 5 integrations or Wave 9 shared surfaces. Do not start Wave 5 early unless a specific integration is urgently needed (see issue #20).

## Wave 6 — AI clarity & project organisation

1. **AI task/thread summaries** — default scannable Now/Done/Next/Waiting/Return cue; expand for full detail; opt-in local LLM with heuristic fallback.
2. **Cleaner project list** — tags/categories, filters, lower density (title + one-line status + open count + last touch).
3. **Optional AI sorter/organiser** — suggest tags/groupings; apply only after human confirmation.

## Wave 7 — Continuity intelligence

1. Stale-thread triage (confirm / snooze; never auto-dismiss).
2. Cross-project Next-up ranking (honour focus-mode drift policy).
3. Thread merge / dedupe cues (human merges only).
4. Return-cue quality nudges (advisory only).

## Wave 8 — Find & capture

1. Progress wiki compaction (reversible).
2. Global search (local-first).
3. Capture share target / mobile PWA.
4. Energy / context modes (no energy guilt).

## Wave 9 — Shared surfaces & discoverability

1. Related-work map (optional; list stays default).
2. Household multi-profile (soft; no public leaderboard by default).
3. skills.sh listing after publish.

## Wave 5 — Optional integrations

Only after clarity/findability work feels stable: Slack/Discord nudges, calendar blocks, public leaderboard only after identity/ledger review. See [rewards-roadmap.md](../rewards-roadmap.md).

## Verification

- `uv run pytest` + `uv run ruff check src tests`
- UI waves: `scripts/browser_smoke.py`
- MCP waves: `scripts/probe_mcp.py`
