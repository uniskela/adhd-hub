# Forge Backlog Manager (FBM) — implementation plan

Design: `docs/internal/superpowers/specs/2026-11-28-forge-backlog-manager-design.md`
Tracker: #370 (child of #15). Stages are tracked there as checklists, not
as separate issues.

**Not sequenced.** Placement in #15 and any release version need maintainer approval (decision D1).
Each slice is one PR with a `feat:` or `fix:` title, behind `ADHD_HUB_BACKLOG_ENABLED` until FBM-04.

Every slice runs `uv run --locked pytest -q`, `uv run --locked ruff check src tests` and
`graphify update .`, and updates the docs it touches.

## Prerequisite fixes (independent `fix:` PRs, recommended before FBM-01)

- **P1 (F1):** derive `source_issue_url` and reconcile `html_url` from the pinned identity, not the
  profile config. Code: `forge/facade.py` (`sync_forge_now` reconcile loop, `_source_url`). Test: two
  connection profiles, a thread pinned to repo A, and its URL never naming repo B. Add a repair pass
  for stored URLs that disagree with identity (rewrite only `source_issue_url`).
- **P2 (F2, if D5 is approved):** inbox close-on-import uses `not_planned`. Code: `board_sync.mark_issue_imported`.
  Changelog note.

## FBM-01 — Read-only scanner

1. `src/adhd_hub/backlog/__init__.py`, `backlog/models.py` (Pydantic: `ScanRequest`, `ScanSummary`,
   `ScanItem`, enums `IssueKind`, `ProtectionFlag`).
2. Store: `backlog_scans`, `backlog_scan_items` tables and CRUD (`Store._init_schema`).
3. `backlog/scanner.py`: list issues through the existing listing code (refactor a shared
   `iter_issue_pages(cfg, state, selector)` out of `repo_sync.discover_issue_payloads` without
   changing its behaviour), per-issue comment count, and timeline flags only when needed for
   protection. Uses `credentials_apply_to_pinned` host matching.
4. Job kind `backlog_scan` on `ForgeJobQueue`. Scan status is persisted in `backlog_scans`.
5. REST: `POST/GET /api/backlog/scans…` behind the feature flag.
6. Tests: `tests/test_backlog_scanner.py` (GET-only transport mock, GitHub/Gitea pagination, PR
   exclusion, truncation, read-only token, flag off → 404).

## FBM-02 — Deterministic and AI-assisted recommendations

1. `backlog/classify.py`: kind precedence, protection flags, title normalisation and stems, series
   detection, reference edges, union-find clusters. Reuse `overlap.tokenize`, `jaccard` and
   `normalize_goal`, and `thread_refresh.issue_snapshot`.
2. `backlog/recommend.py`: default disposition table (§5.4), candidate destinations through
   `check_overlap`.
3. Fixture `tests/fixtures/backlog/ts6_like.json` (80 synthetic issues modelled on the TS6 shapes:
   scout bugs and features, P10 review rounds, finding assessment/implementation pairs, trackers).
   No real issue text.
4. `AiConfig.backlog_suggestions` (default false) with the Settings → AI helpers toggle.
5. `backlog/ai_recommend.py`: payload minimiser and scrubber, batching, prompt v1, Pydantic schema
   (`extra="forbid"`), ref and candidate allowlists, merge rules (§8.6). Reuses `ai_client` URL,
   header and error-hint helpers (refactor `generate_ai_scan_line`'s HTTP part into a shared
   `_post_chat_completion`).
6. `backlog_ai_recommendations` table and cache keying.
7. REST: `POST /api/backlog/scans/{id}/ai-suggestions`, `POST/GET/PATCH /api/backlog/plans…` (draft
   only; no apply yet).
8. Tests: `test_backlog_classify.py` (determinism snapshot, `[ADHD] Bug:` protected, goal identity),
   `test_backlog_ai.py` (opt-in matrix, timeout, 500, malformed, partial validity, injection
   fixtures, cache hit/miss, cancel between batches).

## FBM-03 — Durable local migration

1. Tables: `forge_issue_snapshots`, `forge_issue_snapshot_comments`, `thread_source_links`,
   `backlog_plan_items` state columns, `backlog_operations`, `backlog_operation_steps`.
2. `backlog/snapshot.py`: full capture with complete comment pagination, size limits, `complete`
   flag and canonical hashing.
3. `Store.apply_backlog_item_local(...)`: one transaction per item for migrate (new thread),
   consolidate (link and note on an existing or new thread), reference, and mirror-to-migrate
   handoff. Includes the cross-table retained-identity check.
4. `backlog/executor.py`: durable journal, lease and heartbeat, idempotency keys, verify step (fresh
   connection), startup sweep to `interrupted`, resume and cancel.
5. `PendingActionKind.backlog_plan_apply` and the approve branch (`confirm_backlog_plan`, hash check)
   in `HubService.approve_pending_action`.
6. Integration changes: `import_forge_inbox` and discovery skip retained identities;
   `merge_blocked_reason` treats retained links as `forge_authoritative`; board sync ignores
   handed-over threads.
7. Events: `backlog.*` and `thread.source_*` constants; metadata allowlist keys.
8. Backup/export includes the new tables.
9. Tests: `test_backlog_local_apply.py` (injected failures at each statement, idempotent re-run,
   kill-and-resume, handoff preservation, inbox skip, merge refusal, no forge calls, never `done`),
   plus an extension of `test_merge_dedupe.py`.

## FBM-04 — Verified remote reconciliation and recovery

1. `PendingActionKind.backlog_remote_reconcile`; remote preview rendering exact mutations.
2. Interactive-session requirement for remote approval (D2): distinguish browser or CLI-device
   sessions from the static bearer token in `auth.py`.
3. Remote steps: precheck (fresh verification, remote freshness, optional backup gate), label,
   marker comment, close with `not_planned` or detected `duplicate`, postcheck. Write scope check
   before the phase starts.
4. Retry and backoff (`Retry-After`, 429, secondary rate limit), permanent failure mapping.
5. Recovery: reopen (remote, approved), detach (local, pending action).
6. Tests: `test_backlog_remote.py` (ordering assertions, drift → `needs_review`, idempotent label and
   comment across restart, close reason never `completed`, 403 without an interactive session,
   count mismatch 409, reopen).

## FBM-05 — Dashboard, CLI and MCP

1. UI: Backlog card, scan view, plan editor, preview and approve, progress and recovery, Forge
   cleanup tab, thread Sources panel (`src/adhd_hub/ui/js/backlog.mjs`, reusing `overlap-review.mjs`
   patterns, `confirmDialog` and SSE invalidation). Bump the `sw.js` cache id.
2. CLI: `adhd-hub backlog …` subcommands over REST with the saved session; TTY-only approve.
3. MCP tools from spec §14.2 in `mcp_app.py` with `mcp_results.py` shapes and the
   `mcp-tool-contract.md` checklist.
4. Docs: new public `docs/public/forge-backlog-manager.md` (+ `docs/manifest.json` entry), links from
   `forge-issue-inbox.md`, `merge-dedupe-api.md` and `dashboard.md`; internal contract
   `docs/internal/contracts/forge-backlog-manager-api.md` with fixtures.
5. Tests: JS smoke (`tests/js/backlog_smoke.mjs`), browser script (`scripts/backlog_browser.py`),
   MCP listing and schema tests, CLI TTY refusal.

## FBM-06 — Project policies and backlog health

1. `backlog_policies` table, Pydantic policy model with defaults and validation, policy hash and
   staleness wiring into plans and approvals.
2. Policy editor in the project Issue sync card; `adhd-hub backlog policy`.
3. `backlog/health.py`: signals from the latest scan, one line per project, snooze.
4. `session_digest` optional `backlog_health` field (additive).
5. Tests: `test_backlog_policy.py`, `test_backlog_health.py` (no forge calls, snooze window, digest
   field only when the threshold is crossed).
6. Guidance follow-up (D6) as its own docs/skills PR, if approved.

## Verification of the whole feature

A dry run against a disposable test repository (never a live project) seeded with the TS6-like
fixture: scan → plan → local apply → kill/resume → remote approval → close → reopen. Record the
evidence in the FBM-04 and FBM-05 PR descriptions.
