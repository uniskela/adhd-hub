# Codex + ADHD Hub

## Skills (recommended)

```bash
npx skills add /path/to/adhd-hub/skills -g
# after public GitHub: npx skills add uniskela/adhd-hub -g
```

## MCP

```toml
# ~/.codex/config.toml
[mcp_servers.adhd-hub]
url = "http://127.0.0.1:8787/mcp"
bearer_token_env_var = "ADHD_HUB_AUTH_TOKEN"
```

## Agent instructions (drop into AGENTS.md)

On session start: `resolve_project` → `session_digest` → `check_overlap`.
Before ending with unfinished work: `upsert_progress` (Done/Next/Blockers) with `workspace_path`.
When complete: `mark_done`.

Set `ADHD_HUB_AUTH_TOKEN` in the environment used to launch Codex, then restart it. Keep the token out of checked-in configuration. Use HTTPS for connections outside localhost. Verify the server with `uv run python scripts/probe_mcp.py` (set `ADHD_HUB_MCP_URL` for a remote hub).
