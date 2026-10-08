# MCP tool contract

Streamable HTTP and `adhd-hub mcp-stdio` expose the same tool catalog. Use
`tools/list` for current parameter descriptions, defaults and validation.
See [Connect](connect.md) to connect your client.

| Area | Tools |
| --- | --- |
| Discovery | `check_overlap`, `list_open_threads`, `list_projects`, `list_reminders`, `get_overview`, `suggest_next_up` |
| Project identity | `resolve_project`, `upsert_project`, `register_workspace` |
| Pending human approval | `rename_project`, `delete_project`, `list_pending_actions`, `request_thread_merge` |
| Duplicate review | `suggest_duplicate_threads`, `thread_merge_history` |
| Continuity | `upsert_thread`, `upsert_progress`, `session_digest`, `report_guidance_health` |
| Lifecycle and triage | `mark_done`, `pause_thread`, `dismiss_thread`, `confirm_thread_relevant`, `snooze_thread_triage` |
| Reminders and integration | `set_reminder`, `push_openclaw_memory` |

## Choosing the next call

Resolve the existing project with `create_if_missing=false`, then call
`session_digest` for resume context. Supplying an existing `project_slug` and
`workspace_path` to `resolve_project` saves their mapping even when creation
is disabled. `session_digest` updates reminder cooldowns, fires due non-session
reminders and may build a missing wiki index. Use list tools for reads without
those effects.

For `upsert_progress`, supply the project slug or workspace path and the known
`thread_id`. A thread ID alone does not identify the project for this call.
If `needs_thread_selection=true`, inspect `candidates` and choose the thread
with the same goal. For a separate outcome, explicitly use
`force_new_thread=true` and `create_thread_if_missing=true`. Without a thread
ID and with creation disabled, the call writes project notes only. Omit
`content` for routine structured checkpoints.

`completion.ready` reflects stored state and does not verify PRs, deployments
or remote tasks. When work remains, checkpoint and pause; mark done only when
the outcome is complete. [Return-cue coaching](return-cue-coaching.md) helps
make the resume step useful without blocking a save or pause.

`session_digest` and `get_overview` also expose the optional advisory
[Clock-Off](clock-off-api.md) state and temporary overrides.

## Output compatibility

`session_digest`, `upsert_progress`, `resolve_project`, `mark_done` and
`report_guidance_health` publish typed output schemas. Responses retain text
JSON and `structuredContent`, with no extra `result` envelope. Clients should
handle absent keys, nulls and flat error objects, and allow extensible forge
details. `report_guidance_health.guidance` is a JSON string. `mark_done` returns
the raw Thread on success.

## Annotation audit

Use the annotations in `tools/list` when deciding how to call a tool:

- `readOnlyHint` identifies local reads without mutation.
- `destructiveHint` includes replacing continuity state or reminder cooldowns;
  it does not necessarily mean hard deletion.
- `idempotentHint` is false when retries refresh timestamps or scheduling.
- `openWorldHint` includes optional configured forge, AI or OpenClaw calls.

Queued rename, delete and merge actions require separate human approval.
See [Duplicate-thread review](merge-dedupe-api.md) for merge confirmation.

## Local quality checks

For the complete annotation table, output guarantees and maintainer checks,
see the [MCP implementation contract](https://github.com/uniskela/adhd-hub/blob/main/docs/internal/contracts/mcp-tool-contract.md).
