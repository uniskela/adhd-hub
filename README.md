# ADHD Progress Hub

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

### Connect Cursor

Merge [adapters/cursor-mcp.json](adapters/cursor-mcp.json) into your MCP config (update URL + bearer token).  
Install the rule from [adapters/cursor-rule.mdc](adapters/cursor-rule.mdc) into `.cursor/rules/` (user or project).

**Skills (recommended, all agents):**

```bash
npx skills add ./skills -g
# After this repo is public on GitHub:
# npx skills add uniskela/adhd-hub -g
```

MCP endpoint: `http://<host>:8787/mcp`  
REST docs: `http://<host>:8787/docs`  
UI: `http://<host>:8787/ui`

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

Set in `.env` / config:

```env
ADHD_HUB_OPENCLAW_WEBHOOK_URL=http://openclaw:18789/hooks/wake
ADHD_HUB_OPENCLAW_TOKEN=shared-secret
# optional richer path:
# ADHD_HUB_OPENCLAW_AGENT_URL=http://openclaw:18789/hooks/agent
```

A daily cron inside the hub calls OpenClaw with stale open threads and rebuilds the wiki index.

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

Open **http://127.0.0.1:8787/ui** after `serve` / compose. Project-first dashboard: pick a project, do **Next up**, Settings (token / timezone / forge) stays out of the way. Timezone defaults to your browser local zone on first visit (`ADHD_HUB_TIMEZONE` / `data/prefs.json`).

- **Wiki sync** — pushes `INDEX.md` + `projects/<slug>/PROGRESS.md` (primary memory: **repo root**; otherwise under Wiki path)
- **Board sync** — mirrors threads as Issues with labels `adhd-hub` + `project:<slug>`; optionally attaches to a Gitea/GitHub project board id
- **Primary memory repo** — seeds `README.md` / `AGENTS.md`; leave **Wiki path blank** so files land at `projects/<slug>/` (e.g. `…/alex/projects/projects/adhd-hub`)

Configure in Settings or via `ADHD_HUB_FORGE_*` env / `data/forge.json`. Rename/delete projects from the project panel (delete is safe by default — progress/forge files only removed if you opt in).

**Note:** Hub “wiki” = normal markdown files in the repo (`INDEX.md`, `projects/*/PROGRESS.md`). That is separate from Gitea/GitHub’s built-in Wiki feature. Issues show under the Issues tab when board sync works. Projects boards only if you set a project id/number.

**PAT permissions:** see [docs/forge-permissions.md](docs/forge-permissions.md) for GitHub (fine-grained + classic) and Gitea scopes.

## Privacy

- Default store: SQLite + markdown wiki under `data/`  
- Auth: Bearer token (required when token ≠ `change-me`)  
- Bind `127.0.0.1` for local-only, or Tailscale-only — do not expose publicly without a reverse proxy and strong token  

## Adapters

| Tool | Snippet |
|------|---------|
| Cursor | [adapters/cursor-mcp.json](adapters/cursor-mcp.json), [adapters/cursor-rule.mdc](adapters/cursor-rule.mdc) |
| Codex | [adapters/codex.md](adapters/codex.md) |
| Claude Code | [adapters/claude-code.md](adapters/claude-code.md) |
| OpenClaw | [adapters/openclaw.md](adapters/openclaw.md) |

## Roadmap

- Import from forge tree — scan `projects/*/` on Gitea/GitHub and offer to register missing hub projects
- Archive instead of delete — soft-hide projects without clearing threads
- One-click “add this workspace” from MCP (title from folder + path + open thread defaults)
- Focus mode (timed task + drift policy; only-show-this-project)
- Reminder surface in `/ui` — due reminders alongside pending actions
- Cleanup helper for old forge path `adhd-hub/wiki/**` after root `projects/` migration
- Richer OpenClaw memory round-trips
- Hardening for multi-machine Tailscale deploy (Proxmox / Portainer)
- skills.sh listing after public GitHub publish

## Development

```bash
uv sync --all-extras
uv run pytest
uv run ruff check src tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — [LICENSE](LICENSE)
