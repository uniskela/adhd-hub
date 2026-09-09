# Forge issue inbox (remote / cloud agents)

Agents that cannot reach a private Tailscale Hub MCP can still leave unfinished work for ADHD Hub by opening forge issues. That includes **Cursor Cloud**, **Codex / ChatGPT cloud**, **Claude Code / Claude remote**, and similar sandboxed runners.

They *can* use GitHub/Gitea. The Hub polls those issues and turns them into threads.

## Enable

1. Settings → Connections → Forge: turn on **Board / issues** and **Import cloud-agent issues (inbox)**.
2. Save. Optionally click **Import issue inbox** once to test.
3. The Hub also polls on `ADHD_HUB_FORGE_INBOX_CRON` (default every 15 minutes).

## Agent protocol (any tool)

1. Create an issue titled `[ADHD] <short summary>`.
2. Labels:
   - required: `adhd-hub`
   - optional: `project:<slug>`
   - optional: `source:codex` | `source:chatgpt` | `source:cursor` | `source:claude` | `source:claude-code`
3. Body: short Now / Done / Next / Return cue (no secrets).
4. After import, Hub **closes** the issue and adds `adhd-hub-synced` (never deletes).

## Skills on remote agents

Install Hub skills wherever the agent runs:

```bash
# Cursor / Codex / generic
npx skills add uniskela/adhd-hub -g

# Claude Code agent adapter
npx skills add uniskela/adhd-hub -g -a claude-code
```

Also keep a project `AGENTS.md` (via `adhd-hub setup` / `connect`) so every tool sees the same continuity rules. The session skill falls back to this forge mailbox when MCP is unreachable.

## Operator API

```bash
curl -sS -X POST -H "Authorization: Bearer $ADHD_HUB_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  http://127.0.0.1:8787/api/forge/inbox/import
```

## Related adapters

- [Cursor](../adapters/cursor-mcp.json) / [Cursor rule](../adapters/cursor-rule.mdc)
- [Codex](../adapters/codex.md)
- [Claude Code](../adapters/claude-code.md)
