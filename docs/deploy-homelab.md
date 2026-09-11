# Deploy ADHD Hub on a homelab (Proxmox + Tailscale)

This guide focuses on the **Proxmox/LXC + Tailscale** parts of a hybrid deployment: a Docker Hub instance in the lab is the source of truth, while Cursor (Windows + Cloud), Codex, and a Dev LXC talk to it over MCP.

For generic Docker Compose, published-image, `docker run`, source/`uv`, upgrade, and first-login instructions, start with [Install ADHD Progress Hub](installation.md). For every container/server setting, see [Environment variables](environment-variables.md).

## 1. Create or pick an LXC

- Create a new CT or reuse a Docker host (for example beside OpenClaw).
- Install Docker + Compose.
- Join Tailscale (`tailscale up`). Note the Tailscale IPv4/MagicDNS name you want clients to use.

## 2. Deploy the Hub

For a normal long-lived install, use the published-image Compose example from the [installation guide](installation.md#docker-compose-with-a-published-image) on the LXC.

If you are developing ADHD Hub itself and intentionally deploy the current checkout, the repository also has sync/build tooling. From your Windows/dev machine, after Tailscale SSH auth works:

```bash
# Linux/macOS or Git Bash / WSL:
./scripts/sync-and-deploy.sh root@100.115.187.7 /opt/adhd-hub
```

Or manually on the Docker host:

```bash
git clone <your-repo> /opt/adhd-hub   # or rsync the tree
cd /opt/adhd-hub
cp .env.example .env
# Edit at minimum:
#   ADHD_HUB_AUTH_TOKEN=<long random>
# Optional when OpenClaw is on the same/private network:
#   ADHD_HUB_OPENCLAW_WEBHOOK_URL=http://<openclaw-host>:18789/hooks/wake
#   ADHD_HUB_OPENCLAW_TOKEN=<openclaw hooks token>
docker compose up -d --build
curl -fsS http://127.0.0.1:8787/api/health
```

Ensure container port `8787` is reachable on the Tailscale interface. With the standard Compose mapping, clients use `http://<tailscale-ip>:8787` while the process still listens on `0.0.0.0:8787` inside the container.

### Reverse proxy / HTTPS cookies

If you terminate TLS in front of the Hub (Caddy, nginx, Tailscale Serve):

1. Set `ADHD_HUB_PUBLIC_URL` to the **https** URL browsers and agents use.
2. Set `ADHD_HUB_TRUST_PROXY_HEADERS=true` so login cookies can derive the Secure flag from `X-Forwarded-Proto: https`.
3. Optionally force Secure cookies with `ADHD_HUB_COOKIE_SECURE=true`.
4. Only trust those headers from your proxy — do not expose the Hub directly to the public internet with proxy trust enabled.

Installable PWA: open `/ui/` over HTTPS (or localhost), then use “Install app” / Add to Home Screen. The service worker caches the UI shell only — never `/api` or MCP.

**Note:** First Tailscale SSH from a new machine may require opening a Tailscale authentication URL in the browser.

## 3. OpenClaw

On the OpenClaw gateway, enable hooks with a bearer token, or use Hub pairing from **Settings → Connections → OpenClaw**. Point manual Hub configuration at `/hooks/wake` (and optionally `/hooks/agent`). Stale digests use `ADHD_HUB_STALE_NUDGE_CRON` (default `0 9 * * *`).

You can also have OpenClaw poll:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://adhd-hub:8787/api/threads?stale=true"
```

## 4. Clients

Prefer `adhd-hub connect` / the generated one-liner instead of hand-editing each client; see [Connect](connect.md).

| Client | Typical route |
|--------|---------------|
| Cursor Windows | MCP URL `http://<ts-ip>:8787/mcp` or HTTPS public URL |
| Cursor Cloud | Same MCP URL if the cloud agent can reach that private route; otherwise use the forge mailbox fallback |
| Dev LXC | Same MCP URL from that host |
| Codex / Claude | Connect CLI or their documented MCP configuration |

For MCP clients that support Auth/Authenticate, a correctly configured `ADHD_HUB_PUBLIC_URL` allows Hub OAuth discovery. Static Bearer auth remains supported.

## 5. Local indexer (Windows)

Transcripts normally live on the PC while the Hub lives in the lab. Run the indexer where those transcripts exist rather than mounting personal transcript directories into the server container:

```toml
# config.toml
hub_url = "http://<ts-ip>:8787"
auth_token = "..."
```

```bash
uv run adhd-hub index
```

Schedule it with Task Scheduler if you want nightly capture. See [Indexer schedule](indexer-schedule.md).

## 6. Back up the lab instance

Before upgrades or migrations, use `/ui` → Settings → **Download backup** or the CLI export. Keep the Compose `/data` volume persistent; removing that volume removes the local Hub state.

For regular container upgrades using a published image:

```bash
docker compose pull
docker compose up -d
curl -fsS http://127.0.0.1:8787/api/health
```

## 7. Move an existing local Hub to this LXC

Two complementary paths are available.

### A. Full instance migrate (SQLite threads + wiki + forge prefs)

On the old machine (UI or CLI):

1. `/ui` → Settings → **Download backup**, or `uv run adhd-hub export -o adhd-hub-backup.zip`.
   - Optional encryption: `uv run adhd-hub export -o adhd-hub-backup.zip.enc --passphrase '…'`
2. Copy the backup to the LXC (scp / Tailscale).
3. Stop the target Hub while restoring so SQLite is not open.

If you run the CLI on the host against a bind-mounted data directory, import directly there. With a named Docker volume, restore through the supported UI/import path or a temporary container/CLI environment that points `ADHD_HUB_DATA_DIR` at that volume; do not assume a named volume exists at `./data` on the host.

Encrypted files are a versioned envelope around the zip (magic `ADHDHUB1`), not a password-zip. New exports derive the Fernet key with **scrypt** using a random salt stored in the header. Older v1 encrypted backups still restore with the same passphrase. The HTTP restore path rejects archives over 80 MiB.

Keep the same `ADHD_HUB_AUTH_TOKEN` if you want existing static-Bearer clients to keep working, or reconnect/update those clients. Set `ADHD_HUB_PUBLIC_URL` to the final URL clients should use.

### Legacy forge wiki paths

If an older Hub used `wiki_path = "adhd-hub/wiki"`, migrate local config to repo-root `projects/`:

```bash
uv run adhd-hub forge-wiki-paths          # dry-run
uv run adhd-hub forge-wiki-paths --apply  # write forge.json / project overrides
```

Move remote files under the forge repo separately (`adhd-hub/wiki/projects/` → `projects/`).

### B. Forge-first (wiki already on Gitea/GitHub)

If the memory repo already has `projects/*/PROGRESS.md`:

1. Deploy a fresh Hub on the LXC.
2. Configure the same forge in `/ui` Settings (or `ADHD_HUB_FORGE_*`).
3. Save forge / **Scan for import** — the UI lists remote projects missing from this Hub.
4. **Import** registers projects and pulls progress files.

Forge import does **not** recreate SQLite threads/reminders; use Export/Import (A) when you need full local history.

## 8. Smoke test

First confirm health:

```bash
curl -fsS http://<ts-ip>:8787/api/health
```

Then run `adhd-hub doctor --hub http://<ts-ip>:8787 --project /path/to/project` from a client machine. If you want an API-level write test, use a CLI session or temporary Bearer token and create a disposable thread, then confirm `session_digest` / `check_overlap` can see it.
