# Duplicate-thread review and merge API

Wave 7 backend contract for [#54](https://github.com/uniskela/adhd-hub/issues/54).
The visual review UI is a separate task. Return-cue coaching remains separate.

## Suggestions

All REST routes below require the existing bearer token or browser session.
HTTP MCP uses the existing authenticated `/mcp`; local stdio uses the same service.

| Operation | MCP tool | REST |
|---|---|---|
| Planned task overlap (compatible) | `check_overlap(query, limit=5)` | `GET /api/overlap?q=…&limit=5` |
| Existing thread duplicate review | `suggest_duplicate_threads(thread_id, limit=5)` | `GET /api/threads/{id}/duplicates?limit=5` |
| Queue merge review | `request_thread_merge(source_thread_id, target_thread_id)` | `POST /api/threads/{source_id}/merge` |
| Retained history | `thread_merge_history(thread_id, limit=50)` | `GET /api/threads/{id}/merge-history?limit=50` |

Suggestions preserve `query` and `hits[].thread`, `score`, `reason`. The existing
`score_thread` score and threshold determine retrieval and ordering. Equal scores
sort by thread ID. There is no second ranker, embedding lookup or AI call.
Existing-thread review searches unfinished, unmerged threads in the same project,
including blocked work. `limit` is 1–50. The candidate scan uses the existing
500-thread store bound; suggestions are advisory, not a complete inventory.

New fields on each hit:

| Field | Meaning |
|---|---|
| `outcome` | `same_outcome`, `related`, or `uncertain` |
| `evidence` | Stable machine-readable reasons such as `goal_exact_match`, `distinct_known_goal`, `no_recorded_goal`, `source_goal_required`, `same_project` |
| `merge_allowed` | Whether this particular pair satisfies the safe local merge policy |
| `merge_blocked_reason` | Stable refusal code, or null |

Only exact goal equality after NFC Unicode normalization, case folding and
whitespace normalization supplies `same_outcome` evidence. Punctuation, issue
numbers, word order and negation remain significant. A shared title, project,
workspace, next step or high overlap score cannot authorize a merge. Differently
worded goals stay `related` even if a human might ultimately decide they describe
the same outcome; missing goals stay `uncertain`. This deliberately favors missed
duplicates over merging separate outcomes. Humans must still check that the
recorded goal is actually one independently finishable outcome.

The free-text `check_overlap` surface cannot determine pair ownership and always
returns `merge_allowed: false`; it compares the planned query to recorded goals.
Existing-thread suggestions add `thread_id` and
`alternatives: ["review_separately", "link_in_progress_note"]`. These reads never
create an action or mutate a thread.

## Human-confirmed merge

A merge is allowed only for two different unfinished threads with the same
nonempty normalized goal and the same nonempty project slug. Both must resolve
to local work under Foundation B1 and have no forge identity, import provenance
or legacy `forge_issue:<id>` mapping. Project-inherited forge work is review-only
even before an issue is linked. No merge path calls a forge adapter or changes a
remote issue's title, body, labels, identity or open/closed state.

Queue the proposed direction:

```http
POST /api/threads/source/merge
Content-Type: application/json

{"target_thread_id":"target"}
```

Success returns `pending: true`, `merge_allowed: true` and `action`. The action
has `kind: "merge_threads"` and a `payload` containing complete `source` and
`target` thread snapshots, resolved `work_sources`, policy and safety decision.
The source is the duplicate to retain in history; the target is the active thread
to keep. Queueing changes neither thread. Identical pending requests reuse an
action. There is no MCP approval tool.

The UI must display both goals, both continuity states (focus, next steps,
blocker, resume and pause), source identity and the merge direction, and explain:

- The target's active state is kept, including all three next steps and pause.
- The source is marked locally dismissed and gets `merged_into: target_id`.
- All other source fields, source references, original notes and events are retained.
- The source's different next/resume information remains available in retained history;
  it is not concatenated, truncated or silently substituted into the target.

After a human explicitly confirms that preview:

```http
POST /api/pending-actions/{action_id}/approve
Content-Type: application/json

{"confirm_merge":true}
```

Missing/false confirmation is HTTP 400; strings such as `"true"` are HTTP 422.
Existing approval calls for other action kinds keep their previous contract.
The current generic approval banner cannot approve a merge without this body.
Agents must not send confirmation on behalf of the human.

Approval rereads snapshots and resolved ownership inside a SQLite write
transaction. Changed state or newly attached forge provenance refuses the action;
the human must reject the old action and request/review a fresh one. Source
archival, target timestamp, a merge milestone, two `thread.merged` activity events
and action approval commit together. A failed write rolls all of them back. The
underlying history rows and IDs are never moved or deleted.

Approval returns `approved: true`, `action`, and:

```json
{"result":{"source_thread_id":"source","target_thread_id":"target",
           "history_preserved":true,"remote_changed":false}}
```

Retries return `already_resolved: true` without another merge. Reject via existing
`POST /api/pending-actions/{id}/reject`; rejection changes neither thread.
SQLite is authoritative. A local wiki/index write failure after commit returns
`projection_warning` with the successful approval; retry local project refresh,
not the merge. Live event hints are published after commit. No forge write runs.

## Refusals and retained history

An unsafe queue request returns HTTP 200 with `pending: false`,
`merge_allowed: false`, `reason`, a human-readable `message`, and review/link
alternatives. Linking means an ordinary thread-scoped progress note referring
to the other thread or source issue; it does not change source ownership.

| Reason | Required review |
|---|---|
| `same_thread` | Choose two different threads |
| `already_merged` | Use the active target |
| `unfinished_required` | Do not consolidate completed/dismissed work |
| `different_projects` | Keep project outcomes separate |
| `goal_required` | Record both finishable outcomes first |
| `distinct_outcomes` | Review separately; similarity alone is insufficient |
| `forge_authoritative` | Review source issues; preserve forge authority and identities |

Missing thread/action is HTTP 404. Unsafe or stale approval is HTTP 409 with
`merge_refused:<reason>` or `merge_preview_stale:…`. Invalid bounded input is 422.
Ordinary upsert/status transitions of a retained source fail with
`merged_thread_read_only`; update the target instead. New `Thread.merged_into`
defaults to null, including old databases after additive schema migration.

History returns `thread_id`, `limit_per_thread`, and `items[]`, each containing
the full original `thread`, its `notes[]` and `events[]`. `limit` is 1–500 per
thread. Notes retain their original `thread_id`; events retain their original
work/thread IDs. Multi-stage merges include all retained descendants. Read the
history endpoint even when the target's ordinary notes/context view shows only
its own notes. No transcript bodies or remote histories are fetched.

## Cursor fixtures and checks

- [`cases.json`](https://github.com/uniskela/adhd-hub/blob/main/tests/fixtures/merge_dedupe/cases.json)
  supplies goals, expected evidence classification and policy results for local,
  related, negated, missing-goal and forge-backed scenarios.
- `tests/fixtures/merge_dedupe/responses.json` supplies example suggestion,
  queued approval and retained-history response bodies from the actual service.
- `tests/test_merge_dedupe.py` exercises these fixtures, authentication, MCP
  discovery/calls, explicit confirmation, idempotency, source identity, stale
  review, history preservation, multi-stage merge and injected write failures.
