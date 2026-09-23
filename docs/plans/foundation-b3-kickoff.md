---
search:
  exclude: true
---

# Foundation B3 kickoff — activity ledger, live UI & sync health

Tracking issue: [#75](https://github.com/uniskela/adhd-hub/issues/75)  
Parent: [#71](https://github.com/uniskela/adhd-hub/issues/71) · Roadmap: [#15](https://github.com/uniskela/adhd-hub/issues/15) · Later consumer: [#72](https://github.com/uniskela/adhd-hub/issues/72)

This plan **started** the B3 product train. B3 shipped in full via [#152](https://github.com/uniskela/adhd-hub/pull/152) (closes [#75](https://github.com/uniskela/adhd-hub/issues/75)). Current product train is Wave 6 [#52](https://github.com/uniskela/adhd-hub/issues/52). Keep [#117](https://github.com/uniskela/adhd-hub/issues/117) deferred and separate.

## Context (after Notes)

- Baseline: **v0.13.0**; Notes & context reader landed via PR [#136](https://github.com/uniskela/adhd-hub/pull/136).
- Foundation B1/B2 and Forge job visibility are shipped; they are **not** a substitute for a durable Hub event ledger or live UI invalidation.
- Public sequence: B3 #75 ✅ → **NOW = Wave 6** [#52](https://github.com/uniskela/adhd-hub/issues/52) → 7 [#54](https://github.com/uniskela/adhd-hub/issues/54) → 8 [#55](https://github.com/uniskela/adhd-hub/issues/55). See [improvement-roadmap.md](improvement-roadmap.md).

## Train slices (ordered)

| Slice | Outcome | Notes |
| --- | --- | --- |
| **B3.1 Event ledger** | Durable, versionable structured events after committed mutations | First implementation PR(s); substrate for history + later SSE/stats |
| **B3.2 SSE live invalidation** | Authenticated same-origin SSE; lightweight invalidation; refetch remains truth | Depends on publishable events (or a thin bus fed by the same boundary) |
| **B3.3 Sync / connection health** | Calm last-success / last-failure / conflict / job cues | Builds on Forge jobs; no monitoring dashboard |

Implementation modules: `adhd_hub.events` (publish boundary + redaction), `Store.activity_events`, `GET /api/events` + `/api/events/stream`, `GET /api/sync-health`, UI `live.js` / `sync-health.js`.

Do not fold MCP schema quality (#117) or Wave work into these slices.

## First slice only — immediate next PR (B3.1)

**Goal:** land a minimal durable event ledger that other slices can consume, without live UI or sync-health UI yet.

### In scope

- SQLite (or existing store) table for append-only Hub activity events with: id, schema/version, type, timestamp, project/work/thread ids when known, actor/source when safe, minimal JSON metadata.
- Shared publish helper used after durable commit from a small set of high-value mutations (prefer thread progress / status and forge reconcile success/failure first).
- Idempotency keys or equivalent so sync echoes do not duplicate events (reuse B2 revision/fingerprint where available).
- Privacy: no transcripts, secrets, private Hub URLs, or machine paths in event payloads.
- Unit tests for persistence, idempotency, and privacy redaction/refusal of unsafe fields.
- Brief maintainer note in code or this plan when the publish boundary is introduced.

### Out of scope for the first implementation PR

- SSE endpoint, EventSource client, or UI auto-refresh.
- Sync-health panel / connection status chrome.
- Full event-type coverage for every mutation path (expand in follow-ups).
- Analytics dashboard or #72 aggregations.
- Redis or external bus; in-process fan-out can wait until SSE.
- Any #117 MCP schema work.

### Publish boundary (maintainer note)

After B3.1 lands, call `HubService.publish_hub_event` / `publish_activity_event`
**only after** the mutation is durably committed. Shared boundary covers REST,
MCP, scheduler, and UI. Never put transcripts, secrets, private Hub URLs, or
machine paths in event metadata. Idempotency keys should reuse B2
`external_fingerprint` / thread `state_fingerprint` where available so sync
echoes do not duplicate rows.

### Suggested verify for B3.1

- `uv run pytest` (new ledger tests + regression).
- `uv run ruff check src tests`.
- Manual: mutate a thread via API/MCP and confirm a row appears with expected type and no sensitive fields.

## Follow-on slices (later PRs)

**B3.2:** authenticated SSE stream of invalidation hints; debounce; reconnect + visibility refresh; safe degradation without SSE.

**B3.3:** expose last successful/failed forge reconcile, concise error, conflicts, useful job state; optional compact change history from the ledger (no generic undo).

Acceptance criteria for the full train remain on [#75](https://github.com/uniskela/adhd-hub/issues/75).

## Non-goals (whole train)

- External analytics SaaS; public activity feed; WebSocket unless SSE proves insufficient; heavy distributed event infrastructure.
