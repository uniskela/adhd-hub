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

## When MCP is unreachable (Codex / ChatGPT cloud)

Use the [forge issue inbox](../docs/forge-issue-inbox.md):

1. Open a GitHub/Gitea issue titled `[ADHD] <summary>`.
2. Labels: `adhd-hub`, optional `project:<slug>`, optional `source:codex` (or `source:chatgpt`).
3. Body: Now / Done / Next / Return cue only — no secrets.
4. Hub imports on poll or **Import issue inbox**, then closes with `adhd-hub-synced`.

## Agent instructions (drop into AGENTS.md)

On session start: `resolve_project` → `session_digest` → `check_overlap` **if MCP is available**.
Before ending with unfinished work: `upsert_progress` (Done/Next/Blockers) with `workspace_path`, or the forge mailbox above.
When complete: `mark_done`.
