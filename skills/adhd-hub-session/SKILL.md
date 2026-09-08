---
name: adhd-hub-session
description: >-
  ADHD Progress Hub session protocol — call MCP adhd-hub on start, pause, and
  finish so unfinished coding work is not lost across Cursor, Codex, and Claude.
  Use when starting/resuming a project, pausing mid-task, marking work done, or
  setting a reminder.
---

# ADHD Hub — session protocol

Requires MCP server **`adhd-hub`** (HTTP). Never invent hub state; only report tool results. Never put secrets or full chat transcripts in notes.

## Session start / resume

1. `resolve_project` with `workspace_path` (create_if_missing true if this is a known codebase).
2. `session_digest` with the same `workspace_path` and a short `query` for the task.
3. `check_overlap` with the project/migration name.
4. If hits exist, tell the user what was left open and offer to resume from progress notes.

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

Also `upsert_thread` if this is a new unfinished thread.

## Finished

`mark_done` with the thread id and a one-line note.

## Remind later

If the user asks to be nudged: `set_reminder` (`once` / `session` / `daily` / `random`).
