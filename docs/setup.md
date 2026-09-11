# Personal wire-up checklist

## Day in the life

1. **Hub running** — Docker or `uv run adhd-hub serve` on `:8787`.
2. **Connect once** — prefer the [Connect one-liner](connect.md). Copy it from **Settings → Connections**; do not export the server token into your shell. For MCP clients with an **Auth** / **Authenticate** button, set Hub `ADHD_HUB_PUBLIC_URL` and leave Hub OAuth enabled (default); Approve = Hub UI sign-in + **Allow**. Static `ADHD_HUB_AUTH_TOKEN` Bearer and CLI connect still work; set Hub `ADHD_HUB_OAUTH_ENABLED=false` to disable discovery/OAuth routes. Details: [Connect — MCP Auth / Authenticate](connect.md#mcp-auth--authenticate-oauth).

```bash
# macOS / Linux / WSL
curl -fsSL http://127.0.0.1:8787/install.sh | sh -s -- /path/to/project
```

```powershell
# Windows PowerShell
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

4. **Optional coding companions** (i-have-adhd, Graphify, RTK, Superpowers, Context7, agent-browser, Serena) — toggle under **Settings → Connections**, or see [Recommended coding companions](coding-companions.md).
5. **Start a coding session** in any project — skip Hub tools for trivial/read-only questions and tiny edits. For substantial work: once per session `resolve_project` → `session_digest`, then `check_overlap` before duplicating a thread. See [project agent setup](project-agent-setup.md).
6. **Pause unfinished work** — `upsert_progress` with one **Now**, short Done/Next lists, Waiting/blocked, and a **Return cue**. See [ADHD-friendly writing and planning](writing.md).
7. **Review** — open `http://127.0.0.1:8787/ui`, filter by project, check Stale, open Gitea issues if board sync is on.
8. **Indexer backstop** (optional daily): see [indexer-schedule.md](indexer-schedule.md).

## Optional OpenClaw check-in

If OpenClaw is part of your setup, install the same skills there:

```bash
npx skills add uniskela/adhd-hub -g -a openclaw
```

Then pair from **Settings → Connections → OpenClaw** (recommended): **Start OpenClaw pairing**, paste the prompt into OpenClaw, and **Approve**. Manual webhook/token (and `.env`) remains available. Full steps: [OpenClaw connection and alerts](openclaw.md).

## Local smoke (Windows)

```powershell
cd Z:\Projects\adhd-hub
copy .env.example .env
# Edit .env: ADHD_HUB_AUTH_TOKEN, optional ADHD_HUB_PUBLIC_URL
# (and ADHD_HUB_OAUTH_ENABLED=false only if you need Bearer-only rollback)
copy .cursor\mcp.json.example .cursor\mcp.json   # if present
uv run adhd-hub serve --host 127.0.0.1 --port 8787
```

Or Docker:

```powershell
docker compose up -d --build
```

## Cursor hooks (optional)

See [adapters/cursor-hooks.md](https://github.com/uniskela/adhd-hub/blob/main/adapters/cursor-hooks.md) — sessionStart/stop prompts that nudge digest + progress writes.

## Deploy to lab

```powershell
.\scripts\sync-and-deploy.ps1 -HostName root@100.115.187.7 -RemoteDir /opt/adhd-hub
```

Then set MCP URL to `http://<tailscale-ip>:8787/mcp` and `ADHD_HUB_PUBLIC_URL` to that base for README → `/ui` links.
