# Claude Code + ADHD Hub

ADHD Hub is **not** a Claude Code plugin (see [claude-adhd](https://github.com/shaheer-00/claude-adhd) for that).

## Skills

```bash
npx skills add /path/to/adhd-hub/skills -g -a claude-code
# later: npx skills add uniskela/adhd-hub -g
```

## MCP (when the Hub is reachable)

```json
{
  "mcpServers": {
    "adhd-hub": {
      "type": "http",
      "url": "http://127.0.0.1:8787/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_TOKEN"
      }
    }
  }
}
```

### Local stdio alternative

For a local Claude Code process with local Hub data:

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

Stdio uses the configured `ADHD_HUB_DATA_DIR` and needs no bearer header. It does not start the dashboard, REST API, OAuth endpoints, or background scheduler; prefer the HTTP configuration above for a persistent/shared Hub.

Optional: run `adhd-hub index` on a machine that has `~/.claude/projects` transcripts so unfinished phrases / pending replies are posted as **summaries** to the hub (never auto-completes).

Habits: `resolve_project` → `session_digest` → work → `upsert_progress` / `mark_done`.

## When MCP is unreachable (Claude remote / cloud)

**Primary signal:** Hub MCP tools missing, errored, unauthorized, or auth failure — check that; do not invent “I'm in cloud.” On the first substantial Hub-worthy turn, say Hub MCP is unavailable (short `/mcp` + `ADHD_HUB_AUTH_TOKEN` + restart hint). Never invent Hub continuity/progress/thread state or claim a Hub write succeeded.

CLOUD_AGENT: do not assume local skill CLIs like `graphify` exist; one-line notice if missing, then repo tools / committed `graphify-out/`. LOCAL_WORKSPACE may have them. See `env-check`.

Use the [forge issue inbox](../docs/forge-issue-inbox.md): issue title `[ADHD] …` (sufficient for allowlisted authors), optional labels `adhd-hub` + `project:<slug>` + `source:claude` or `source:claude-code`, short Goal/Focus/Next/Resume body (repository-relative summaries only; no secrets/private URLs/absolute machine paths). Skip labels if the token cannot set them. The creating account must be on the Hub **Inbox authors** allowlist. The Hub imports and closes with `adhd-hub-synced` (never deletes).
