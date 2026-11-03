# Coding-agent onboarding audit and follow-ups

Reviewed 2026-11-03 against the current connection helpers, CLI login, project
setup, generated POSIX/PowerShell installers, probe script, adapters, Settings UI
and existing connect/authentication tests. Official client references are linked
in [the connection guide](../public/connect.md#agent-setup-and-authenticated-diagnostics).

## Verified findings

- Claude user registrations targeted `~/.claude/mcp.json`; documented user scope
  is the top-level `mcpServers` in `~/.claude.json`. The previous header used
  Cursor's `${env:NAME}` rather than Claude's `${NAME}` expansion.
- Cursor's existing project/user JSON paths and interpolation were correct.
  Codex's `bearer_token_env_var` was correct, but its replacement could overwrite
  options or append a duplicate when an existing TOML table name was quoted.
- Connect defaulted to no agents, and configuration presence plus REST health
  could produce a green connected banner without any MCP initialization.
- CLI short-code sessions already authenticated REST and MCP on the server,
  but generated agent configs did not read the CLI credentials file. The login
  warning existed; the broader setup wording obscured that distinction.
- Doctor primarily inspected Cursor/Codex config presence, omitted Claude, and
  could send OpenClaw test notifications and POST guidance verification.

## Resulting behavior

The new `agents` commands share registrations with connect and the existing
merge helpers. Read-only status/doctor and the probe script use one bounded
Streamable HTTP probe. Registration, environment credential availability, direct
MCP access and launched-agent verification remain separate reported facts.

Project/user/local conflicts block adding another entry. Existing custom auth
and other settings survive; unsupported layouts are refused. Writes are atomic
and retain a private pre-edit backup. Installer empty selections now prompt only
interactively, otherwise fail with explicit target instructions. Selected unusable
MCP registrations fail setup/connect and cannot produce a green connected banner.

Compatibility notes: `connect --scope project` now applies to Claude and Codex
as well as Cursor. Existing user entries are detected and require scope selection
or manual cleanup. `use-hub` reuses existing scopes by default rather than adding
parallel registrations. HTTPS is required outside loopback. Doctor no longer writes
Hub guidance verification or sends OpenClaw test notifications. Standalone CLI
login, static bearer authentication, OAuth and stdio remain supported. The probe
script now uses injected environment credentials only, with no implicit `.env`
lookup. No server authentication architecture changes or new dependencies.

## Deliberate follow-ups

- A remote MCP proxy backed by a saved CLI session could avoid separately
  injecting bearer credentials. Design its token storage, revocation, transport
  and process lifecycle separately; no proxy is included in this change.
- Client-native runtime verification and access to per-client OAuth stores need
  separate adapters and cross-platform validation. Current diagnostics never
  claim to have launched or authenticated a coding agent.
- Native Windows/macOS, service-manager and real client OAuth smoke tests remain
  operator validation. Automated coverage uses temporary homes, mock transports,
  the real Hub test app and a loopback streaming MCP server without production
  credentials.

No committed `graphify-out/wiki/` tree was present to update. Public setup and
adapter documentation carry the updated connection contract; the local graph is
refreshed using `graphify update .`.
