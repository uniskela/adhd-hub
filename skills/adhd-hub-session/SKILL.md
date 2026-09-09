---
name: adhd-hub-session
description: >-
  ADHD Progress Hub session protocol — call MCP adhd-hub on start, pause, and
  finish so unfinished coding work is not lost across Cursor, Codex, and Claude.
  Use when starting/resuming a project, pausing mid-task, marking work done, or
  setting a reminder.
---

# ADHD Hub — session protocol

Requires MCP server **`adhd-hub`** (Streamable HTTP at `/mcp`). If tools are unavailable, say so briefly, continue the authorized work, and provide a concise local handoff; never claim a hub write succeeded. Never invent hub state; only report tool results. Never put secrets or full chat transcripts in notes.

## Session start / resume

1. `resolve_project` with `workspace_path` (create_if_missing true if this is a known codebase).
2. `session_digest` with the same `workspace_path` and a short `query` for the task.
3. `check_overlap` with the project/migration name.
4. If hits exist, summarize relevant open work and incorporate it when it matches the current task. Do not interrupt already authorized work just to reconfirm it.

## Leaving work incomplete

Call `upsert_progress` with:

- `workspace_path` and/or `project_slug` from resolve
- `source_tool`: `cursor` | `codex` | `claude` | etc.
- Structured content:

```markdown
## Done
- …

## Next
- …

## Blockers
- … (or none)
```

Keep the `thread_id` returned by `upsert_progress`: it already keeps or creates an open thread. Do not also create a duplicate with `upsert_thread`. Use `upsert_thread(thread_id=...)` to update a known thread, or create one separately only for distinct work. Progress appends are not idempotent; after an ambiguous timeout, inspect the digest before retrying.

## Finished

`mark_done(thread_id=...)` with the known id for the completed task and a one-line note. Never close unrelated overlap hits. To write final progress without creating an open thread, use `upsert_progress(create_thread_if_missing=false)` before marking the task done.

## Remind later

If the user asks to be nudged: `set_reminder` (`once` / `session` / `daily` / `random`). Supply `due_at_iso` with an explicit timezone offset for a one-time reminder; ask for a time only if it cannot be inferred.
