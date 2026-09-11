# ADHD Progress Hub

[![Coded with Codex](https://vibecoded.fyi/badges/terminal/agents/codex.svg)](https://vibecoded.fyi/)
[![Coded with Cursor](https://vibecoded.fyi/badges/terminal/agents/cursor.svg)](https://vibecoded.fyi/)

Self-hosted **source of truth** for half-finished plans, migrations, and setups — so coding agents (Cursor, Codex, Claude Code, …) can check overlap, save progress, and nudge you later.

Inspired by [claude-adhd](https://github.com/shaheer-00/claude-adhd) (see [ATTRIBUTION.md](ATTRIBUTION.md)). This project is **tool-agnostic**: MCP + REST hub, optional OpenClaw notifications, optional local transcript indexer (summaries only).

## Why

You start a Proxmox migration / homelab setup / refactor in Cursor Cloud, continue on a Dev LXC, forget for a week, then rediscover a half-finished chat — or you don’t. The hub keeps:

- **Threads** — open / blocked / done / dismissed work items  
- **Progress wiki** — `data/wiki/projects/<slug>/PROGRESS.md`  
- **Overlap checks** — “am I about to redo something half-done?”  
- **Reminders** — once / session / daily / random  
- **OpenClaw bridge** (optional) — chat nudges + memory sync when you’re away from the IDE  

## Quick start

### `uv` / `uvx`

```bash
cp .env.example .env   # set ADHD_HUB_AUTH_TOKEN
uv sync
uv run adhd-hub serve --host 127.0.0.1 --port 8787
```

### Docker

```bash
cp .env.example .env   # set a real token
docker compose up -d --build
curl -s http://127.0.0.1:8787/api/health
```

Published images (only after a manual release-PR merge by `uniskela`):

- `:latest`, `X.Y.Z`, and `X.Y` on the Git tag created for that release (for example `0.3.1`, `0.3`)

**Releases (Release Please):** after `uniskela` manually merges a PR to `main` with [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `feat!:`…), Release Please opens or updates a release PR. It never auto-merges that PR. When `uniskela` manually merges the release PR, Release Please creates `vX.Y.Z` and then publishes the matching multi-architecture images. The publish workflow has no direct `push`, PR, or manual trigger.

Documentation, chore, test, and CI-only merges do not open a release PR, even if their subject accidentally starts with `feat:`. A feature, fix, performance, revert, or explicit breaking-change subject reaches Release Please only when that commit changes a shipped runtime surface (`src/`, package metadata/lockfile, `Dockerfile`, or `docker-compose.yml`). A generated release PR continues through the tag-and-publish step after `uniskela` manually merges it.

```bash
docker pull ghcr.io/uniskela/adhd-hub:latest
docker pull ghcr.io/uniskela/adhd-hub:1.2.3
```

Repo secrets for Docker Hub: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`. GHCR uses `GITHUB_TOKEN` (packages: write).

### Connect Cursor

Merge [adapters/cursor-mcp.json](adapters/cursor-mcp.json) into your MCP config (update URL + bearer token).  
Install the rule from [adapters/cursor-rule.mdc](adapters/cursor-rule.mdc) into `.cursor/rules/` (user or project).

**Skills (recommended, all agents):**

```bash
# Install from the published repository:
npx skills add uniskela/adhd-hub -g
# Or, while developing an unreleased local checkout:
npx skills add ./skills -g
```

For calm, resumable project notes and plans, use the [ADHD-friendly writing guide](docs/writing.md): one visible **Now** action, brief context, and a concrete return cue.

**Documentation site:** enable **Settings → Pages → GitHub Actions** to publish [the public docs portal](https://uniskela.github.io/adhd-hub/) (built with [Zensical](https://zensical.org/)). Preview locally with `uv sync --extra dev && uv run zensical serve`. The workflow deploys only from `main` after `uniskela` merges documentation changes; it does not run for pull requests or manual dispatches.

MCP endpoint: `http://<host>:8787/mcp`  
REST docs: `http://<host>:8787/docs`  
UI: `http://<host>:8787/ui/`

## MCP tools

| Tool | Purpose |
|------|---------|
| `session_digest` | Stale/open threads + due reminders + wiki snippet |
| `check_overlap` | Rank open threads vs what you’re starting |
| `resolve_project` | Map workspace path → project slug |
| `list_projects` / `upsert_project` | Project registry (+ optional forge overrides) |
| `rename_project` / `delete_project` | Queue rename/delete for **/ui confirmation** (not applied immediately) |
| `list_pending_actions` | See delete/rename requests waiting for you |
| `list_open_threads` | List unfinished work |
| `upsert_thread` | Create/update a thread |
| `upsert_progress` | Append to PROGRESS.md (+ keep thread open) |
| `mark_done` | Close a thread |
| `set_reminder` | once / session / daily / random |

## Optional OpenClaw

Install the Hub skills for OpenClaw:

```bash
npx skills add uniskela/adhd-hub -g -a openclaw
```

**Pairing (recommended):** In **Settings → Connections → OpenClaw**, click **Start OpenClaw pairing**, copy the prompt into OpenClaw, then **Approve** what it submits. OpenClaw never needs `ADHD_HUB_AUTH_TOKEN` — only the short pairing code. Full steps: [OpenClaw connection and alerts](docs/openclaw.md).

**Manual path:** Enable private hooks on the OpenClaw gateway. Then in the same Connections panel, save the webhook or agent URL, bearer token, alert schedule, stale age, cooldown, and alert size. Use **Save & send test** to verify the route.

The bearer token is encrypted before it is written to the Hub data directory and is never returned to the browser. Environment variables remain available for initial provisioning:

```env
ADHD_HUB_OPENCLAW_WEBHOOK_URL=http://openclaw:18789/hooks/wake
ADHD_HUB_OPENCLAW_TOKEN=<OpenClaw hook bearer token>
# optional richer path:
# ADHD_HUB_OPENCLAW_AGENT_URL=http://openclaw:18789/hooks/agent
```

Environment changes require a restart; web UI changes apply immediately. The stale-work job sends OpenClaw one concise, non-nagging reminder and stays quiet when there is no stale work. Keep both services on your LAN or Tailscale. See [the OpenClaw guide](docs/openclaw.md) for details.

## Optional transcript indexer

On a machine that has local transcripts (does **not** upload raw chats — only heuristic summaries):

```bash
uv run adhd-hub index --dry-run
uv run adhd-hub index
```

Roots (override in `config.toml` `[indexer]`):

- Cursor: `~/.cursor/projects/**/agent-transcripts/**/*.jsonl`
- Codex: `~/.codex/sessions/**/*.jsonl`
- Claude Code: `~/.claude/projects/**/*.jsonl`

## Homelab / Tailscale

See [docs/deploy-homelab.md](docs/deploy-homelab.md). Typical pattern: Docker on Proxmox LXC, publish `:8787` on Tailscale, point Cursor Cloud + Windows + Dev LXC MCP clients at `http://<tailscale-ip>:8787/mcp`.

## Optional forge sync (GitHub / Gitea)

Open **http://127.0.0.1:8787/ui/** after `serve` / compose. Project-first dashboard: pick a project, do **Next up**, Settings (token / timezone / forge) stays out of the way. Timezone defaults to your browser local zone on first visit (`ADHD_HUB_TIMEZONE` / `data/prefs.json`).

- **Wiki sync** — pushes `INDEX.md` + `projects/<slug>/PROGRESS.md` (primary memory: **repo root**; otherwise under Wiki path)
- **Board sync** — mirrors threads as Issues with labels `adhd-hub` + `project:<slug>`; optionally attaches to a Gitea/GitHub project board id
- **Primary memory repo** — seeds `README.md` / `AGENTS.md`; leave **Wiki path blank** so files land at `projects/<slug>/` (e.g. `…/alex/projects/projects/adhd-hub`)
- **Import from forge** — if the repo already has `projects/*/PROGRESS.md`, Settings → Scan for import (or after Sync) offers to register missing projects and pull progress files

Configure in Settings or via `ADHD_HUB_FORGE_*` env / `data/forge.json`. Rename/delete projects from the project panel (delete is safe by default — progress/forge files only removed if you opt in).

**Note:** Hub “wiki” = normal markdown files in the repo (`INDEX.md`, `projects/*/PROGRESS.md`). That is separate from Gitea/GitHub’s built-in Wiki feature. Issues show under the Issues tab when board sync works. Projects boards only if you set a project id/number.

**Cloud / remote mailbox:** enable **Import cloud-agent issues (inbox)** and set **Inbox authors** (fail closed: empty allowlist imports nothing). The Hub polls open issues from those usernames that either have the `adhd-hub` label **or** a title starting with `[ADHD]` (Cursor Cloud, Codex/ChatGPT, Claude, etc.), creates threads, then closes them with `adhd-hub-synced` (never deletes). Title prefix is enough when agents cannot set labels. Optional `source:*` labels record the tool. See [docs/forge-issue-inbox.md](docs/forge-issue-inbox.md).

**PAT permissions:** see [docs/forge-permissions.md](docs/forge-permissions.md) for GitHub (fine-grained + classic) and Gitea scopes.

## Privacy

- Default store: SQLite + markdown wiki under `data/`  
- Auth: REST and MCP accept bearer tokens. `/ui/` supports a separate dashboard password, with `ADHD_HUB_AUTH_TOKEN` for initial setup and recovery. Both issue a 12-hour HttpOnly, SameSite=Strict session cookie; credentials are never stored in localStorage. See [password setup and recovery](docs/authentication.md). Log out revokes the session. Browser sessions are stored in SQLite (`data/browser_sessions.sqlite3`) and survive a restart; login throttles stay in process memory. HTTPS sets the Secure cookie flag (configure trusted proxy headers when terminating TLS upstream).
- Default-token development mode is allowed only with a loopback bind. Set a long random token before binding to `0.0.0.0`; generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Use HTTPS for remote access.
- Cookie-authenticated writes require `X-Hub-Request: 1` and a matching Origin when present. CLI and MCP clients continue using bearer auth.
- Settings precedence is process environment, then the first nonempty TOML file (`--config`, `./config.toml`, or `~/.config/adhd-hub/config.toml`), then `.env`. `ADHD_HUB_PUBLIC_URL` sets the external base URL used in forge links.
- Bind `127.0.0.1` for local-only, or Tailscale-only — do not expose publicly without a reverse proxy and strong token
- Migrate instances with `/ui` backup zip or forge **Import** (see [docs/deploy-homelab.md](docs/deploy-homelab.md)). Optional passphrase backups use a versioned envelope: new exports are salted scrypt + Fernet (v2); v1 SHA-256 passphrase files still decrypt.

## Adapters

| Tool | Snippet |
|------|---------|
| Cursor | [adapters/cursor-mcp.json](adapters/cursor-mcp.json), [adapters/cursor-rule.mdc](adapters/cursor-rule.mdc) |
| Codex | [adapters/codex.md](adapters/codex.md) |
| Claude Code | [adapters/claude-code.md](adapters/claude-code.md) |
| OpenClaw | [adapters/openclaw.md](adapters/openclaw.md) |

### Add Hub guidance to another project

Install a reversible, project-local `AGENTS.md` section that keeps coding-agent sessions connected to the Hub:

```bash
adhd-hub setup /path/to/project
```

Add `--install-skills` to also run `npx skills add uniskela/adhd-hub -g`, or pass `--skills-source /path/to/adhd-hub/skills` while developing locally. Skill installation is opt-in because it changes a global directory. See [project agent setup](docs/project-agent-setup.md).

## Connect (one-liner)

With the Hub running and `ADHD_HUB_PUBLIC_URL` set for remote clients, copy the command from **Settings → Connections** (no server token in the command):

```bash
# macOS / Linux / WSL / Git Bash
curl -fsSL http://<hub-host>:8787/install.sh | sh -s -- /path/to/project
```

```powershell
# Windows PowerShell
irm http://<hub-host>:8787/install.ps1 | iex
```

The CLI opens your browser (or prints a one-time code). Press **Allow this CLI**. A session is saved on disk; do not `export ADHD_HUB_AUTH_TOKEN` into your profile for this step.

Install scripts prefer this Hub's `/install/cli-wheel.url` (a PEP 427 wheel matching the server), falling back to `git+https`. Choose agents in **Settings → Connections** (baked into `/install.sh` and `/install.ps1`), or pass `--agents` / `ADHD_HUB_CONNECT_AGENTS`. Hub alias `claude` maps to skills.sh `claude-code`; there is no Cursor-only default. Details: [docs/connect.md](docs/connect.md).

```bash
adhd-hub doctor --hub http://<hub-host>:8787 --project /path/to/project
```

`adhd-hub connect` merges MCP configs, writes the reversible `AGENTS.md` block, and can install Cursor rules, global skills, OpenClaw skills, register the project, and scan `--find-roots`.

## Roadmap

Sequenced waves live in [docs/plans/improvement-roadmap.md](docs/plans/improvement-roadmap.md). Near-term highlights:

- **Wave 0 (shipped in 0.3.5):** Hub-backed `/install.sh` + `/install.ps1` + `adhd-hub connect` / `doctor`
- **Wave 1–2 (shipped in 0.3.6):** Soft-archive, reminders, focus mode; MCP parity + OpenClaw memory digest
- **Wave 3 (shipped in 0.3.7):** Durable sessions, proxy/Secure cookies, forge wiki-path cleanup, encrypted backups, doctor remote checks, installable PWA
- **Wave 4 (shipped in 0.3.8):** Maintainability, UI modules, and a11y
- **0.4.0 (shipped):** Connect agent prefs, Hub-served CLI wheel, and OpenClaw pairing
- Wave 5 (opt-in Slack/Discord/calendar) is still upcoming
- skills.sh listing after publish

### Dashboard comfort

The dashboard includes light/dark/system themes, a focus view, quick task capture, and optional XP, levels, and daily goals. See [dashboard preferences](docs/dashboard.md).

## Development

```bash
uv sync --all-extras
uv run pytest
uv run ruff check src tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — [LICENSE](LICENSE)

## Brand and rewards

See the [brand guide](docs/brand-guide.md) for the logo, colours, and UI patterns, and the [reward roadmap](docs/rewards-roadmap.md) for ranks, sharing, and the future leaderboard direction.
