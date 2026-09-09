# Connect a machine or project in one step

Point coding agents at a running ADHD Progress Hub without hand-editing every config file.

## One-liner (piggybacks on the Hub)

On the Hub host, set `ADHD_HUB_PUBLIC_URL` to the URL clients should use (for example a Tailscale address). Then from any trusted machine:

```bash
export ADHD_HUB_AUTH_TOKEN=...   # keep this in your environment; the script never embeds it
curl -fsSL "$ADHD_HUB_PUBLIC_URL/install.sh" | sh -s -- /path/to/project
```

`/install.sh` is public and token-free. It runs `adhd-hub connect` (or `uvx …`) with the Hub URL baked in.

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
