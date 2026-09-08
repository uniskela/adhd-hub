# Codex + ADHD Hub

## Skills (recommended)

```bash
npx skills add /path/to/adhd-hub/skills -g
# after public GitHub: npx skills add uniskela/adhd-hub -g
```

## MCP

```toml
# ~/.codex/config.toml (example — exact MCP table keys may vary by Codex version)
[mcp_servers.adhd-hub]
url = "http://127.0.0.1:8787/mcp"
http_headers = { Authorization = "Bearer YOUR_TOKEN" }
```

## Agent instructions (drop into AGENTS.md)

On session start: `resolve_project` → `session_digest` → `check_overlap`.
Before ending with unfinished work: `upsert_progress` (Done/Next/Blockers) with `workspace_path`.
When complete: `mark_done`.
