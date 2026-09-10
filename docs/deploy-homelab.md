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

### Reverse proxy / HTTPS cookies

If you terminate TLS in front of the Hub (Caddy, nginx, Tailscale Serve):

1. Set `ADHD_HUB_PUBLIC_URL` to the **https** URL browsers use.
2. Set `ADHD_HUB_TRUST_PROXY_HEADERS=true` so login cookies get the `Secure` flag from `X-Forwarded-Proto: https`.
3. Optionally force cookies with `ADHD_HUB_COOKIE_SECURE=true`.
4. Only trust those headers from your proxy — do not expose the Hub directly to the public internet with proxy trust enabled.

Installable PWA: open `/ui/` over HTTPS (or localhost), then “Install app” / Add to Home Screen. The service worker caches the UI shell only — never `/api` or MCP.

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

## 7. Move an existing local hub to this LXC

Two complementary paths:

### A. Full instance migrate (SQLite threads + wiki + forge prefs)

On the old machine (UI or CLI):

1. `/ui` → Settings → **Download backup**, or `uv run adhd-hub export -o adhd-hub-backup.zip`
   - Optional encryption: `uv run adhd-hub export -o adhd-hub-backup.zip.enc --passphrase '…'`
2. Copy the zip to the LXC (scp / Tailscale)
3. On the LXC: **stop** the container, restore into the data volume, start again:

```bash
# Example: compose volume at ./data
docker compose stop
uv run adhd-hub import /path/to/adhd-hub-backup.zip
# Encrypted:
# uv run adhd-hub import /path/to/adhd-hub-backup.zip.enc --passphrase '…'
# Prefer CLI import while the server is stopped so SQLite is not open.
docker compose up -d
```

Schedule backups however you like (cron / Task Scheduler) — weekly export of `data/` is enough for most homelabs. Encrypted exports are safe to park on shared storage.

Encrypted files are a versioned envelope around the zip (magic `ADHDHUB1`), not a password-zip. New exports derive the Fernet key with **scrypt** (random salt, stored in the header). Backups created before this upgrade used a single SHA-256 of a fixed prefix plus the passphrase (v1); those still restore with the same passphrase. The HTTP restore path still rejects archives over 80 MiB.

Keep the same `ADHD_HUB_AUTH_TOKEN` (or update MCP clients). Point `ADHD_HUB_PUBLIC_URL` at the Tailscale IP.

### Legacy forge wiki paths

If an older Hub used `wiki_path = "adhd-hub/wiki"`, migrate local config to repo-root `projects/`:

```bash
uv run adhd-hub forge-wiki-paths          # dry-run
uv run adhd-hub forge-wiki-paths --apply  # write forge.json / project overrides
```

Move remote files under the forge repo separately (`adhd-hub/wiki/projects/` → `projects/`).

### B. Forge-first (wiki already on Gitea/GitHub)

If the memory repo already has `projects/*/PROGRESS.md`:

1. Deploy a fresh hub on the LXC
2. Configure the same forge in `/ui` Settings (or `ADHD_HUB_FORGE_*`)
3. Save forge / **Scan for import** — the UI lists remote projects missing from this hub
4. **Import** registers projects and pulls progress files

Forge import does **not** recreate SQLite threads/reminders; use Export/Import (A) when you need the full local history.

## 8. Smoke test

```bash
TOKEN=...
curl -s -H "Authorization: Bearer $TOKEN" -X POST http://<ts-ip>:8787/api/threads \
  -H 'Content-Type: application/json' \
  -d '{"summary":"Finish openclaw Valkey upgrade","project_slug":"openclaw-valkey","source_tool":"manual"}'

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://<ts-ip>:8787/api/overlap?q=openclaw%20valkey"
```

In Cursor, start a chat about that migration and confirm `check_overlap` / `session_digest` surface the thread.
