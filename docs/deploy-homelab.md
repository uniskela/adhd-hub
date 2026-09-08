# Deploy ADHD Hub on a homelab (Proxmox + Tailscale)

This matches the “hybrid” layout: **Docker hub on the lab** as source of truth; Cursor (Windows + Cloud), Codex, and a Dev LXC talk to it over **Tailscale** via MCP.

## 1. Create / pick an LXC

- New CT or reuse a Docker host (e.g. beside OpenClaw).
- Install Docker + Compose.
- Join Tailscale (`tailscale up`). Note the Tailscale IPv4.

## 2. Ship the app

From your Windows/dev machine (after Tailscale SSH auth works):

```bash
# Linux/macOS or Git Bash / WSL:
./scripts/sync-and-deploy.sh root@100.115.187.7 /opt/adhd-hub
```

Or manually on the Docker host:

```bash
git clone <your-repo> /opt/adhd-hub   # or rsync the tree
cd /opt/adhd-hub
cp .env.example .env
# Edit:
#   ADHD_HUB_AUTH_TOKEN=<long random>
#   ADHD_HUB_OPENCLAW_WEBHOOK_URL=http://<openclaw-host>:18789/hooks/wake
#   ADHD_HUB_OPENCLAW_TOKEN=<openclaw hooks token>
docker compose up -d --build
# Or pull a published image instead:
#   image: ghcr.io/uniskela/adhd-hub:latest  (see docker-compose.yml)
curl -s http://127.0.0.1:8787/api/health
```

Ensure the container port `8787` is reachable on the Tailscale interface (publish `8787:8787` is enough if the LXC’s Tailscale IP is used by clients).

**Note:** First Tailscale SSH from a new machine may require opening an auth URL in the browser (`login.tailscale.com/...`).

## 3. OpenClaw

On the OpenClaw gateway, enable hooks with a bearer token. Point hub env at `/hooks/wake` (and optionally `/hooks/agent`).  
Stale digests fire on `ADHD_HUB` cron (`stale_nudge_cron`, default `0 9 * * *`).

You can also have OpenClaw poll:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://adhd-hub:8787/api/threads?stale=true"
```

## 4. Clients

| Client | Config |
|--------|--------|
| Cursor Windows | MCP URL `http://<ts-ip>:8787/mcp` + Authorization header; install `adapters/cursor-rule.mdc` |
| Cursor Cloud | Same MCP URL (Cloud agent must reach Tailscale — MagicDNS / subnet router as needed) |
| Dev LXC | Same MCP URL from that host |
| Codex | See `adapters/codex.md` |

## 5. Local indexer (Windows)

Transcripts live on the PC; the hub may live on the lab:

```bash
# config.toml
hub_url = "http://<ts-ip>:8787"
auth_token = "..."

uv run adhd-hub index
```

Schedule via Task Scheduler if you want nightly capture.

## 6. Smoke test

```bash
TOKEN=...
curl -s -H "Authorization: Bearer $TOKEN" -X POST http://<ts-ip>:8787/api/threads \
  -H 'Content-Type: application/json' \
  -d '{"summary":"Finish openclaw Valkey upgrade","project_slug":"openclaw-valkey","source_tool":"manual"}'

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://<ts-ip>:8787/api/overlap?q=openclaw%20valkey"
```

In Cursor, start a chat about that migration and confirm `check_overlap` / `session_digest` surface the thread.
