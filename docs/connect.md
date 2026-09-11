# Connect a machine or project in one step

Point coding agents at a running ADHD Progress Hub without hand-editing every config file, and without putting the **server** access token in your shell.

## Safer CLI connect (recommended)

Stay signed in to the Hub UI. In **Settings → Connections** copy the command (no token in it):

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

If `adhd-hub` is not on `PATH`, the install scripts use:

```text
uvx --from git+https://github.com/uniskela/adhd-hub.git adhd-hub …
```

(`adhd-hub` is not on PyPI yet.)

What happens next:

1. The CLI opens your browser to this Hub (or prints a short code like `ABCD-WXYZ`).
2. Press **Allow this CLI** (or type the code under Settings → Connections).
3. The CLI saves a **CLI session** under `~/.config/adhd-hub/credentials.json` (mode `0600`). That file is local to this computer.

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

The CLI session is accepted as Bearer for REST and MCP. It is **not** the server access token. Revoke it in Settings → Connections (Windows / MCP / skills) or with `adhd-hub logout`. Dashboard password login is unchanged.

Project MCP snippets still interpolate an environment variable so they stay safe to commit. Existing clients that already use `ADHD_HUB_AUTH_TOKEN` keep working.

## MCP Auth / Authenticate (OAuth)

MCP clients that offer an **Auth** / **Authenticate** control can obtain a Hub Bearer for `/mcp` via Hub OAuth when the **Hub server** has:

- `ADHD_HUB_PUBLIC_URL` set to the URL agents and browsers use, and
- OAuth enabled (default; Hub env `ADHD_HUB_OAUTH_ENABLED` unset or `true`).

Flow (agent-agnostic — any MCP client that speaks MCP OAuth 2.1; Cursor is one verification target):

1. Point the client at `https://<hub>/mcp` (or your public Hub `/mcp`).
2. Choose **Auth** / **Authenticate** in the client.
3. Sign into the Hub UI if prompted, then press **Allow** on the consent page.

That issues an opaque OAuth access token for MCP only. It is not the server access token and is not a CLI connect session.

**Still supported (no Auth button required):**

- Static `Authorization: Bearer …` with `ADHD_HUB_AUTH_TOKEN` on the client (or `${env:ADHD_HUB_AUTH_TOKEN}` in MCP config).
- CLI `adhd-hub connect` / `adhd-hub login` (user-code + Allow in Settings → Connections).

**Rollback:** set `ADHD_HUB_OAUTH_ENABLED=false` on the Hub and restart. Discovery (`.well-known/…`) and `/api/oauth/*` turn off; static Bearer and CLI connect keep working. `adhd-hub doctor --hub <url>` always probes that Hub’s OAuth well-known when diagnosing a non-loopback Hub (or when `ADHD_HUB_PUBLIC_URL` is set), independent of any local `ADHD_HUB_OAUTH_ENABLED` in the doctor process; it warns on missing/malformed metadata. Unreachable Hub is a warning, not a hard failure.

## CLI wire-up flags

Both install scripts look for `uvx` first and install the CLI from **this Hub's** `/install/cli-wheel.url` (PEP 427 wheel matching the server), falling back to `git+https://github.com/uniskela/adhd-hub.git` if the wheel is missing. Prefer `uv tool install git+https://github.com/uniskela/adhd-hub.git` only when you want a standalone CLI without a running Hub. `connect` runs `login` automatically when no session is saved (`--no-login` skips that).

`--agents` controls which tools get **MCP / config wire-up** and which agents receive Hub **skills**. There is no assumed default: set agents in **Settings → Connections**, pass `--agents` / `-Agents`, or set `ADHD_HUB_CONNECT_AGENTS`. Use `*` to install skills for every skills.sh agent. Hub alias `claude` maps to skills.sh id `claude-code`.

```powershell
iex "& { $(irm $env:ADHD_HUB_PUBLIC_URL/install.ps1) } -Agents 'cursor,codex,claude'"
# or all agents:
iex "& { $(irm $env:ADHD_HUB_PUBLIC_URL/install.ps1) } -Agents '*'"
```

`--skill *` in the skills CLI means “both Hub skills” (projects + session), not “every coding agent.”

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

- **Cursor MCP** — project `.cursor/mcp.json` or user `~/.cursor/mcp.json` (`--scope user`), using `${env:ADHD_HUB_AUTH_TOKEN}` so the file stays token-free
- **Codex / Claude** — optional MCP blocks when listed in `--agents`
- **Cursor rule** — `.cursor/rules/adhd-hub.mdc` with `--cursor-rule`
- **AGENTS.md** — same reversible managed block as `adhd-hub setup`
- **Skills** — opt-in global `npx skills add` (`--skills`)
- **OpenClaw skills** — opt-in `npx skills add … -a openclaw`; hook URL/token still configured in **Settings → Connections**
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

In **Settings → Connections**, under **Coding companions**, toggle i-have-adhd / Graphify / RTK and **Save connect defaults**. Those choices are included in `/install.sh` and `/install.ps1`.

`connect` / `doctor` also list them when missing. You can pass flags manually:

```bash
adhd-hub connect /path/to/project --agents codex,claude --with-i-have-adhd --with-graphify
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
