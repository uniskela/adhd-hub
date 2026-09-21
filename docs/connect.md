# Connect a machine or project in one step

Point coding agents at a running ADHD Progress Hub without hand-editing every config file, and without putting the **server** access token in your shell.

## Safer CLI connect (recommended)

Stay signed in to the Hub UI. In **Settings → Agents & install** copy the command (no token in it):

### macOS / Linux / WSL / Git Bash

```bash
curl -fsSL "$ADHD_HUB_PUBLIC_URL/install.sh" | sh -s -- /path/to/project
```

### Windows PowerShell

Prefer download-then-run (more reliable when `iex` is blocked by policy):

```powershell
iwr "$env:ADHD_HUB_PUBLIC_URL/install.ps1" -OutFile $env:TEMP\adhd-hub-install.ps1
powershell -ExecutionPolicy Bypass -File $env:TEMP\adhd-hub-install.ps1 -Project 'C:\path\to\project'
```

One-liner (when `iex` is allowed):

```powershell
iex "& { $(irm $env:ADHD_HUB_PUBLIC_URL/install.ps1) } -Project 'C:\path\to\project'"
```

If `adhd-hub` is already on `PATH` and `uv` is available, re-running `install.sh` / `install.ps1` **refreshes** that CLI from this Hub’s wheel (`uv tool install --force`) before connect — so an old `0.7.x` tool install becomes this Hub’s version without a manual follow-up. Then the scripts prefer the refreshed `adhd-hub`, falling back to `uvx --from <this Hub’s wheel URL>` (GitHub git fallback). (`adhd-hub` is not on PyPI yet.)

If **none** of those tools are on `PATH`, the script explains that Hub connect needs the local **uv** toolchain + **adhd-hub** CLI (nothing remote is modified), then asks on a TTY:

```text
Install uv now using the official Astral installer, then install the ADHD Hub CLI? [y/N]
```

Answer `y` to install uv via Astral’s official installer, `uv tool install --force` the CLI (overwrites a leftover `~/.local/bin/adhd-hub` shim — common after removing uv and re-testing), and continue connect. Answer `N` (default) to print manual steps and exit. Non-interactive runs (no `/dev/tty`, CI) never auto-install; set `ADHD_HUB_INSTALL_UV=1` to opt in for automation. After a successful `uvx` connect when `adhd-hub` is still missing, scripts may also offer a permanent CLI install (`ADHD_HUB_INSTALL_CLI=1` for non-interactive opt-in). Dry-run connect does not install or refresh the CLI.

What happens next:

1. The CLI opens your browser to this Hub (or prints a short code like `ABCD-WXYZ`).
2. Press **Allow this CLI** (or type the code under **Settings → Windows / MCP**).
3. The CLI saves a **CLI session** under `~/.config/adhd-hub/credentials.json` (mode `0600`). That file is local to this computer.

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
2. Retargets Cursor / Codex / Claude MCP entries to `https://…/mcp`
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

The CLI session is accepted as Bearer for REST and MCP. It is **not** the server access token. Revoke it in **Settings → Windows / MCP** or with `adhd-hub logout`. Dashboard password login is unchanged.

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
- CLI `adhd-hub connect` / `adhd-hub login` (user-code + Allow in **Settings → Windows / MCP**).

**Rollback:** set `ADHD_HUB_OAUTH_ENABLED=false` on the Hub and restart. Discovery (`.well-known/…`) and `/api/oauth/*` turn off; static Bearer and CLI connect keep working. `adhd-hub doctor --hub <url>` always probes that Hub’s OAuth well-known when diagnosing a non-loopback Hub (or when `ADHD_HUB_PUBLIC_URL` is set), independent of any local `ADHD_HUB_OAUTH_ENABLED` in the doctor process; it warns on missing/malformed metadata. Unreachable Hub is a warning, not a hard failure.

## CLI wire-up flags

Both install scripts refresh an existing `adhd-hub` on PATH from **this Hub's** `/install/cli-wheel.url` when `uv` is available, then prefer that durable CLI (ephemeral `uvx --from <wheel>` is the fallback; GitHub git if the wheel URL is missing). If `uv` itself is missing, they offer an interactive Astral bootstrap (see above) or honor `ADHD_HUB_INSTALL_UV=1`. Prefer `uv tool install git+https://github.com/uniskela/adhd-hub.git` only when you want a standalone CLI without a running Hub. `connect` runs `login` automatically when no session is saved (`--no-login` skips that).

`--agents` controls which tools get **MCP / config wire-up** and which agents receive Hub **skills**. There is no assumed default: set agents in **Settings → Agents & install**, pass `--agents` / `-Agents`, or set `ADHD_HUB_CONNECT_AGENTS`. Use `*` to install skills for every skills.sh agent. Hub alias `claude` maps to skills.sh id `claude-code`.

```powershell
iex "& { $(irm $env:ADHD_HUB_PUBLIC_URL/install.ps1) } -Agents 'cursor,codex,claude'"
# or all agents:
iex "& { $(irm $env:ADHD_HUB_PUBLIC_URL/install.ps1) } -Agents '*'"
```

`--skill *` in the skills CLI means “Hub skills (session, projects, env-check)” (projects + session), not “every coding agent.”

Install-script flags (also via env): `--agents`, `--scope`, `--register`, `--openclaw-skills`, `--no-skills`, `--no-cursor-rule`, `--dry-run`, plus `ADHD_HUB_CONNECT_FLAGS` for extras.

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

For Cursor-only Marketplace install (skills + rule + BYO MCP variables, no per-project `connect`), see [adhd-hub-cursorskill](https://github.com/uniskela/adhd-hub-cursorskill) and [Cursor plugin skill sync](cursor-plugin-skill-sync.md). `adhd-hub connect` remains the project/CLI path below.

- **Cursor MCP** — project `.cursor/mcp.json` or user `~/.cursor/mcp.json` (`--scope user`), using `${env:ADHD_HUB_AUTH_TOKEN}` so the file stays token-free
- **Codex / Claude** — optional MCP blocks when listed in `--agents`
- **Cursor rule** — `.cursor/rules/adhd-hub.mdc` with `--cursor-rule`
- **AGENTS.md** — same reversible managed block as `adhd-hub setup`
- **Skills** — opt-in global `npx skills add` (`--skills`)
- **OpenClaw skills** — opt-in `npx skills add … -a openclaw`; hook URL/token still configured in **Settings → OpenClaw**
- **Register** — `GET /api/projects/resolve?create=true` when a CLI session or bearer token is available
- **Find** — scan `--find-roots` for `.git` / `AGENTS.md` / `.cursor` folders and list them

`adhd-hub setup` remains available for AGENTS-only installs.

## Connect and doctor report

`adhd-hub connect` and `adhd-hub doctor` print the same scannable report (login uses it too). While a subprocess runs, the CLI uses a quiet prefix, for example `→ Running  npx skills add …` (dim on a color TTY).

### Outcome first

A banner, then the Hub URL:

```text
Complete! ADHD Hub is connected.
Hub: http://127.0.0.1:8787
```

On failure the banner is `Connect finished with errors — see summary below.` (doctor uses that same wording). Color is green for success and red for failure when color is on. Failure here means at least one step has status **error**. **warn**, **missing**, and **manual** still appear under **Needs attention** on a green report (typical for `doctor` when optional files are absent).

### Do next or Fix these

- **Do next** (success) — short bullets. Always includes opening the Hub UI and a close-the-terminal note. After `connect`, also restart agents, a `doctor` verify line, and optional `adhd-hub` PATH install. Optional companions guide when companion steps ran.
- **Fix these** (failure) — numbered `name — detail` lines for **warn**, **error**, and **missing** steps only. Manual companion tips are not listed here.

A failing report ends with `Fix the XX/!! items above, then re-run the install/connect command.`

### Needs attention and Done

**Needs attention** lists every **warn**, **error**, **missing**, or **manual** step with a mark and the same step detail. Empty sections are omitted.

| Status | Mark | Color (when enabled) |
| --- | --- | --- |
| ok | `OK` | green |
| skipped, manual | `--` | dim |
| warn, missing | `!!` | yellow |
| error | `XX` | red |

OK and skipped steps collapse under **Done** as group counts (`Hub`, `Agents`, `Companions`, `Other` when any of that group succeeded or was skipped), for example `Hub · 3 ok`.

Pass global `-v` / `--verbose` to also print **Summary of what ran** with every step.

### Color

Color is on when stdout is a TTY. It is off when output is piped (including typical CI) or when `NO_COLOR` or `ADHD_HUB_NO_COLOR` is set to a non-empty value. There is no separate `--no-color` flag.

## Optional coding companions

In **Settings → Agents & install**, under **Coding companions**, toggle opt-in companions (i-have-adhd, Graphify, RTK, Superpowers, Context7, agent-browser, Serena) and **Save connect defaults**. Those choices are included in `/install.sh` and `/install.ps1`.

`connect` / `doctor` also list them when missing. You can pass flags manually:

```bash
adhd-hub connect /path/to/project --agents codex,claude --with-i-have-adhd --with-graphify --with-context7
```

Full install tables, licenses, and privacy notes: [Recommended coding companions](coding-companions.md).

## Safety

- Never commits Hub URLs or tokens into `AGENTS.md`
- Refuses to overwrite symlinks
- Merges only the `adhd-hub` MCP server key; other MCP servers stay untouched
- OpenClaw gateway secrets are not written by the one-liner; use the Hub UI or Hub-server env
- Connect grants are hashed in `data/connect.sqlite3`, expire in 10 minutes, and cannot be reused
- Backups still omit browser sessions, passwords, and CLI connect grants

See the [improvement roadmap](plans/improvement-roadmap.md) Wave 0 for status and follow-ons.
