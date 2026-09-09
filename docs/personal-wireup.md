# Personal wire-up checklist

## Day in the life

1. **Hub running** — Docker or `uv run adhd-hub serve` on `:8787`.
2. **Connect once** — prefer the [Connect one-liner](connect.md) so MCP, `AGENTS.md`, Cursor rule, and optional skills land together:

```bash
# macOS / Linux / WSL
export ADHD_HUB_AUTH_TOKEN=...
curl -fsSL http://127.0.0.1:8787/install.sh | sh -s -- /path/to/project
```

```powershell
# Windows PowerShell
$env:ADHD_HUB_AUTH_TOKEN = "..."
irm http://127.0.0.1:8787/install.ps1 | iex
```

```bash
adhd-hub doctor --project /path/to/project
```

3. **Skills (global)** if you skipped `--skills` on connect:

```powershell
# Install from GitHub (recommended):
npx skills add uniskela/adhd-hub -g
# Or, while developing an unreleased local checkout:
cd Z:\Projects\adhd-hub
npx skills add ./skills -g
```

4. **Start a coding session** in any project — agent should `resolve_project` → `session_digest` → `check_overlap`.
5. **Pause unfinished work** — `upsert_progress` with one **Now**, short Done/Next lists, Waiting/blocked, and a **Return cue**. See [ADHD-friendly writing and planning](adhd-friendly-writing.md).
6. **Review** — open `http://127.0.0.1:8787/ui`, filter by project, check Stale, open Gitea issues if board sync is on.
7. **Indexer backstop** (optional daily): see [indexer-schedule.md](indexer-schedule.md).

## Optional OpenClaw check-in

If OpenClaw is part of your setup, install the same skills there:

```bash
npx skills add uniskela/adhd-hub -g -a openclaw
```

Then connect the Hub to OpenClaw's private hooks for one gentle daily stale-work reminder. The short setup and safe test are in [OpenClaw connection and alerts](openclaw.md).

## Local smoke (Windows)

```powershell
cd Z:\Projects\adhd-hub
copy .env.example .env
# Edit .env: ADHD_HUB_AUTH_TOKEN, optional ADHD_HUB_PUBLIC_URL
copy .cursor\mcp.json.example .cursor\mcp.json   # if present
uv run adhd-hub serve --host 127.0.0.1 --port 8787
```

Or Docker:

```powershell
docker compose up -d --build
```

## Cursor hooks (optional)

See [adapters/cursor-hooks.md](../adapters/cursor-hooks.md) — sessionStart/stop prompts that nudge digest + progress writes.

## Deploy to lab

```powershell
.\scripts\sync-and-deploy.ps1 -HostName root@100.115.187.7 -RemoteDir /opt/adhd-hub
```

Then set MCP URL to `http://<tailscale-ip>:8787/mcp` and `ADHD_HUB_PUBLIC_URL` to that base for README → `/ui` links.
