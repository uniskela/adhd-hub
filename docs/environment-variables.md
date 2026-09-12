# Environment variables

ADHD Progress Hub server configuration uses the `ADHD_HUB_` prefix. This page documents every environment-backed field in the server `Settings` model, plus the additional runtime/client variables read directly outside that model. Developer-only smoke/probe variables are separated at the end so they are not mistaken for normal container configuration.

For a container install, put normal server settings in the `.env` file referenced by Compose. Do **not** put secrets in `compose.yml`, source control, `AGENTS.md`, issues, or progress notes.

## Configuration precedence

The server resolves `Settings` configuration in this order, highest priority first:

1. process environment variables (`ADHD_HUB_*`);
2. the first non-empty TOML config found from an explicit `--config`, `./config.toml`, then `~/.config/adhd-hub/config.toml`;
3. `./.env`;
4. built-in defaults.

Variables documented below as direct runtime/client overrides are read by their owning component and do not necessarily participate in that `Settings` precedence chain.

Docker Compose adds one more practical rule: values under a service's explicit `environment:` section override the same names loaded through `env_file`. The repository Compose file intentionally pins `ADHD_HUB_HOST=0.0.0.0`, `ADHD_HUB_PORT=8787`, and `ADHD_HUB_DATA_DIR=/data` inside the container.

Boolean values accept the normal Pydantic forms such as `true` / `false`, `1` / `0`, and similar common variants. Cron fields use standard five-field cron expressions.

## Core server and storage

| Variable | Default | Type | Purpose |
| --- | --- | --- | --- |
| `ADHD_HUB_HOST` | `127.0.0.1` | string | Address the server binds to. The container image/Compose uses `0.0.0.0` so Docker can publish the port. |
| `ADHD_HUB_PORT` | `8787` | integer | Port inside the process/container. In Compose, change the host side of `HOST:8787` instead of changing this unless you also change the container mapping. |
| `ADHD_HUB_DATA_DIR` | `./data` | path | SQLite databases, wiki, preferences, sessions, and local Hub data. The container image uses `/data`; persist it with a volume. |
| `ADHD_HUB_AUTH_TOKEN` | `change-me` | secret string | Server bearer token for REST/MCP plus dashboard setup/recovery. `change-me` is development-only; use a long random value before non-loopback exposure. |
| `ADHD_HUB_PUBLIC_URL` | unset | URL string | Externally reachable Hub base URL used for browser links, CORS-related behaviour, forge links, install/connect output, and MCP OAuth discovery. No trailing slash is needed. |
| `ADHD_HUB_HUB_URL` | unset | URL string | Client/indexer Hub URL fallback. Normally leave unset in the server container; `PUBLIC_URL` is the usual server-facing setting. |
| `ADHD_HUB_TIMEZONE` | `UTC` | IANA timezone | Default timezone, for example `Australia/Sydney`. The dashboard can also persist the operator preference. |

## Hub behaviour and limits

| Variable | Default | Type | Purpose |
| --- | --- | --- | --- |
| `ADHD_HUB_STALE_DAYS` | `3` | integer | Age in days used when deciding that unfinished work is stale. |
| `ADHD_HUB_DIGEST_LIMIT` | `5` | integer | Default maximum number of threads included in compact session/digest views. |
| `ADHD_HUB_OVERLAP_LIMIT` | `5` | integer | Maximum overlap candidates returned by default. |
| `ADHD_HUB_REMIND_COOLDOWN_DAYS` | `3` | integer | Cooldown between stale-work reminder nudges. |
| `ADHD_HUB_DIGEST_MAX_NUDGE` | `2` | integer | Maximum stale/nudge items included in a digest. |
| `ADHD_HUB_MAX_SESSIONS` | `50` | integer | Maximum local transcript sessions considered by an indexer run. |

## Scheduled jobs

| Variable | Default | Purpose |
| --- | --- | --- |
| `ADHD_HUB_STALE_NUDGE_CRON` | `0 9 * * *` | Schedule for stale-work/OpenClaw nudges. |
| `ADHD_HUB_WIKI_INDEX_CRON` | `30 9 * * *` | Schedule for rebuilding/synchronising the wiki index task. |
| `ADHD_HUB_FORGE_INBOX_CRON` | `*/15 * * * *` | Poll schedule for the forge issue inbox when enabled. |
| `ADHD_HUB_FORGE_RECONCILE_CRON` | `*/30 * * * *` | Poll schedule for pinned-identity repo reconcile when forge board sync is enabled. |

## Authentication, OAuth, and reverse proxies

| Variable | Default | Type | Purpose |
| --- | --- | --- | --- |
| `ADHD_HUB_OAUTH_ENABLED` | `true` | boolean | Enables MCP OAuth protected-resource/authorization discovery and `/api/oauth/*`. Static Bearer auth and CLI connect continue to work when disabled. |
| `ADHD_HUB_TRUST_PROXY_HEADERS` | `false` | boolean | Trusts forwarded scheme/host headers from a reverse proxy. Enable only when requests arrive through a proxy you control. |
| `ADHD_HUB_COOKIE_SECURE` | auto | boolean or unset | Forces the dashboard session cookie Secure flag when set. Unset means auto-detect HTTPS (including trusted forwarded proto when proxy trust is enabled). |

For a TLS reverse proxy, a typical configuration is:

```env
ADHD_HUB_PUBLIC_URL=https://adhd-hub.example.com
ADHD_HUB_TRUST_PROXY_HEADERS=true
# Optional hard override:
# ADHD_HUB_COOKIE_SECURE=true
```

See [Authentication](authentication.md) and [Installation](installation.md#reverse-proxy-https-and-tailscale).

## OpenClaw

These are optional. OpenClaw connection details can also be configured from **Settings → OpenClaw**; UI-saved configuration is intended for normal ongoing administration while environment variables are useful for initial provisioning.

| Variable | Default | Type | Purpose |
| --- | --- | --- | --- |
| `ADHD_HUB_OPENCLAW_WEBHOOK_URL` | unset | URL | OpenClaw wake webhook, commonly `http://openclaw:18789/hooks/wake` on a shared Docker network. |
| `ADHD_HUB_OPENCLAW_AGENT_URL` | unset | URL | Optional richer OpenClaw agent hook. |
| `ADHD_HUB_OPENCLAW_TOKEN` | unset | secret string | Bearer token used for the manual OpenClaw hook path. Pairing is preferred where available. |
| `ADHD_HUB_OPENCLAW_ALERTS_ENABLED` | `true` | boolean | Enables scheduled OpenClaw alerts when OpenClaw is configured. |

See [OpenClaw connection and alerts](openclaw.md).

## Forge: GitHub or Gitea

Forge settings can also be saved from the dashboard. Environment variables are useful for provisioning a fresh instance; do not commit PATs/tokens.

| Variable | Default | Type | Purpose |
| --- | --- | --- | --- |
| `ADHD_HUB_FORGE_PROVIDER` | `none` | `none`, `github`, or `gitea` | Forge backend. |
| `ADHD_HUB_FORGE_BASE_URL` | `https://api.github.com` | URL | Forge API base URL. Use the Gitea `/api/v1` base for Gitea. |
| `ADHD_HUB_FORGE_WEB_BASE_URL` | `https://github.com` | URL | Human-facing forge URL used to build links. |
| `ADHD_HUB_FORGE_TOKEN` | unset | secret string | GitHub/Gitea token. See the permissions guide for minimum scopes. |
| `ADHD_HUB_FORGE_OWNER` | unset | string | Repository owner/organisation. |
| `ADHD_HUB_FORGE_REPO` | unset | string | Repository name used for sync/inbox. |
| `ADHD_HUB_FORGE_WIKI_ENABLED` | `false` | boolean | Enables markdown progress/wiki synchronisation. |
| `ADHD_HUB_FORGE_WIKI_PATH` | `adhd-hub/wiki` | string | Remote path prefix. A blank path means repository root and is recommended for a primary-memory repository. |
| `ADHD_HUB_FORGE_WIKI_BRANCH` | `main` | string | Branch used for forge wiki/progress writes. |
| `ADHD_HUB_FORGE_PRIMARY_MEMORY_REPO` | `false` | boolean | Treats the forge repository as the primary markdown memory repository. |
| `ADHD_HUB_FORGE_BOARD_ENABLED` | `false` | boolean | Enables thread/issue board synchronisation. |
| `ADHD_HUB_FORGE_BOARD_INBOX_ENABLED` | `false` | boolean | Enables importing `[ADHD]` / `adhd-hub` issues as cloud-agent mailbox entries. |
| `ADHD_HUB_FORGE_BOARD_INBOX_SYNCED_LABEL` | `adhd-hub-synced` | string | Label applied after a mailbox issue is successfully imported. |
| `ADHD_HUB_FORGE_BOARD_INBOX_AUTHORS` | empty | comma-separated string | Allowlist of forge logins whose inbox issues may be imported. Empty fails closed. |
| `ADHD_HUB_FORGE_PROJECT_NUMBER` | unset | integer | GitHub project number when project-board integration is used. |
| `ADHD_HUB_FORGE_PROJECT_ID` | unset | string | Gitea project identifier when applicable. |

See [Forge permissions](forge-permissions.md) and [Forge issue inbox](forge-issue-inbox.md).

## Local transcript indexer paths

These paths are primarily for the CLI/indexer running on the machine that owns the transcripts. They are usually **not useful inside the server container** unless you deliberately mount those transcript directories into it.

| Variable | Default | Type | Purpose |
| --- | --- | --- | --- |
| `ADHD_HUB_CURSOR_PROJECTS_DIR` | unset | path | Override the Cursor projects/transcripts root. |
| `ADHD_HUB_CODEX_SESSIONS_DIR` | unset | path | Override the Codex sessions root. |
| `ADHD_HUB_CLAUDE_PROJECTS_DIR` | unset | path | Override the Claude Code projects root. |

The related `ADHD_HUB_MAX_SESSIONS` limit is documented under Hub behaviour above. See [Indexer schedule](indexer-schedule.md).

## Docker image / package-serving internals

The image sets a few implementation variables itself. They are not normal Hub configuration and usually should not be overridden:

| Variable | Image value | Purpose |
| --- | --- | --- |
| `ADHD_HUB_WHEEL_DIR` | `/app/dist` | Directory searched for the wheel served by the Hub-backed client installer. |
| `ADHD_HUB_WHEEL_PATH` | unset | Optional direct override to a specific wheel file. Primarily useful for packaging/development; normally leave unset in Docker. |
| `UV_OFFLINE` | `1` | Prevents the running container from re-resolving Python dependencies. |
| `UV_COMPILE_BYTECODE` | `1` | Build-time/runtime uv optimisation. |
| `UV_LINK_MODE` | `copy` | Keeps the image's uv environment independent of a uv cache link strategy. |

The image also defaults `ADHD_HUB_HOST=0.0.0.0`, `ADHD_HUB_PORT=8787`, and `ADHD_HUB_DATA_DIR=/data`; those three are normal Hub settings described above.

## Client/connect-only environment variables

The following variables affect the **client bootstrap/connect command or CLI**, not the long-running Docker server. Do not add them to the server container unless you intentionally run client tooling there.

- `ADHD_HUB_URL` — extra CLI Hub-URL fallback; `ADHD_HUB_PUBLIC_URL` and `ADHD_HUB_HUB_URL` are preferred where applicable.
- `ADHD_HUB_CREDENTIALS` — override the local CLI credentials/session JSON path.
- `ADHD_HUB_NO_COLOR` — disable Hub CLI status colouring when non-empty. Standard `NO_COLOR` is also respected.
- `ADHD_HUB_CONNECT_AGENTS` — default comma-separated agent targets for generated install scripts.
- `ADHD_HUB_CONNECT_SCOPE` — `project` or `user` Cursor MCP scope.
- `ADHD_HUB_CONNECT_REGISTER` — opt into project registration.
- `ADHD_HUB_CONNECT_OPENCLAW_SKILLS` — opt into OpenClaw skill installation.
- `ADHD_HUB_CONNECT_NO_SKILLS` — skip Hub skill installation in the bootstrap script.
- `ADHD_HUB_CONNECT_DRY_RUN` — preview connect changes.
- `ADHD_HUB_CONNECT_FLAGS` — additional generated-script CLI flags.
- `ADHD_HUB_CONNECT_WITH_I_HAVE_ADHD`, `ADHD_HUB_CONNECT_WITH_GRAPHIFY`, `ADHD_HUB_CONNECT_WITH_RTK`, `ADHD_HUB_CONNECT_WITH_SUPERPOWERS`, `ADHD_HUB_CONNECT_WITH_CONTEXT7`, `ADHD_HUB_CONNECT_WITH_AGENT_BROWSER`, `ADHD_HUB_CONNECT_WITH_SERENA` — opt-in companion defaults.

See [Connect a machine or project](connect.md) for the supported CLI/bootstrap workflow.

## Developer and smoke-test-only variables

These are read by repository utility scripts rather than the running Hub service and normally do **not** belong in a Docker `.env`:

- `ADHD_HUB_MCP_URL` — MCP endpoint override for `scripts/probe_mcp.py` (default `http://127.0.0.1:8787/mcp`).
- `ADHD_HUB_SCREENSHOT_DIR` — output directory used by `scripts/browser_smoke.py`.
- `ADHD_HUB_BROWSER_EXECUTABLE` — optional browser executable override for `scripts/browser_smoke.py`.

## When changes take effect

Environment and TOML changes require restarting the server/container. Settings saved through the dashboard are designed to apply through the Hub's persisted preferences/configuration path and generally do not require editing `.env`.

For Compose:

```bash
docker compose up -d
```

recreates the service when its environment/configuration changed. Use `docker compose logs -f adhd-hub` and `/api/health` to verify the restart.
