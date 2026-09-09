# ADHD Hub MCP tools (reference)

| Tool | Purpose |
|------|---------|
| `session_digest` | Stale/open threads + reminders for a workspace |
| `check_overlap` | Rank open threads vs a query |
| `resolve_project` | Map cwd → project slug |
| `list_projects` / `upsert_project` | Project registry |
| `list_open_threads` | Browse unfinished work |
| `upsert_thread` | Create/update a thread |
| `upsert_progress` | Append PROGRESS.md; returns `thread_id` (set `create_thread_if_missing=false` for notes only) |
| `mark_done` | Close a thread |
| `set_reminder` | once / session / daily / random |

Setup: configure the `/mcp` endpoint for an ADHD Hub instance you operate and an `Authorization: Bearer` header using an environment variable (for example, `ADHD_HUB_MCP_TOKEN`). Prefer HTTPS; plain HTTP is only for loopback, Docker, or a private LAN/Tailscale network controlled by the operator. Browser session cookies only authorize REST, not MCP. Run `uv run python scripts/probe_mcp.py` from the repo to verify tool discovery. Never paste credentials into progress notes. The Hub stores only the requested project/thread/reminder fields in its configured local SQLite/Markdown directory; this protocol sends no full transcripts.

Hub UI: `{ADHD_HUB_PUBLIC_URL}/ui` when configured.
