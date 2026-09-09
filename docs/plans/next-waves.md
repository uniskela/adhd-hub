# Next waves (post forge-inbox + connect)

Tracking plan for ADHD Progress Hub after the connect one-liner (PR #13) and forge issue inbox (PR #14). Detailed Wave 0 notes live on the connect branch as `docs/plans/improvement-roadmap.md` once merged.

## GitHub tracking

| Item | Issue |
|------|-------|
| Parent epic | [#15](https://github.com/uniskela/adhd-hub/issues/15) |
| Wave 1 — UX | [#16](https://github.com/uniskela/adhd-hub/issues/16) |
| Wave 2 — MCP | [#17](https://github.com/uniskela/adhd-hub/issues/17) |
| Wave 3 — Ops | [#18](https://github.com/uniskela/adhd-hub/issues/18) |
| Wave 4 — Maintainability | [#19](https://github.com/uniskela/adhd-hub/issues/19) |
| Wave 5 — Integrations | [#20](https://github.com/uniskela/adhd-hub/issues/20) |

## Security note (forge inbox)

Inbox sync imports **only** issues authored by usernames in `board_inbox_authors` / `ADHD_HUB_FORGE_BOARD_INBOX_AUTHORS`. Empty allowlist ⇒ import nothing. See [forge-issue-inbox.md](../forge-issue-inbox.md).

## Suggested order

| Priority | Wave | Focus |
|----------|------|--------|
| Done | Inbox harden | Author allowlist (0.3.5) |
| Now | Wave 1 | ADHD UX depth in `/ui` (#16) |
| Then | Wave 2 | MCP parity + OpenClaw memory |
| Later | Connect leftovers | Windows smoke, setup-complete cue |
| Then | Wave 3 | Homelab ops & trust |
| Then | Wave 4 | Split `app.js` / facades / a11y |
| Opt-in | Wave 5 | Slack/Discord, calendar; leaderboard only with identity review |

Keep PRs focused: do not pile Wave 1 onto the forge-inbox PR.

## Wave 1 — ADHD UX depth

1. Reminders in `/ui` (due beside pending actions; create/snooze from My work).
2. Soft-archive projects (hide without deleting threads/wiki; restore path).
3. Focus mode (timed Now session + drift policy; honour reduced-motion).
4. Quick capture → optional auto-thread.
5. Pause/resume polish (`resume_step` after “where was I?”).

## Wave 2 — Agent / MCP parity

1. MCP: `pause_thread`, `dismiss_thread`, `list_reminders`, `get_overview`.
2. One-click workspace add from MCP (complements `connect --register`).
3. Richer OpenClaw memory round-trips (short digest; no raw chats).
4. Keep skills/AGENTS aligned; skills.sh after publish.

## Wave 3 — Homelab ops & trust

1. Durable browser sessions for multi-worker / restart survival.
2. Tailscale / reverse-proxy cookbook (trusted headers, Secure cookies).
3. Forge legacy path cleanup helper.
4. Backup schedule docs + optional encrypted passphrase.
5. `doctor` remote checks (forge, OpenClaw, indexer).

## Wave 4 — Design system & maintainability

1. Split `app.js` by screen.
2. Facades for forge/openclaw out of `HubService`.
3. A11y pass (focus order, live regions, chart alternatives).
4. Calm motion only; no streak guilt.

## Wave 5 — Optional integrations

Only after Waves 0–2 feel stable: Slack/Discord nudges, calendar blocks, public leaderboard only after identity/ledger review. See [rewards-roadmap.md](../rewards-roadmap.md).

## Verification

- `uv run pytest` + `uv run ruff check src tests`
- UI waves: `scripts/browser_smoke.py`
- MCP waves: `scripts/probe_mcp.py`
