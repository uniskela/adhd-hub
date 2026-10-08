# MCP tool contract

Streamable HTTP and `adhd-hub mcp-stdio` expose the same catalog. Use
`tools/list` as the current contract: parameter descriptions document formats,
defaults, omission behavior and interactions. Names, defaults and validation
remain compatible; schema metadata does not add business rules.

The local inventory for issue [#117](https://github.com/uniskela/adhd-hub/issues/117)
on 2026-10-08 contains **26 tools and 95 described input parameters**, rather
than the historical 20-tool Glama catalog or the issue's earlier 23-tool count:

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

Resolve an existing project with `create_if_missing=false`, then use
`session_digest` for resume context. Supplying both an existing `project_slug`
and `workspace_path` to `resolve_project` persists that mapping even when
creation is disabled. `session_digest` updates reminder cooldowns, marks due
non-session reminders fired, and may build a missing wiki index. Use list tools
for reads without those effects.

For progress, supply a project slug or workspace path **and** the known
`thread_id`. A thread ID alone does not identify the project for this operation.
If `needs_thread_selection=true`, inspect `candidates` and choose the same Goal,
or explicitly start a separate outcome with `force_new_thread=true` and
`create_thread_if_missing=true`. With no thread ID and creation disabled, the
call writes project notes only. Omit `content` for routine structured checkpoints.

Session items and compact progress threads expose `completion.ready` and
`completion.reasons`, plus advisory `return_cue` coaching. Readiness uses stored
state; it does not verify a PR, deployment or remote task. When work remains,
checkpoint and pause. Mark done only after the actual outcome is complete.

## Output compatibility

The five tools `session_digest`, `upsert_progress`, `resolve_project`,
`mark_done` and `report_guidance_health` expose typed output schemas. Open-ended forge details remain extensible.
They retain existing text JSON and `structuredContent`, including absent keys,
nulls, timestamps and flat error objects; there is no new `result` envelope.
`report_guidance_health.guidance` remains a JSON **string**. `mark_done` still
returns the raw Thread on success, without adding completion or return-cue fields.

## Annotation audit

All four hints are explicit. `destructiveHint=true` means the call can replace
existing state, including status or cooldowns; it does not imply hard deletion.
`openWorldHint=true` includes optional configured forge, AI or OpenClaw calls.
Retries that refresh timestamps or scheduling are not advertised as idempotent.

| Tools | Read-only | Destructive | Idempotent | Open-world | Reason |
| --- | --- | --- | --- | --- | --- |
| `check_overlap`, `suggest_duplicate_threads`, `thread_merge_history`, `list_open_threads`, `list_projects`, `list_pending_actions`, `list_reminders`, `get_overview`, `suggest_next_up` | true | false | true | false | Local reads and ranking only. |
| `request_thread_merge`, `rename_project`, `delete_project` | false | false | true | false | Queue only; identical pending payloads are deduplicated. Execution requires separate human approval. |
| `resolve_project` | false | false | false | false | May register a project or add a workspace mapping; repeated mapping saves refresh project timestamps. |
| `upsert_project`, `report_guidance_health` | false | true | false | false | Replace registry/verification fields and refresh update/verification timestamps. |
| `upsert_thread`, `upsert_progress` | false | true | false | true | Replace continuity fields and rebuild projections; may add notes, invoke AI and sync forge/wiki. |
| `mark_done` | false | true | false | true | Replaces status; a linked issue is PATCHed again on retry and its projection may change. Local completion notes are added only on transition. |
| `dismiss_thread` | false | true | true | true | Soft-close preserves history; repeated dismissal skips notes, wiki and forge sync. |
| `pause_thread` | false | true | false | false | Replaces the resume cue and refreshes pause/update timestamps and lifecycle events. |
| `confirm_thread_relevant`, `snooze_thread_triage` | false | true | false | false | Replace cooldown/snooze state; repeated calls move scheduling and emit events. |
| `register_workspace` | false | false | true | true | Keeps a registered mapping and existing unfinished work; creates a default thread only when none exists, with optional forge/AI sync. |
| `set_reminder` | false | false | false | false | Each call creates a new reminder. |
| `session_digest` | false | true | false | false | Advances cooldowns, fires due reminders and may rebuild the local wiki index. |
| `push_openclaw_memory` | false | false | false | true | Sends a new digest to configured external memory. |

## Local quality checks

`tests/test_mcp_metadata.py` checks the current catalog, parameter descriptions,
annotation profiles and useful output fields. `tests/test_mcp_stdio.py` exercises
initialize, tools/list and representative success, selection and error calls over
the local subprocess transport. Run:

```bash
uv run pytest -q tests/test_mcp.py tests/test_mcp_metadata.py tests/test_mcp_results.py tests/test_mcp_stdio.py
uv run pytest -q
uv run ruff check src tests
git diff --check
```

The diagnostic baseline remains the issue's 2026-09-22 Glama scores:
`session_digest` 3.7/5 (parameters 3/5), `upsert_progress` 3.7/5 (parameters 2/5),
`report_guidance_health` and `upsert_thread` 3.8/5 (parameters 2/5).
The local pre-change catalog had no parameter descriptions. This change covers
all current inputs rather than deferring P2. CI uses local contract checks and
never calls Glama. After release and catalog rebuild, compare all six dimensions
and record the new scores in #117; no new external score is claimed here.
