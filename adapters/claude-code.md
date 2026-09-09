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

Optional: run `adhd-hub index` on a machine that has `~/.claude/projects` transcripts so unfinished phrases / pending replies are posted as **summaries** to the hub (never auto-completes).

Habits: `resolve_project` → `session_digest` → work → `upsert_progress` / `mark_done`.

## When MCP is unreachable (Claude remote / cloud)

Use the [forge issue inbox](../docs/forge-issue-inbox.md): issue title `[ADHD] …`, labels `adhd-hub` + optional `project:<slug>` + optional `source:claude` or `source:claude-code`, short progress body. The Hub imports and closes with `adhd-hub-synced` (never deletes).
