# Codex + ADHD Hub

## Skills (recommended)

```bash
npx skills add /path/to/adhd-hub/skills -g
# after public GitHub: npx skills add uniskela/adhd-hub -g
```

## MCP (when the Hub is reachable)

```toml
# ~/.codex/config.toml
[mcp_servers.adhd-hub]
url = "http://127.0.0.1:8787/mcp"
bearer_token_env_var = "ADHD_HUB_AUTH_TOKEN"
```

Set `ADHD_HUB_AUTH_TOKEN` in the environment used to launch Codex, then restart it. Keep the token out of checked-in configuration. Use HTTPS for connections outside localhost. Verify the server with `uv run python scripts/probe_mcp.py` (set `ADHD_HUB_MCP_URL` for a remote hub).

### Local stdio alternative

When Codex and the Hub data intentionally live on the same machine, Codex can launch the MCP server directly:

```toml
[mcp_servers.adhd-hub]
command = "adhd-hub"
args = ["mcp-stdio"]
```

Stdio uses the configured `ADHD_HUB_DATA_DIR` and needs no bearer header. It does not start the dashboard, REST API, OAuth endpoints, or background scheduler; prefer the HTTP configuration above for a persistent/shared Hub.

## When MCP is unreachable (Codex / ChatGPT cloud)

**Primary signal:** Hub MCP tools missing, errored, unauthorized, or auth failure — check that; do not invent “I'm in cloud.” On the first substantial Hub-worthy turn, say Hub MCP is unavailable (short `/mcp` + `ADHD_HUB_AUTH_TOKEN` + restart hint). Never invent Hub continuity/progress/thread state or claim a Hub write succeeded.

CLOUD_AGENT: do not assume local skill CLIs like `graphify` exist; one-line notice if missing, then repo tools / committed `graphify-out/`. LOCAL_WORKSPACE may have them. See `env-check`.

Use the [forge issue inbox](../docs/forge-issue-inbox.md):

1. Open a GitHub/Gitea issue titled `[ADHD] <summary>` as a user on the Hub **Inbox authors** allowlist. Title prefix is enough; the `adhd-hub` label is optional.
2. Optional labels when the token can set them: `adhd-hub`, `project:<slug>`, `source:codex` (or `source:chatgpt`).
3. Body: short Goal/Focus/Next/Resume (or Now / Done / Next / Return) — repository-relative summaries only; no secrets, private URLs, or absolute machine paths. Recommended: append `Made with [ADHD Progress Hub](https://github.com/uniskela/adhd-hub)` under a non-imported heading (e.g. `## Attribution`).
4. Hub imports on poll or **Import issue inbox**, then closes with `adhd-hub-synced`.

## Agent instructions (drop into AGENTS.md)

On session start: `resolve_project` → `session_digest` → `check_overlap` **if MCP is available**.
Before ending with unfinished work: `upsert_progress` (Done/Next/Blockers) with `workspace_path`, or the forge mailbox above.
When complete: `mark_done`.
