# Connect a machine or project in one step

Point coding agents at a running ADHD Progress Hub without hand-editing every config file.

## One-liner (piggybacks on the Hub)

On the Hub host, set `ADHD_HUB_PUBLIC_URL` to the URL clients should use (for example a Tailscale address). The Hub serves two public, token-free bootstraps:

### macOS / Linux / WSL / Git Bash

```bash
export ADHD_HUB_AUTH_TOKEN=...   # keep this in your environment; the script never embeds it
curl -fsSL "$ADHD_HUB_PUBLIC_URL/install.sh" | sh -s -- /path/to/project
# optional flags:
curl -fsSL "$ADHD_HUB_PUBLIC_URL/install.sh" | sh -s -- /path/to/project --register --dry-run
curl -fsSL "$ADHD_HUB_PUBLIC_URL/install.sh" | sh -s -- /path/to/project --agents cursor,codex --openclaw-skills
```

### Windows PowerShell

Prefer download-then-run (more reliable when `iex` is blocked by policy):

```powershell
$env:ADHD_HUB_AUTH_TOKEN = "..."
iwr "$env:ADHD_HUB_PUBLIC_URL/install.ps1" -OutFile $env:TEMP\adhd-hub-install.ps1
powershell -ExecutionPolicy Bypass -File $env:TEMP\adhd-hub-install.ps1 -Project 'C:\path\to\project' -Register
```

One-liner (when `iex` is allowed):

```powershell
$env:ADHD_HUB_AUTH_TOKEN = "..."
iex "& { $(irm $env:ADHD_HUB_PUBLIC_URL/install.ps1) } -Project 'C:\path\to\project' -Register -DryRun"
```

Both scripts look for `adhd-hub` or `uvx` on `PATH`, then run `adhd-hub connect` with the Hub URL baked in. Prefer `uv tool install adhd-hub` once per machine.

Install-script flags (also via env): `--agents`, `--scope`, `--register`, `--openclaw-skills`, `--no-skills`, `--no-cursor-rule`, `--dry-run`, plus `ADHD_HUB_CONNECT_FLAGS` for extras.

## CLI

```bash
adhd-hub connect /path/to/project \
  --hub http://100.x.x.x:8787 \
  --agents cursor,codex \
  --scope project \
  --cursor-rule \
  --skills \
  --openclaw-skills \
  --register \
  --find-roots ~/Projects

# Preview without writing files or registering:
adhd-hub connect /path/to/project --hub http://100.x.x.x:8787 --cursor-rule --skills --dry-run

adhd-hub doctor --hub http://100.x.x.x:8787 --project /path/to/project
```

### What connect configures

- **Cursor MCP** — project `.cursor/mcp.json` or user `~/.cursor/mcp.json` (`--scope user`), using `${env:ADHD_HUB_AUTH_TOKEN}`
- **Codex / Claude** — optional MCP blocks when listed in `--agents`
- **Cursor rule** — `.cursor/rules/adhd-hub.mdc` with `--cursor-rule`
- **AGENTS.md** — same reversible managed block as `adhd-hub setup`
- **Skills** — opt-in global `npx skills add` (`--skills`)
- **OpenClaw skills** — opt-in `npx skills add … -a openclaw`; hook URL/token still configured in **Settings → Connections**
- **Register** — `GET /api/projects/resolve?create=true` when a bearer token is available
- **Find** — scan `--find-roots` for `.git` / `AGENTS.md` / `.cursor` folders and list them

`adhd-hub setup` remains available for AGENTS-only installs.

## Safety

- Never commits Hub URLs or tokens into `AGENTS.md`
- Refuses to overwrite symlinks
- Merges only the `adhd-hub` MCP server key; other MCP servers stay untouched
- OpenClaw gateway secrets are not written by the one-liner; use the Hub UI or Hub-server env

See the [improvement roadmap](plans/improvement-roadmap.md) Wave 0 for status and follow-ons.
