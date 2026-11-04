# Connect a machine or project in one step

Point coding agents at a running ADHD Progress Hub without hand-editing every config file, and without putting bearer tokens in commands or configuration files.

## Agent setup and authenticated diagnostics

Without a project checkout:

```bash
adhd-hub agents setup --hub https://hub.example.com --agents codex,claude,cursor --scope user
adhd-hub agents status --hub https://hub.example.com --agents codex,claude,cursor
adhd-hub agents doctor --hub https://hub.example.com --agents codex,claude,cursor --json
```

`setup` writes registrations, then checks MCP directly. If credentials are missing,
registrations are still saved and the command exits nonzero with recovery guidance.
`status` and `doctor` share the same read-only checks: neither launches an agent,
changes configuration, sends notifications, nor writes verification back to the Hub.
They report executable detection, config paths/scopes, credential presence (`SET` or
`MISSING`), endpoint reachability, initialization, authentication and discovery of
`get_overview`. A config file alone never means connected. Exit status is nonzero
for configuration errors, missing environment credentials or failed authenticated
probes. Missing executables and inaccessible client OAuth stores remain warnings.

The probe handles JSON and SSE, MCP session IDs, the initialized notification,
protocol negotiation and paginated `tools/list`, with time and response-size limits.
HTTP 401/403 means missing, expired, rejected or insufficient credentials; the CLI
cannot infer which from the status alone. TLS/network failures are separate from
configuration findings. HTTPS is required outside loopback. Redirects to other
endpoints are refused so credentials cannot follow them.

### Authentication methods are separate

| Method | Used by | What setup does |
| --- | --- | --- |
| Server bearer (`ADHD_HUB_AUTH_TOKEN`) | Processes inheriting that environment variable | New registrations reference the variable; no literal secret is written |
| CLI short-code session | `adhd-hub` CLI using its local credentials file | Login saves a CLI session; it does **not** fill agent environments or OAuth stores |
| MCP OAuth browser authorization | The client that completed authorization | Existing headerless/OAuth configurations are preserved; authorize separately in each client |

The Hub accepts CLI-session bearers at MCP too, but agents do not automatically
read the CLI credentials file. A successful CLI login or CLI-token probe therefore
cannot verify an agent's credentials. Agent diagnostics use the agent registration's
environment bearer, never silently substitute a saved CLI session. Client OAuth,
custom headers, alternate token variables and local stdio registrations are preserved
and reported as unavailable for direct verification. Use the client's own MCP status
to verify these integrations. To change to OAuth, review/remove the bearer header
(or Codex's `bearer_token_env_var`) yourself and authorize with the client's Auth
control; Codex supports `codex mcp login adhd-hub`.

### Locations and scopes

| Client | User scope | Project scope | Bearer syntax |
| --- | --- | --- | --- |
| Claude Code | `~/.claude.json`, top-level `mcpServers` | `.mcp.json` | `Bearer ${ADHD_HUB_AUTH_TOKEN}` |
| Cursor | `~/.cursor/mcp.json` | `.cursor/mcp.json` | `Bearer ${env:ADHD_HUB_AUTH_TOKEN}` |
| Codex | `~/.codex/config.toml` | `.codex/config.toml` | `bearer_token_env_var = "ADHD_HUB_AUTH_TOKEN"` |

`CODEX_HOME` and `CLAUDE_CONFIG_DIR` overrides are respected. With
`CLAUDE_CONFIG_DIR`, user `.claude.json` lives **inside** that directory. Claude's
local per-project entries inside its user JSON are also inspected when `--project`
is supplied. Codex ancestor `.codex/config.toml` layers are inspected; project
configuration only loads for trusted projects. Pass the intended `--project` to
detect project/user conflicts. User-only setup deliberately does not inspect an
arbitrary current directory or scan every checkout on the machine.

`connect --scope project` now consistently targets project scope for all three
clients; older releases always wrote Codex and Claude at user scope. Existing
user entries cause a conflict report: reuse `--scope user` or review/remove the
redundant entry. Setup never silently deletes registrations from another scope.
Unrelated settings/servers and existing custom authentication are preserved. JSON
writes and supported Codex table edits are atomic, with one private
`*.adhd-hub.bak` backup of the pre-edit file. Unusual TOML layouts are refused for
manual review; comments and other tables are retained. JSON-with-comments is not
rewritten automatically.

### Preview and repair

```bash
adhd-hub agents setup --agents claude,cursor,codex --hub https://hub.example.com --dry-run
adhd-hub agents repair --agents claude --hub https://hub.example.com
adhd-hub agents repair --agents claude --hub https://hub.example.com --apply
# Explicit workspace:
adhd-hub agents setup --agents claude,cursor,codex --scope project --project ./repo --hub https://hub.example.com
```

Repair previews by default. `--apply` uses the same idempotent setup helpers;
`--dry-run` always wins over apply. Recognized old interpolation is repaired.
Custom authentication/transport cannot be retargeted automatically. Review scope
conflicts and malformed files manually; previews never print their contents.
Restart selected agents after applying, then ask each agent to list Hub tools.
The direct probe does not establish that a launched agent inherited the same HOME,
PATH, current directory, environment or OAuth session.

### Headless Debian, SSH and multiple users

Run setup as the account that actually launches agents. For example, log in as
that account over SSH, then use an accessible working directory:

```bash
cd "$HOME"
export PATH="$HOME/.local/bin:$PATH"
adhd-hub agents setup --hub https://hub.example.com --agents codex,claude,cursor --scope user --non-interactive
# Bash: read a token without putting its value in shell history or command arguments.
read -r -s -p 'Hub bearer token: ' ADHD_HUB_AUTH_TOKEN
printf '\n'
export ADHD_HUB_AUTH_TOKEN
adhd-hub agents doctor --hub https://hub.example.com --agents codex,claude,cursor --scope user
# Launch agents from this environment, or inject the variable in their service.
```

An initial missing-credential result is expected until the variable is injected.
For unattended installation, inject it with your existing secret manager/service
launcher before setup; do not put its value on a command line. Do not copy a
server `.env` into a checkout or shell profile.

A systemd service's `EnvironmentFile=` applies to its processes, not a new SSH
shell. An administrator's successful probe does not verify a service account.
Switching accounts with `sudo -u ... -H` changes HOME but normally filters environment
variables and retains cwd. This explains both missing-token errors and attempts
to read a protected administrator checkout's `.mcp.json`. Use a service-account
login, `cd "$HOME"`, and the same approved environment injection as the launcher.
Doctor never reads privileged service environment files or inspects another
process's environment. An administrator must manage any service changes; setup
does not edit systemd, restart services or change networking.

If a separate MCP server launches `codex`, that executable also needs to be on the
launcher's PATH. ADHD Hub diagnostics check the selected clients, not unrelated
servers. Run `command -v codex claude cursor-agent` in the agent launch context.
Each user has separate config/OAuth stores; copying another user's registration is
not a substitute for setup and authentication under the right account.

### Windows

Run setup in PowerShell under the Windows account that launches the agents:

```powershell
adhd-hub agents setup --hub https://hub.example.com --agents codex,claude,cursor --scope user --non-interactive
adhd-hub agents doctor --hub https://hub.example.com --agents codex,claude,cursor --json
```

Home paths resolve under that account's profile, including
`$HOME\.claude.json`. A Windows service, scheduled task, WSL session, SSH session
and desktop app can have different users, HOME and environments. Environment
changes affect newly launched processes; restart the agent/launcher after the
approved credential injection. Prefer per-client OAuth for desktop use when
available. Do not put tokens in PowerShell commands, profiles or project files.
`install.ps1 -NonInteractive -Agents 'codex,claude,cursor'` forwards noninteractive
setup; `install.sh --non-interactive --agents codex,claude,cursor` does the same on
Linux/macOS. `ADHD_HUB_CONNECT_NON_INTERACTIVE=1` is the installer env equivalent.

Official configuration references checked 2026-11-03:
[Claude Code MCP](https://code.claude.com/docs/en/mcp),
[Claude config locations](https://code.claude.com/docs/en/mcp-quickstart),
[Cursor MCP](https://cursor.com/docs/mcp),
[Codex MCP](https://developers.openai.com/codex/mcp).

## Recommended connect flow

Use this path when the Hub is already running and you want to connect a project or coding machine.

### 1. Copy the command from the Hub

Stay signed in to the Hub UI and open **Settings → Coding agents**. Copy the generated command.

The generated command does **not** contain the server access token.

### 2. Run it from the project you want to connect

#### macOS / Linux / WSL / Git Bash

```bash
curl -fsSL "$ADHD_HUB_PUBLIC_URL/install.sh" | sh -s -- /path/to/project
```

#### Windows PowerShell

Download-then-run is the most reliable option when `iex` is blocked:

```powershell
iwr "$env:ADHD_HUB_PUBLIC_URL/install.ps1" -OutFile $env:TEMP\adhd-hub-install.ps1
powershell -ExecutionPolicy Bypass -File $env:TEMP\adhd-hub-install.ps1 -Project 'C:\path\to\project'
```

If `iex` is allowed:

```powershell
iex "& { $(irm $env:ADHD_HUB_PUBLIC_URL/install.ps1) } -Project 'C:\path\to\project'"
```

Choose a repository directory deliberately. `.` means the current directory, so running the installer from your home directory targets your home directory.

### 3. Approve this computer

The CLI will:

1. open your browser to the Hub, or print a short code such as `ABCD-WXYZ`;
2. ask you to choose **Allow** in the browser, or enter the code under **Settings → Coding agents**;
3. save a local CLI session in `~/.config/adhd-hub/credentials.json`; on Unix-like systems, the file has mode `0600`.

That CLI session is local to the computer. It is **not** the server access token.

### 4. Restart your coding agents and verify

```bash
adhd-hub doctor --hub "$ADHD_HUB_PUBLIC_URL" --project /path/to/project
```

The install/connect summary separates successful checks from skipped or warning checks. Optional companion installs can partly succeed, so review **Needs attention** before assuming every agent reloaded correctly.

## What the installer handles

The bootstrap scripts try the least disruptive path first:

- If `adhd-hub` is already on `PATH` and `uv` is available, they refresh the CLI from this Hub's wheel before connecting.
- Otherwise they can fall back to `uvx --from <this Hub's wheel URL>`, then GitHub if the wheel URL is unavailable.
- If `uv` is missing, interactive runs ask before using Astral's official installer.
- Non-interactive runs never install `uv` automatically unless `ADHD_HUB_INSTALL_UV=1` is set.
- After an ephemeral `uvx` connect, interactive scripts may offer to install the CLI permanently. Non-interactive opt-in is `ADHD_HUB_INSTALL_CLI=1`.
- Dry-run connect does not install or refresh the CLI.

If no supported toolchain is available, the script prints the manual recovery steps instead of modifying the machine silently.

### PATH fixes

The shell installer checks common tool locations such as `~/.local/bin` and custom `UV_TOOL_BIN_DIR` paths. It can run `uv tool update-shell` to update shell profiles without replacing unrelated profile settings.

A script piped into `sh` cannot modify the **current** shell process. If needed, it prints commands such as:

```bash
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
export PATH="$(uv tool dir --bin):$PATH"
```

Run those in the current terminal, restart your coding agents, then run `adhd-hub doctor` again.

### Agent selection

Use the same explicit agent list you actually use, for example:

```bash
--agents cursor,codex,claude,openclaw
```

This avoids installing optional integrations for agents that are not part of your workflow. Eve and PromptScript, for example, require project-local skills and can otherwise show up as warnings.

### Windows TLS note

On Windows, `adhd-hub` uses the **OS certificate store** (via `truststore`) for Hub HTTPS — closer to the browser than Python’s bundled CAs alone. That matters for private/internal CAs and some intermediate chains. If `adhd-hub login` still fails with `certificate has expired` while Debian works:

1. Confirm Windows date/time is correct.
2. Open the Hub URL in a browser — if the padlock shows expired, renew the Hub certificate.
3. If you use a private CA, install it into **Trusted Root Certification Authorities**.

Debian/LXC often already works because system Python trusts `/etc/ssl/certs`.

You can run the handshake alone:

```bash
adhd-hub login --hub "$ADHD_HUB_PUBLIC_URL"
adhd-hub logout --hub "$ADHD_HUB_PUBLIC_URL"   # forget this machine's session
```

### Switch Hub host (localhost → remote)

If `connect` defaulted to `http://127.0.0.1:8787` and you want a hosted Hub instead:

```bash
adhd-hub use-hub https://adhd-hub.example.com \
  --project /path/to/project \
  --agents cursor,codex,claude
```

That command:

1. Saves the URL as your CLI **default hub** (`~/.config/adhd-hub/credentials.json` → `default_hub`)
2. Retargets Cursor / Codex / Claude MCP entries to `https://…/mcp`, reusing each existing scope (`--scope both`, the default) without creating a second registration
3. Runs the browser login handshake if you are not already signed in to that Hub

Afterward, `adhd-hub doctor` / `connect` / `login` without `--hub` use the saved host (env vars like `ADHD_HUB_PUBLIC_URL` still win when set).

You can also re-run a full connect with an explicit host:

```bash
adhd-hub connect /path/to/project --hub https://adhd-hub.example.com --agents cursor,codex,claude
```

### Threat model (short)

| Secret | Where it lives | Where it must not go |
| --- | --- | --- |
| Server `ADHD_HUB_AUTH_TOKEN` | Hub process environment / `.env` | Shell profile, install URL, `mcp.json`, chat logs |
| One-time connect code | Hub SQLite for ~10 minutes, single-use | Reuse / replay; it expires |
| CLI session (`ahcli_…`) | `~/.config/adhd-hub/credentials.json` on the client | Shell `export`, git, progress notes |

The CLI session is accepted as Bearer for REST and MCP. It is **not** the server access token. Each accepted use refreshes it for 90 days, and the saved credentials file is kept so the CLI can reconnect while the Hub session is still valid. Revoke it under **Settings → Coding agents → Connected computers** or with `adhd-hub logout`. Dashboard password login is unchanged.

Project MCP snippets still interpolate an environment variable so they stay safe to commit. Existing clients that already use `ADHD_HUB_AUTH_TOKEN` keep working.

## Local stdio transport (optional)

Local MCP clients that can spawn a subprocess can use the same Hub tool catalog without an HTTP connection:

```json
{
  "mcpServers": {
    "adhd-hub": {
      "command": "adhd-hub",
      "args": ["mcp-stdio"]
    }
  }
}
```

The equivalent command is `adhd-hub mcp-stdio`. It loads normal Hub settings (`.env`, config TOML, and `ADHD_HUB_*` environment variables) and persists through the configured `ADHD_HUB_DATA_DIR`. Because stdio is a local child-process transport, it does not use an HTTP bearer header.

Use this when the agent and Hub data are intentionally local to the same machine, or when an MCP inspector/proxy such as Glama needs a stdio child process. It does **not** start the REST API, dashboard, OAuth endpoints, or background scheduler. If you already run a persistent Hub server, or need multiple machines/remote agents, keep the Streamable HTTP `/mcp` configuration above. `adhd-hub connect` continues to wire the HTTP transport by default.

## MCP Auth / Authenticate (OAuth)

MCP clients that offer an **Auth** / **Authenticate** control can obtain a Hub Bearer for `/mcp` via Hub OAuth when the **Hub server** has:

- `ADHD_HUB_PUBLIC_URL` set to the URL agents and browsers use, and
- OAuth enabled (default; Hub env `ADHD_HUB_OAUTH_ENABLED` unset or `true`).

Flow (agent-agnostic — any MCP client that speaks MCP OAuth 2.1; Cursor is one verification target):

1. Point the client at `https://<hub>/mcp` (or your public Hub `/mcp`).
2. Choose **Auth** / **Authenticate** in the client.
3. Sign into the Hub UI if prompted, then press **Allow** on the consent page.

That issues an opaque OAuth access token for MCP only. It is not the server access token and is not a CLI connect session.

**Browser on a different machine from the agent?** A loopback callback returns to
the browser machine. For OpenClaw, use the [remote gateway SSH callback setup](openclaw-mcp-oauth.md#remote-browser-gateway)
before approving; no authorization-code copying is needed. Do not rewrite the
authorization URL or expose the callback publicly.

**Still supported (no Auth button required):**

- Static `Authorization: Bearer …` with `ADHD_HUB_AUTH_TOKEN` on the client (or `${env:ADHD_HUB_AUTH_TOKEN}` in MCP config).
- CLI `adhd-hub connect` / `adhd-hub login` (user-code + Allow in **Settings → Coding agents**).

**Rollback:** set `ADHD_HUB_OAUTH_ENABLED=false` on the Hub and restart. Discovery (`.well-known/…`) and `/api/oauth/*` turn off; static Bearer and CLI connect keep working. `adhd-hub doctor --hub <url>` always probes that Hub’s OAuth well-known when diagnosing a non-loopback Hub (or when `ADHD_HUB_PUBLIC_URL` is set), independent of any local `ADHD_HUB_OAUTH_ENABLED` in the doctor process; it warns on missing/malformed metadata. OAuth discovery failures are warnings; failed authenticated MCP probes are errors in doctor.

## CLI wire-up flags

Both install scripts refresh an existing `adhd-hub` on PATH from **this Hub's** `/install/cli-wheel.url` when `uv` is available, then prefer that durable CLI (ephemeral `uvx --from <wheel>` is the fallback; GitHub git if the wheel URL is missing). If `uv` itself is missing, they offer an interactive Astral bootstrap (see above) or honor `ADHD_HUB_INSTALL_UV=1`. Prefer `uv tool install git+https://github.com/uniskela/adhd-hub.git` only when you want a standalone CLI without a running Hub. `connect` offers CLI login on an interactive TTY when no session is saved (`--no-login` or `--non-interactive` skips it). Agent-only setup never starts CLI login.

`--agents` controls which tools get **MCP / config wire-up** and which agents receive Hub **skills**. With no selection, interactive CLI runs offer detected agents. Noninteractive runs require `--agents` / `-Agents` or `ADHD_HUB_CONNECT_AGENTS` and fail before login/config writes if none are selected. Use `*` to install skills for every skills.sh agent. Hub alias `claude` maps to skills.sh id `claude-code`.

In **Settings → Coding agents**, choose agents before copying setup. The Linux/macOS
and Windows commands include that selection immediately; running the command adds
missing MCP registrations and checks existing settings. The browser does not write
configuration on the agent's machine. **Save as defaults** stores the agent, skills
and extras choices for future installs. The user-level setup and doctor commands
also follow the current selection and work without a project checkout.

```powershell
iex "& { $(irm $env:ADHD_HUB_PUBLIC_URL/install.ps1) } -Agents 'cursor,codex,claude'"
# or all agents:
iex "& { $(irm $env:ADHD_HUB_PUBLIC_URL/install.ps1) } -Agents '*'"
```

`--skill *` in the skills CLI means “Hub skills (session, projects, env-check)” (projects + session), not “every coding agent.”

**Hub skills mode** (Settings → Coding agents → Where Hub skills go, or flags/env):

| Mode | Flag | Effect |
|------|------|--------|
| Global (default) | `--skills` | `npx skills add … -g` for selected agents |
| Project | `--project-skills` | Sync Hub-owned skills into `.agents/skills/` in the connected repo |
| Off | omit both skills flags | Skip Hub skills (companions unchanged) |

Do not pass `--skills` and `--project-skills` together. Install scripts also accept `--no-skills` (and `ADHD_HUB_CONNECT_NO_SKILLS=1`) for off; that flag is **installer-only** — `adhd-hub connect` itself has no `--no-skills`. Env: `ADHD_HUB_CONNECT_SKILLS_MODE=global|project|off`.

Install-script flags (also via env): `--agents`, `--scope`, `--register`, `--openclaw-skills`, `--skills` / `--project-skills` / `--no-skills`, `--no-cursor-rule`, `--dry-run`, plus `ADHD_HUB_CONNECT_FLAGS` for extras.

```bash
adhd-hub connect /path/to/project \
  --hub https://hub.example.com \
  --agents cursor,codex \
  --scope project \
  --cursor-rule \
  --skills \
  --openclaw-skills \
  --register \
  --find-roots ~/Projects

# Preview without writing files or registering:
adhd-hub connect /path/to/project --hub https://hub.example.com --cursor-rule --skills --dry-run

adhd-hub doctor --hub https://hub.example.com --project /path/to/project
```

### What connect configures

For Cursor-only Marketplace install (skills + rule + BYO MCP variables, no per-project `connect`), see [adhd-hub-cursorskill](https://github.com/uniskela/adhd-hub-cursorskill) and [Cursor plugin skill sync](cursor-plugin-skill-sync.md). `adhd-hub connect` remains the project/CLI path below.

- **Cursor MCP** — project `.cursor/mcp.json` or user `~/.cursor/mcp.json` (`--scope user`), using `${env:ADHD_HUB_AUTH_TOKEN}` so the file stays token-free
- **Codex / Claude** — selected scope from the table above; existing settings/authentication are preserved
- **Cursor rule** — `.cursor/rules/adhd-hub.mdc` with `--cursor-rule`
- **AGENTS.md** — same reversible managed block as `adhd-hub setup`
- **Skills** — Hub skills via Settings mode or flags: `--skills` (global npx `-g`) or `--project-skills` (repo `.agents/skills`). Missing `npx` for global **warns** and still succeeds; project sync failures warn the same way. Companions (i-have-adhd, etc.) stay separate opt-ins / Select all in Settings.
- **OpenClaw skills** — opt-in `npx skills add … -a openclaw`; hook URL/token still configured in **Settings → Phone alerts**. Missing `npx` warns only (does not fail Hub connect)
- **Register** — `GET /api/projects/resolve?create=true` when a CLI session or bearer token is available
- **Find** — scan `--find-roots` for `.git` / `AGENTS.md` / `.cursor` folders and list them

`adhd-hub setup` remains available for AGENTS-only installs.

## Connect and doctor report

`adhd-hub connect` and `adhd-hub doctor` print the same scannable report (login uses it too). While a subprocess runs, the CLI uses a quiet prefix, for example `→ Running  npx skills add …` (dim on a color TTY).

The banner reports errors or attention items and never says an agent is connected
because a file exists. Normal output includes registration destinations; `-v`
also lists all checks. Setup can save configuration while credentials are missing:
review the authentication and direct HTTP results before using the registration.
Dry runs say **Preview only** and do not start login, install tools or write files.
For machine-readable output use `agents … --json` or `doctor --json`.

### Color

Color is on when stdout is a TTY. It is off when output is piped (including typical CI) or when `NO_COLOR` or `ADHD_HUB_NO_COLOR` is set to a non-empty value. There is no separate `--no-color` flag.

## Optional third-party companions

In **Settings → Coding agents**, under **Helpful extras**, toggle opt-in companions (i-have-adhd, Superpowers, Ponytail, Graphify, Context7, agent-browser, RTK, Serena, Humanizer) and **Save as defaults**. Those choices are included in `/install.sh` and `/install.ps1`.

`connect` / `doctor` also list them when missing. You can pass flags manually:

```bash
adhd-hub connect /path/to/project --agents codex,claude --with-i-have-adhd --with-graphify --with-context7 --with-ponytail --with-humanizer
```

Full install tables, licenses, and privacy notes: [Recommended third-party companions](coding-companions.md).

## Safety

- Never commits Hub URLs or tokens into `AGENTS.md`
- Refuses to overwrite symlinks
- Merges only the `adhd-hub` MCP server key; other MCP servers stay untouched
- OpenClaw gateway secrets are not written by the one-liner; use the Hub UI or Hub-server env
- Connect grants are hashed in `data/connect.sqlite3`, expire in 10 minutes, and cannot be reused
- Backups still omit browser sessions, passwords, and CLI connect grants

See the [improvement roadmap](plans/improvement-roadmap.md) Wave 0 for status and follow-ons.
