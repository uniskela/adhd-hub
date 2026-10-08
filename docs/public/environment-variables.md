# Environment variables

ADHD Progress Hub server configuration uses the `ADHD_HUB_` prefix. Use this page as a reference rather than a setup checklist.

For a normal container install:

1. put server settings in the `.env` file used by Compose;
2. keep `ADHD_HUB_DATA_DIR=/data` and mount persistent storage there;
3. set a strong `ADHD_HUB_AUTH_TOKEN` before non-loopback access;
4. set `ADHD_HUB_PUBLIC_URL` when browsers or agents use another hostname;
5. keep secrets out of `compose.yml`, source control, `AGENTS.md`, issues, and progress notes.

Developer-only smoke/probe variables are listed separately near the end.

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
| `ADHD_HUB_DATA_DIR` | `./data` (host/dev) / `/data` (container image + Compose) | path | SQLite databases (`hub.sqlite3` includes project **tags** and AI scan-line cache), `ai.json` (AI settings), wiki, preferences, sessions. **In Docker prefer absolute `/data` and mount a volume there.** Relative `./data` resolves to `/app/data`; current images remap that known default to `/data`, and Compose pins `/data` so persistence does not rely on remapping. Older images without remapping lose `/app/data` when the container is recreated. |
| `ADHD_HUB_AUTH_TOKEN` | `change-me` | secret string | Server bearer token for REST/MCP plus dashboard setup/recovery. `change-me` / empty / `.env.example` placeholder are development-only; the server refuses to start with a weak token when using a non-loopback bind, non-loopback `PUBLIC_URL`, or `TRUST_PROXY_HEADERS`. |
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
| `ADHD_HUB_SEED_DEMO` | `false` | boolean | When true, load the generic sample pack on boot if it is not already present (same as **Settings → Your data → Load sample data**). Never wipes existing projects; a second boot is a no-op. Remove only via **Remove sample data**. |
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

## Wave 6 AI scan-lines (opt-in)

Soft default: **off**. Heuristic scan-lines always work without AI.

For most users, configure this under **Settings → AI helpers**:

1. choose a Base URL preset or enter a custom OpenAI-compatible base URL;
2. choose a model and optional API key;
3. set the timeout;
4. use **Test and load models** to refresh the model list;
5. save the settings.

UI-saved values live in `data/ai.json`. The API key is encrypted with the Hub access token and is never returned to the browser. Environment variables are mainly useful for provisioning a fresh instance.

Uses an OpenAI-compatible `/chat/completions` endpoint (local Ollama or similar preferred). Only bounded, scrubbed structured thread fields are sent — never progress bodies, transcript references, or forge `source_conflicts` blobs. Continuity fields are capped (~80–120 chars) and ritual/agent walls are dropped; when a forge conflict exists, Hub’s side is preferred over forge text. Common credential, URL, and machine-path patterns are redacted before the request and again on the response; keep sensitive material out of continuity fields. Stub or truncated AI replies fall back to the heuristic scan-line. On failure or when unset, heuristic scan-lines are used.

On My work, the reader’s **⋯ → Rewrite scan line** forces a refresh for one thread (`POST /api/threads/{id}/scan-line`). With a project selected, **⋯ → Rewrite all scan lines** beside the project title confirms, then rewrites every open thread in that project and its nested descendants (`POST /api/projects/{slug}/scan-lines`) with a short delay between calls; when AI is off the request explains and no-ops. **Rewrite scan lines on their own** (Settings, default off) rewrites on thread/progress save and opportunistically ensures stale cards when My work loads — only when the content hash drifts. Soft ensure uses `POST /api/threads/{id}/scan-line` with `{"mode":"ensure"}` (hash skip); omit mode or use `force` for a manual rewrite.

| Variable | Default | Type | Purpose |
| --- | --- | --- | --- |
| `ADHD_HUB_AI_ENABLED` | `false` | boolean | Soft enable gate on `Settings`. A non-empty `ADHD_HUB_AI_BASE_URL` still bootstraps enabled when no `data/ai.json` exists yet. Prefer **Settings → AI helpers** for ongoing on/off. Alone (without a base URL) does not activate AI. |
| `ADHD_HUB_AI_BASE_URL` | unset | URL | OpenAI-compatible API base ending before `/chat/completions`, e.g. `http://127.0.0.1:11434/v1`. When set and no `data/ai.json` yet, AI starts enabled. |
| `ADHD_HUB_AI_MODEL` | `llama3.2` | string | Model id passed to the provider. Gemini OpenAI-compat list ids may include a `models/` prefix; Hub strips that (and a leading `google/`) for chat and when filling the Model dropdown. Non-chat list entries (embeddings, Imagen, image/TTS variants) are hidden, and Gemini flash ids known to be unavailable to new users are filtered from the list. Prefer bare current chat ids like `gemini-3.6-flash`. |
| `ADHD_HUB_AI_API_KEY` | unset | secret string | Optional bearer token for remote providers. Prefer Settings for ongoing secrets. |
| `ADHD_HUB_AI_TIMEOUT_SECONDS` | `15` | float | HTTP timeout for a scan-line rewrite (greater than 0, at most 30 seconds). Local or proxy models (Ollama, Codex-lb, etc.) often need a higher timeout than cloud APIs; raise this in Settings if you see ReadTimeout / “AI timed out”. |

For a TLS reverse proxy, a typical configuration is:

```env
ADHD_HUB_PUBLIC_URL=https://adhd-hub.example.com
ADHD_HUB_TRUST_PROXY_HEADERS=true
# Optional hard override:
# ADHD_HUB_COOKIE_SECURE=true
```

See [Authentication](authentication.md) and [Installation](installation.md#reverse-proxy-https-and-tailscale).

## OpenClaw

These are optional. OpenClaw connection details can also be configured from **Settings → Phone alerts**; UI-saved configuration is intended for normal ongoing administration while environment variables are useful for initial provisioning.

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
| `UV_NO_CACHE` | `1` (image) | Disables uv's on-disk package archive cache in the container image so scanners do not inventory leftover build wheels alongside `.venv`. |

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
