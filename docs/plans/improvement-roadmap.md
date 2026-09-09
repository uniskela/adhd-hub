# ADHD Progress Hub — improvement roadmap (2026-09)

Approved planning snapshot for sequenced delivery after **v0.3.4**. This is the source of truth for upcoming waves; README “Roadmap” bullets should stay aligned with Wave status below.

## Current state (evidence)

Self-hosted FastAPI hub: SQLite + markdown wiki, MCP (`/mcp`), REST (`/api`), calm `/ui` (Now / My work / Progress), forge sync, OpenClaw nudges, rewards, backup/import, `adhd-hub setup` (AGENTS.md only), agent skills, Pages docs.

Largest complexity: [`src/adhd_hub/ui/app.js`](../../src/adhd_hub/ui/app.js), [`service.py`](../../src/adhd_hub/service.py), [`store.py`](../../src/adhd_hub/store.py). MCP is thinner than REST (no pause/dismiss/list reminders/forge). Browser sessions are in-process (single worker). Rewards prefs are browser-local.

## Product principles (do not violate)

- Calm, resumable, non-punitive ADHD UX (brand guide + writing guide).
- Summaries only — never raw transcripts or secrets in hub payloads or generated docs.
- Public/committed artifacts never embed Hub URL, tokens, or machine paths.
- Soft defaults; destructive actions need explicit human confirmation (pending actions pattern).
- Opt-in for global side effects (skills, OpenClaw, forge).

## Wave 0 — Client wire-up one-liner (this delivery)

**Goal:** One calm command that connects a machine and/or project to a running Hub, piggybacking on the server’s public URL.

### Operator experience

```bash
# From any machine that can reach the Hub (token stays in the env, never in the script):
export ADHD_HUB_AUTH_TOKEN=...   # optional until MCP probe / register
curl -fsSL http://<hub-host>:8787/install.sh | sh -s -- /path/to/project
```

```powershell
# Windows PowerShell
$env:ADHD_HUB_AUTH_TOKEN = "..."
irm http://<hub-host>:8787/install.ps1 | iex
```

```bash
# Equivalent once the package is installed:
adhd-hub connect /path/to/project --hub http://<hub-host>:8787
adhd-hub connect /path/to/project --hub http://<hub-host>:8787 --dry-run
adhd-hub doctor --hub http://<hub-host>:8787 --project /path/to/project
```

### What `connect` does

| Step | Global | Per-project | Notes |
|------|--------|-------------|--------|
| Probe Hub `/api/health` + `/` | yes | — | Fail soft with clear next step |
| Merge MCP into Cursor user or project config | `--scope user\|project` | project `.cursor/mcp.json` | Uses `${env:ADHD_HUB_AUTH_TOKEN}`; never writes the token |
| Codex `~/.codex/config.toml` MCP block | optional | — | `bearer_token_env_var` |
| Claude Code MCP snippet / config merge | optional | — | HTTP MCP shape from adapters |
| Install Cursor rule | optional | `.cursor/rules/adhd-hub.mdc` | From adapters |
| `AGENTS.md` managed block | — | yes | Reuses existing `project_setup` |
| `npx skills add … -g` | `--skills` | — | Opt-in |
| OpenClaw skills (`-a openclaw`) | `--openclaw-skills` | — | Opt-in; does not store OpenClaw hook token locally |
| Register project on Hub | `--register` | resolve via API | Requires bearer token |
| Discover candidate folders | `--find-roots` | report/register | Heuristic: `.git` / existing Hub markers |
| Print OpenClaw Connections next steps | when Hub reachable | — | Token entry remains in `/ui` |

### Server piggyback

- Public `GET /install.sh` (macOS/Linux/WSL) and `GET /install.ps1` (Windows) — shell/PowerShell bootstrap with Hub base URL derived from request or `ADHD_HUB_PUBLIC_URL`. **No auth token in the script.**
- Root JSON hint includes both install paths.
- Connections settings already hold OpenClaw; connect only installs skills and points operators at Save & test. UI shows both Unix and Windows copy commands.

### Non-goals for Wave 0

- Auto-writing OpenClaw gateway hook secrets into the Hub without an explicit authenticated API call.
- OAuth or multi-user Hub accounts.
- Rewriting unrelated MCP servers already present (merge by server key `adhd-hub` only).

## Wave 1 — ADHD UX depth

1. **Reminders in `/ui`** — due reminders beside pending actions; create/snooze from My work.
2. **Soft-archive projects** — hide without deleting threads/wiki; restore path.
3. **Focus mode** — timed Now session + drift policy (“only this project”); honour reduced-motion.
4. **Quick capture → thread** — Save a thought already exists; wire optional auto-thread create.
5. **Pause/resume polish** — surface `resume_step` more prominently after doctor-style “where was I?”.

## Wave 2 — Agent / MCP parity

1. MCP tools: `pause_thread`, `dismiss_thread`, `list_reminders`, `get_overview` (read-only).
2. One-click workspace add from MCP (title from folder + path + default open thread) — complements `connect --register`.
3. Richer OpenClaw memory round-trips (short digest in / short ack out; still no raw chats).
4. Keep skills/AGENTS aligned with new tools; skills.sh listing after publish.

## Wave 3 — Homelab ops & trust

1. Durable browser sessions (sqlite/redis-backed) for multi-worker / restart survival.
2. Tailscale / reverse-proxy cookbook polish (trusted headers, HTTPS cookie Secure).
3. Forge legacy path cleanup helper (`adhd-hub/wiki/**` → root `projects/`).
4. Backup schedule docs + optional encrypted backup passphrase.
5. `doctor` remote checks: forge reachability, OpenClaw test hook, indexer last run.

## Wave 4 — Design system & maintainability

1. Split `app.js` by screen (now / work / progress / settings / share).
2. Facades for forge/openclaw out of `HubService` without behaviour change.
3. A11y pass: focus order, live regions for save confirmations, chart alternatives.
4. Prefer calm motion only; no streak guilt or competitive UI.

## Wave 5 — Optional integrations (explicit opt-in)

Only after Waves 0–2 feel stable:

| Integration | Fit | Constraint |
|-------------|-----|------------|
| Slack / Discord | Gentle stale nudge parallel to OpenClaw | Same anti-nag policy |
| Linear / GitHub Projects already partial | Import issues as threads | Never auto-close remote |
| Calendar | Reminder due → calendar block | Local-first; no public calendars by default |
| Public leaderboard | See [rewards-roadmap.md](../rewards-roadmap.md) | Separate identity + ledger review |

## Verification per wave

- `uv run pytest` + `uv run ruff check src tests`
- `scripts/browser_smoke.py` for UI waves
- `scripts/probe_mcp.py` for MCP waves
- Manual: `curl …/install.sh` + `adhd-hub doctor` on a clean temp home

## Rollback

- Wire-up writes are idempotent and scoped; uninstall via `adhd-hub setup --uninstall` and documented MCP key removal.
- Feature flags / prefs stay opt-in; forge and OpenClaw remain disableable in Settings.

## Status

| Wave | Status |
|------|--------|
| 0 Client wire-up | Shipped in 0.3.5 |
| 1 ADHD UX depth | Merged (PR #22 / issue #16) |
| 2 MCP parity | This PR — branch `cursor/wave2-mcp-parity-5570` / issue #17 |
| 3–5 | Planned |

Waves 1 and 2 are intended for the **same release** after Wave 2 merges.
