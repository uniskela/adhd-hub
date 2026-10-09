# Duplicate-thread review and merge API

The dashboard's **Possible overlap** review helps you compare threads that may
describe the same outcome. Similar wording alone never authorizes a merge.
See [Dashboard](dashboard.md) for the user interface and
[Return-cue coaching](return-cue-coaching.md) for help recording a restart step.

## Suggestions

REST routes require your existing bearer token or browser session. HTTP MCP
uses authenticated `/mcp`; local stdio exposes the same tools.

| Operation | MCP tool | REST |
| --- | --- | --- |
| Check a planned task | `check_overlap(query, limit=5)` | `GET /api/overlap?q=…&limit=5` |
| Review an existing thread | `suggest_duplicate_threads(thread_id, limit=5)` | `GET /api/threads/{id}/duplicates?limit=5` |
| Queue a merge for review | `request_thread_merge(source_thread_id, target_thread_id)` | `POST /api/threads/{source_id}/merge` |
| Read retained history | `thread_merge_history(thread_id, limit=50)` | `GET /api/threads/{id}/merge-history?limit=50` |

Each suggestion includes the thread, score and reason, plus an `outcome`
(`same_outcome`, `related` or `uncertain`), evidence and `merge_allowed`.
Suggestion limits are 1–50. Reads do not change threads or queue actions.
The planned-task check always returns `merge_allowed: false` because a query
does not establish which two threads belong together.

## Human-confirmed merge

Only two different unfinished local threads in the same project with the same
nonempty normalized goal can be merged. Forge-backed or imported work stays
review-only. Before confirming, check that both goals represent one independently
finishable outcome.

Queue the direction with `POST /api/threads/source/merge` and
`{"target_thread_id":"target"}`, or the corresponding MCP tool. The source
is the duplicate; the target is the active thread you keep. Queueing changes
neither thread. Review both goals, continuity states and source identities:

- The target keeps its focus, next steps, resume cue and pause state.
- The source is locally dismissed with `merged_into` pointing to the target.
- The source's original fields, notes and events remain in retained history.
- No remote issue is changed.

After a person confirms the preview, an integration can approve with
`POST /api/pending-actions/{action_id}/approve` and `{"confirm_merge":true}`.
Agents must not confirm on the person's behalf. Reject through
`POST /api/pending-actions/{action_id}/reject`; rejection changes neither thread.
If the preview becomes stale, reject it and request a fresh review.

## Refusals and retained history

Unsafe queue requests return `pending: false`, `merge_allowed: false`, a reason
and review alternatives. Typical reasons include different projects, missing
goals, distinct outcomes, finished threads or forge authority. Keep those
outcomes separate or add an ordinary progress note linking them.

Unsafe or stale approval returns `409`; missing threads or actions return `404`.
A merged source is read-only: update its active target instead.

History includes each retained thread's original fields, notes and events,
including descendants from earlier merges. The history limit is 1–500 per
thread. Read the history endpoint to see source notes that do not appear in
the target's ordinary context view.

## Cursor fixtures and checks

For response examples, refusal codes, transaction guarantees and maintainer
fixtures, see the [merge implementation contract](https://github.com/uniskela/adhd-hub/blob/main/docs/internal/contracts/merge-dedupe-api.md).
