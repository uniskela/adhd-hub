# Install ADHD Progress Hub

ADHD Progress Hub is a self-hosted server. For a persistent home server or VPS, **Docker Compose with a published image is the recommended install**. Running from source with `uv` is useful for development, and the standalone CLI can be installed separately on machines that only need to connect coding agents to an existing Hub.

## Choose an install method

| Method | Best for | Updates |
| --- | --- | --- |
| Docker Compose + published image | Recommended self-hosted server | `docker compose pull && docker compose up -d` |
| Docker Compose + local build | Developing an unreleased checkout | Rebuild from the checkout |
| `docker run` | Small/simple container deployments | Pull and recreate the container |
| Source + `uv` | Development or non-container server | Pull source, `uv sync`, restart |
| `uv tool install` | Client CLI only | Re-run with `--upgrade` |

ADHD Hub requires a persistent data directory. In the container image that directory is `/data`; do not run the server without a persistent volume if you care about its threads, wiki, preferences, sessions, and local configuration.

## Docker Compose with a published image

Create a directory for the deployment:

```bash
mkdir adhd-hub
cd adhd-hub
```

Create `.env` with at least a strong server token:

```env
ADHD_HUB_AUTH_TOKEN=replace-with-a-long-random-value
# Set this when browsers/agents reach the Hub through another hostname or URL:
# ADHD_HUB_PUBLIC_URL=https://adhd-hub.example.com
```

Generate a token with Python if needed:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Create `compose.yml`:

```yaml
services:
  adhd-hub:
    image: ghcr.io/uniskela/adhd-hub:latest
    container_name: adhd-hub
    restart: unless-stopped
    ports:
      - "8787:8787"
    env_file:
      - .env
    environment:
      ADHD_HUB_HOST: "0.0.0.0"
      ADHD_HUB_PORT: "8787"
      ADHD_HUB_DATA_DIR: /data
    volumes:
      - adhd_hub_data:/data

volumes:
  adhd_hub_data:
```

The same release tags are also published as `docker.io/uniskela/adhd-hub`. Release images are available as `latest`, `X.Y.Z`, and `X.Y`. Pin an `X.Y.Z` tag if you want upgrades to happen only when you deliberately change the image tag.

Start the Hub and check it:

```bash
docker compose up -d
docker compose logs -f adhd-hub
curl -fsS http://127.0.0.1:8787/api/health
```

Then open `http://<host>:8787/ui/`. Sign in with `ADHD_HUB_AUTH_TOKEN` for initial setup/recovery and create a dashboard password for normal browser use. See [Authentication](authentication.md).

### Host port versus container port

The Compose `environment:` block above deliberately pins the **container** to `0.0.0.0:8787` and `/data`. Values in `environment:` override the same names from `env_file`.

To expose the Hub on host port `9000`, change only the port mapping:

```yaml
ports:
  - "9000:8787"
```

Do not set `ADHD_HUB_PORT=9000` in `.env` while the Compose file still overrides it to `8787`.

## Use the repository Compose file

The repository's `docker-compose.yml` is convenient when you cloned the source tree. It contains `build: .`, so it builds the current checkout and tags that local build with the current project version.

```bash
git clone https://github.com/uniskela/adhd-hub.git
cd adhd-hub
cp .env.example .env
# Edit ADHD_HUB_AUTH_TOKEN before exposing the service.
docker compose up -d --build
```

For a normal server that should consume released images without a source checkout, prefer the published-image Compose example above.

## Plain `docker run`

A named volume provides the same persistent `/data` storage:

```bash
docker volume create adhd_hub_data

docker run -d \
  --name adhd-hub \
  --restart unless-stopped \
  -p 8787:8787 \
  --env-file .env \
  -e ADHD_HUB_HOST=0.0.0.0 \
  -e ADHD_HUB_PORT=8787 \
  -e ADHD_HUB_DATA_DIR=/data \
  -v adhd_hub_data:/data \
  ghcr.io/uniskela/adhd-hub:latest
```

## Run the server from source with `uv`

Python **3.12 or newer** is required. ADHD Hub is not currently published on PyPI.

```bash
git clone https://github.com/uniskela/adhd-hub.git
cd adhd-hub
cp .env.example .env
# Edit ADHD_HUB_AUTH_TOKEN.
uv sync
uv run adhd-hub serve --host 127.0.0.1 --port 8787
```

Use `127.0.0.1` for a local-only server. If you deliberately bind outside loopback, set a strong token first and use a trusted private network or HTTPS reverse proxy.

## Install only the client CLI

Machines that connect Cursor/Codex/Claude to an already-running Hub do not need to run the server. Install the CLI from GitHub:

```bash
uv tool install "git+https://github.com/uniskela/adhd-hub.git"
```

Or use the Hub's [Connect one-liner](connect.md), which prefers a wheel served by the running Hub and falls back to GitHub. `adhd-hub` is not currently on PyPI.

## Configuration

All server settings use the `ADHD_HUB_` prefix. Start with `.env.example`, then use the [Environment variables reference](environment-variables.md) for every supported setting and its default.

Settings precedence is:

1. process environment variables;
2. the first non-empty TOML config found from `--config`, `./config.toml`, then `~/.config/adhd-hub/config.toml`;
3. `./.env`;
4. built-in defaults.

For Docker Compose, remember that a service's explicit `environment:` entries override values loaded through `env_file`.

## Reverse proxy, HTTPS, and Tailscale

When browsers or agents reach the Hub through another URL, set `ADHD_HUB_PUBLIC_URL` to that external base URL. This is also used for MCP OAuth discovery.

Behind Caddy, nginx, Tailscale Serve, or another trusted TLS terminator:

```env
ADHD_HUB_PUBLIC_URL=https://adhd-hub.example.com
ADHD_HUB_TRUST_PROXY_HEADERS=true
# Optional if you want to force Secure cookies:
# ADHD_HUB_COOKIE_SECURE=true
```

Only trust forwarded headers from a proxy you control. For a Proxmox/Tailscale layout, migration instructions, and homelab-specific networking, see [Homelab deployment](deploy-homelab.md).

## Connect coding agents after the server is running

Open **Settings → Agents & install** and copy the generated command, or run the CLI directly:

```bash
adhd-hub connect /path/to/project \
  --hub http://<hub-host>:8787 \
  --agents cursor,codex,claude

adhd-hub doctor \
  --hub http://<hub-host>:8787 \
  --project /path/to/project
```

See [Connect a machine or project](connect.md) for browser login, MCP OAuth, skills, agent selection, and doctor output.

## Upgrade a container install

With a published image:

```bash
docker compose pull
docker compose up -d
docker compose logs --tail=100 adhd-hub
curl -fsS http://127.0.0.1:8787/api/health
```

A named/bind-mounted `/data` volume survives container replacement. Do not remove that volume during a normal upgrade.

For a local-build checkout:

```bash
git pull --ff-only
docker compose up -d --build
```

## Back up before important changes

Use **Settings → Download backup** or the CLI export before a major upgrade/migration. Keep `/data` persistent and backed up as well. The [Homelab deployment](deploy-homelab.md#7-move-an-existing-local-hub-to-this-lxc) guide covers a full instance migration and encrypted exports.
