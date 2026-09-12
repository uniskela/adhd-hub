# Foundation B2b — explicit outbound mutations, promote, scheduler, Needs review

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete #74 after B2a: remote-first `mark_done`/reopen, local→repo promote/link, periodic reconcile with lock/backoff, and minimal Needs review persistence.

**Architecture:** Extend `RepoWorkSync` / `ForgeFacade` with explicit forge-aware mutations. Continuity `upsert_progress` stays Hub-only (B2a). Scheduler adds `forge_repo_reconcile` reusing Sync-now inbound shape from B2a.

**Tech Stack:** Same as B2a (Python, SQLite, httpx, pytest).

**Spec:** `docs/superpowers/specs/2026-09-12-repo-primary-issue-sync-design.md` (B2b sections)

**Depends on:** B2a inbound authority on branch `feat/foundation-b2-repo-primary-sync`

## Global Constraints

- B1 + B2a unchanged; no last-write-wins.
- External `mark_done`: close remote **first** → `external_issue_state` → Hub `done` only after success.
- Failed remote leave local projection unchanged; fail loud.
- Promote/link: no private history dump; no status block unless `publish_hub_status_block`.
- Needs review: minimal persistence only (#75 owns live UI/history).
- Do not commit unless operator asks.

## File map

| File | Responsibility |
|------|----------------|
| `src/adhd_hub/forge/repo_sync.py` | `close_remote_issue`, `reopen_remote_issue`, promote helpers |
| `src/adhd_hub/forge/facade.py` | Wire mutations; promote/link; Needs review records |
| `src/adhd_hub/service.py` / `mcp_app.py` / `api.py` | Explicit mark_done path for external; promote endpoints |
| `src/adhd_hub/scheduler.py` | `forge_repo_reconcile` job + overlap lock + backoff |
| `src/adhd_hub/store.py` | Minimal sync_review / pending_actions reuse |
| `tests/test_repo_sync_b2b.py` | Focused suite |

---

### Task 1: Remote-first mark_done / reopen

**Files:** `repo_sync.py`, `service.py`, `tests/test_repo_sync_b2b.py`

- [ ] External `mark_done`: PATCH remote closed using pinned identity + safe credentials; on success apply projection then Hub `done`; on failure raise/return error without Hub done.
- [ ] Hub-authority `mark_done`: Hub-only (no forge), as today after B2a.
- [ ] Explicit `reopen_external_issue(thread_id)`: remote open first, then projection + Hub open.
- [ ] Tests: success path; failed PATCH leaves Hub open and `external_issue_state` unchanged.

### Task 2: Promote / link

- [ ] `link_external_issue(thread_id, owner, repo, number)` and `promote_create_issue(thread_id)` on project forge target.
- [ ] Atomic attach; collision → Needs review / error.
- [ ] Create issue title from summary; body empty/minimal (no status block default).
- [ ] Tests: link, create, no private history in body, collision.

### Task 3: Minimal Needs review

- [ ] Persist kind/reason/project/identity/thread_ids/message via `pending_actions` or meta list.
- [ ] Surface on Sync now / list API lightly.
- [ ] Tests: multi-project disambiguation records review item.

### Task 4: Scheduler + Sync now polish

- [ ] Job `forge_repo_reconcile` cron setting; skip if lock held; backoff on 429/5xx.
- [ ] Sync now already reconciles pinned + discovers (B2a); ensure scheduler calls same entrypoint.
- [ ] Tests: overlap lock skips second run.

### Task 5: Verify + close #74

- [ ] `uv run pytest tests/test_repo_sync_b2a.py tests/test_repo_sync_b2b.py tests/test_work_identity.py`
- [ ] Full pytest/ruff vs main baseline
- [ ] PR notes: B2b completes #74; document transitional gap closed by remote-first mark_done

## Spec coverage

| Item | Task |
|------|------|
| Remote-first mark_done/reopen | 1 |
| Promote/link | 2 |
| Needs review minimal | 3 |
| Scheduler lock/backoff | 4 |
| Close #74 when both land | 5 |
