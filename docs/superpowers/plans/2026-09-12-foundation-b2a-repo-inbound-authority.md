# Foundation B2a — inbound authority & stop Hub-primary mirroring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce repo-primary inbound authority for #74 B2a: stop Hub-status→remote-state and default continuity publication, add safe import policy + scoped discover/reconcile with a small local projection, and refuse continuity API attempts to mutate repo-owned fields with clear errors.

**Architecture:** Add `RepoWorkSync` for discover/fingerprint/apply on top of B1 identity. Shrink `BoardForgeSync.sync_thread` so external-authority and default paths no longer mirror Hub status or write status blocks. Enforce write boundaries in `HubService`/`Store` continuity paths. Leave explicit remote-first `mark_done` / promote / scheduler to **B2b**.

**Tech Stack:** Python 3.12+, SQLite via `Store`, `httpx` forge clients, Pydantic `ForgeConfig`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-12-repo-primary-issue-sync-design.md` (B2a sections)

**Parent:** [#74](https://github.com/uniskela/adhd-hub/issues/74) · Umbrella [#71](https://github.com/uniskela/adhd-hub/issues/71) · Depends on B1 [#73](https://github.com/uniskela/adhd-hub/issues/73) / PR #76

## Global Constraints

- B1 identity/authority model is fixed (`work_identity.py`); do not redesign unless a concrete blocker.
- `Thread.status` = Hub continuity; `external_issue_state` = remote task state; no last-write-wins.
- External authority: **no** Hub continuity PATCH by default.
- External + `publish_hub_status_block=true`: **status-block body merge only** — never Hub-driven remote state/title/labels.
- Legacy mirror path: `authority=hub` + `board_mirror_local=true` only; prefer **preserve existing** mirrors, **do not create new** Hub-primary mirrors that pin-on-link into external. Do not weaken B1 pin-on-link.
- Continuity APIs must **error clearly** on attempted repo-owned field mutation — never silently ignore.
- `upsert_progress` / normal continuity never mutate remote open/closed.
- B2a `mark_done` becomes Hub-local only (no remote close) — **intentional transitional gap** until B2b remote-first `mark_done`.
- **Do not cut a user-facing release between B2a and B2b** unless that transitional gap is intentionally documented in the PR/release notes.
- Import default for new/unconfigured: `manual` (never `all_open`). Migrated inbox installs → `adhd_inbox`.
- **Linked reconcile uses pinned identity** `(provider, host, owner, repo, number)`; not gated on project forge target. Project forge target is for **discovery/new association** only. Unreachable pinned identity → structured skip/error; never substitute another repo.
- **Sync now:** (1) wiki/scaffold (2) reconcile all linked threads by pinned identity (3) credentials must match pinned provider/host (4) separately discover via resolvable project forge + policy (5) no new Hub mirrors.
- **Atomic import:** `Store.get_or_create_thread_for_external_identity` (transactional); no orphan thread on attach race/collision.
- **`assigned_to_me`:** username from explicit `forge_account_login` (or equivalent) else authenticated `/user` lookup/cache — **not** inbox authors. Unavailable → clear failure.
- **Exclude PRs** from GitHub issue lists (`pull_request` key present); test coverage required.
- Fingerprint: normalized fields + **NFC** title; include NFC equivalence test.
- Projection stays small: identity, title→summary, state, labels-as-needed, `external_updated_at`, normalized fingerprint.
- Needs review / promote / outbound close / scheduler cron = **B2b** (B2a may return structured skip/conflict dicts without persisting Needs review).
- No secrets, private Hub URLs, or absolute machine paths in public PR text.
- Do not commit unless the operator explicitly asks.
- After meaningful code edits: `graphify update .` (use `%USERPROFILE%\.local\bin\graphify.exe` if PATH missing).

## File map

| File | Responsibility |
|------|----------------|
| `src/adhd_hub/forge/config.py` | Import-policy + mirror/status-block/close flags + `forge_account_login` |
| `src/adhd_hub/forge/repo_sync.py` (new) | Snapshot, fingerprint (NFC), discover (no PRs), pinned reconcile fetch |
| `src/adhd_hub/forge/board_sync.py` | External/default skip; status-block-only opt-in; isolated legacy mirror |
| `src/adhd_hub/forge/facade.py` | Wire discover/import defaults; stop blind mirror; Sync now inbound |
| `src/adhd_hub/work_identity.py` | Error helper / ownership constants if needed |
| `src/adhd_hub/store.py` | Revision columns; apply projection; **atomic** get-or-create-by-identity |
| `src/adhd_hub/models.py` | Thread fields for revision; serializers if needed |
| `src/adhd_hub/service.py` | Continuity write-boundary errors; transitional mark_done forge behaviour |
| `src/adhd_hub/api.py` | Map domain errors; import `close_imported` default false |
| `tests/test_repo_sync_b2a.py` (new) | B2a focused suite |
| `tests/test_work_identity.py` | Keep green; extend only if shared helpers change |
| Spec (already written) | Design source of truth |

**Out of B2a:** remote-first mark_done/reopen, promote/link, scheduler job, persisted Needs review (#75 UI).

## Transitional behaviour (document in PR body)

After B2a merges and before B2b:

1. Continuity upserts do not close/reopen remotes.
2. `mark_done` / `dismiss` update Hub only; remotes stay as-is.
3. Inbound reconcile can update `external_issue_state` + title projection.
4. Explicit remote close returns in B2b.

Do not tag/publish a standalone B2a release without stating (1)–(4).

---

### Task 1: Config flags + revision schema

**Files:**
- Modify: `src/adhd_hub/forge/config.py`
- Modify: `src/adhd_hub/models.py` (`Thread` additive fields)
- Modify: `src/adhd_hub/store.py` (migrate columns)
- Test: `tests/test_repo_sync_b2a.py`

**Interfaces:**
- Produces: `ForgeConfig` fields below; `Thread.external_updated_at: str | None`; `Thread.external_fingerprint: str | None`

Add to `ForgeConfig`:

```python
class IssueImportPolicy(StrEnum):
    manual = "manual"
    all_open = "all_open"
    labels = "labels"
    assigned_to_me = "assigned_to_me"
    adhd_inbox = "adhd_inbox"

# on ForgeConfig:
issue_import_policy: IssueImportPolicy = IssueImportPolicy.manual
issue_import_labels: list[str] = Field(default_factory=list)
forge_account_login: str = ""  # explicit login for assigned_to_me; else /user lookup
board_mirror_local: bool = False
board_inbox_close_imported: bool = False
publish_hub_status_block: bool = False
```

Migration helper (call from load or one-shot meta flag): if existing `forge.json` has `board_inbox_enabled=true` and policy unset/manual default would wipe inbox behaviour, set `issue_import_policy=adhd_inbox` once when migrating old configs that lack the new key.

- [ ] **Step 1: Write failing tests**

```python
def test_forge_config_defaults_are_safe() -> None:
    cfg = ForgeConfig()
    assert cfg.issue_import_policy == IssueImportPolicy.manual
    assert cfg.board_inbox_close_imported is False
    assert cfg.board_mirror_local is False
    assert cfg.publish_hub_status_block is False


def test_thread_revision_columns_round_trip(tmp_path: Path) -> None:
    store = Store(tmp_path / "hub.sqlite3")
    # create local thread then set revision fields via store helper added in Task 3,
    # or assert migrate adds columns without error:
    store._ensure_schema()  # use public migrate path the project already uses
    cols = {row[1] for row in store._conn.execute("PRAGMA table_info(threads)").fetchall()}
    assert "external_updated_at" in cols
    assert "external_fingerprint" in cols
```

Adjust private accessors to match Store’s real API (prefer existing migrate entry used by HubService init).

- [ ] **Step 2: Run — expect FAIL**

`uv run pytest tests/test_repo_sync_b2a.py::test_forge_config_defaults_are_safe tests/test_repo_sync_b2a.py::test_thread_revision_columns_round_trip -v`

- [ ] **Step 3: Implement config + schema**

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit only if operator asked**

---

### Task 2: Fingerprint + minimal snapshot helpers

**Files:**
- Create: `src/adhd_hub/forge/repo_sync.py`
- Test: `tests/test_repo_sync_b2a.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True, slots=True)
class IssueSnapshot:
    identity: ExternalIdentity
    title: str
    state: ExternalIssueState  # open|closed
    labels: tuple[str, ...]  # normalized lower sorted unique
    updated_at: str  # provider timestamp, normalized ISO or raw stable string
    assignee_logins: tuple[str, ...] = ()  # transient; not required in fingerprint

def normalize_labels(labels: Iterable[str]) -> tuple[str, ...]: ...
def fingerprint_for(snapshot: IssueSnapshot) -> str: ...
# sha256 hex of canonical lines:
# provider, host, owner, repo, number, state, unicodedata.normalize("NFC", title.strip()), labels joined
```

Do **not** include body/comments/milestone/raw JSON. `updated_at` is stored separately and must not affect the fingerprint.

- [ ] **Step 1: Failing tests**

```python
def test_fingerprint_stable_under_label_order_and_casing() -> None:
    a = IssueSnapshot(
        identity=normalize_external_identity(WorkSource.github, "github.com", "Acme", "App", 9),
        title=" Fix me ",
        state=ExternalIssueState.open,
        labels=("Bug", "help wanted"),
        updated_at="2026-09-12T00:00:00Z",
    )
    b = IssueSnapshot(
        identity=normalize_external_identity(WorkSource.github, "github.com", "acme", "app", 9),
        title=" Fix me ",
        state=ExternalIssueState.open,
        labels=("help wanted", "BUG"),
        updated_at="2026-09-12T99:99:99Z",  # updated_at must NOT affect fingerprint
    )
    assert fingerprint_for(a) == fingerprint_for(b)


def test_fingerprint_nfc_title_normalization() -> None:
    # U+00E9 (é) vs e + U+0301 combining acute → same fingerprint
    composed = "caf\u00e9"
    decomposed = "cafe\u0301"
    a = IssueSnapshot(
        identity=normalize_external_identity(WorkSource.github, "github.com", "o", "r", 1),
        title=composed,
        state=ExternalIssueState.open,
        labels=(),
        updated_at="t1",
    )
    b = IssueSnapshot(
        identity=normalize_external_identity(WorkSource.github, "github.com", "o", "r", 1),
        title=decomposed,
        state=ExternalIssueState.open,
        labels=(),
        updated_at="t2",
    )
    assert fingerprint_for(a) == fingerprint_for(b)


def test_fingerprint_changes_when_state_changes() -> None:
    ...
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement helpers in `repo_sync.py`** (use `unicodedata.normalize("NFC", ...)`)

- [ ] **Step 4: Run — expect PASS**

---

### Task 3: Apply projection + pinned-identity reconcile fetch

**Files:**
- Modify: `src/adhd_hub/forge/repo_sync.py`
- Modify: `src/adhd_hub/store.py` (`apply_external_projection` or equivalent)
- Test: `tests/test_repo_sync_b2a.py`

**Interfaces:**
- Produces:

```python
def apply_external_projection(store: Store, thread_id: str, snapshot: IssueSnapshot) -> dict:
    """Update summary, external_issue_state, labels-if-stored, revision fields.
    Never touch focus/next/blocked/resume/status/progress notes.
    No-op when fingerprint matches. Returns {applied: bool, ...}.
    """

def fetch_pinned_issue(client, cfg_for_credentials: ForgeConfig, identity: ExternalIdentity) -> IssueSnapshot | dict:
    """GET owner/repo/number from pinned identity. On 404/auth/host mismatch:
    return {skipped: True, reason: 'pinned_identity_unreachable', ...}.
    Never fetch a different owner/repo from project config as a substitute.
    """
```

- [ ] **Step 1: Failing tests**

```python
def test_apply_projection_updates_state_not_hub_status(tmp_path: Path) -> None:
    svc = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    # create project + attach external identity via store.attach_external_identity
    # set focus/next on thread; Hub status open
    # apply snapshot with closed + new title
    # assert external_issue_state closed, summary==title, status still open
    # assert focus/next unchanged
    # second apply same fingerprint → applied False


def test_split_state_open_hub_closed_external_is_ok(tmp_path: Path) -> None:
    # after apply closed remote, Thread.status remains open — not an error
    ...


def test_reconcile_uses_pinned_identity_not_project_forge_repo(monkeypatch, tmp_path):
    # thread pinned to ownerA/repoA#7; project forge points at ownerB/repoB
    # assert HTTP GET path uses ownerA/repoA/issues/7 only
    ...


def test_pinned_identity_unreachable_returns_skip(monkeypatch, tmp_path):
    ...
```

- [ ] **Step 2–4: TDD implement + pass**

---

### Task 3b: Atomic `get_or_create_thread_for_external_identity`

**Files:**
- Modify: `src/adhd_hub/store.py`
- Test: `tests/test_repo_sync_b2a.py`

```python
def get_or_create_thread_for_external_identity(
    self,
    *,
    identity: ExternalIdentity,
    project_slug: str,
    summary: str,
    external_issue_state: ExternalIssueState | None = None,
) -> tuple[Thread, bool]:
    """Single transaction: lookup by identity; if missing create thread + attach.
    On unique collision, return existing thread (created=False). Never leave orphan.
    """
```

- [ ] **Step 1: Failing tests** — concurrent-style double create (sequential attach race simulation) leaves one thread; no orphan without identity

- [ ] **Step 2–4: TDD implement + pass**

---

### Task 4: Write-boundary enforcement (loud errors)

**Files:**
- Modify: `src/adhd_hub/work_identity.py` (error type/message helper)
- Modify: `src/adhd_hub/service.py` (`upsert_progress`, `upsert_thread` / store thread write paths)
- Modify: `src/adhd_hub/api.py` / `mcp_app.py` if needed so `ValueError` surfaces (already 400)
- Test: `tests/test_repo_sync_b2a.py`

**Interfaces:**
- Produces:

```python
class RepoOwnedFieldMutationError(ValueError):
    """continuity API attempted to change a repo-owned field on external-authority work"""

REPO_OWNED_CONTINUITY_MUTATION = (
    "repo_owned_field_forbidden: use an explicit forge-aware operation "
    "(B2b mark_done/reopen/promote) to change remote-owned fields"
)
```

Rules for `authority=external`:

- `upsert_progress`: if `payload.title` is set and would change `thread.summary` → raise `RepoOwnedFieldMutationError`
- Reject any path that sets `external_issue_state`, identity columns, or projected labels via continuity/generic upsert
- Allowed: goal/focus/next/blocked/resume/content/history; Hub status transitions that are continuity-only remain local
- **Do not** strip/ignore forbidden fields silently

- [ ] **Step 1: Failing tests**

```python
def test_upsert_progress_rejects_title_change_on_external(tmp_path: Path) -> None:
    ...
    with pytest.raises(ValueError, match="repo_owned_field_forbidden"):
        svc.upsert_progress(ProgressUpsert(
            project_slug=slug,
            thread_id=thread.id,
            title="Hacked remote title",
            focus="ok focus",
        ))


def test_upsert_progress_allows_focus_on_external(tmp_path: Path) -> None:
    ...
    out = svc.upsert_progress(ProgressUpsert(
        project_slug=slug,
        thread_id=thread.id,
        focus="new focus only",
    ))
    assert out["thread"]["focus"] == "new focus only"
```

- [ ] **Step 2–4: TDD implement + pass**

---

### Task 5: Disable Hub-primary mirroring + status-block control flow

**Files:**
- Modify: `src/adhd_hub/forge/board_sync.py` (`sync_thread`, `_create_issue`, `_update_issue`, body helpers)
- Modify: `src/adhd_hub/forge/facade.py` (`_forge_after_thread`, `sync_forge_now`)
- Modify: `src/adhd_hub/service.py` (`mark_done` / `mark_dismissed` forge side effects)
- Test: `tests/test_repo_sync_b2a.py` (httpx mock / monkeypatch)

**Control flow (locked):**

| Case | Behaviour |
| --- | --- |
| `authority=external` default | Skip entirely — no continuity PATCH |
| `authority=external` + `publish_hub_status_block=true` | PATCH **body status-block merge only**; never `state` / title / labels from Hub |
| `authority=hub` + `board_mirror_local=false` | Skip create/update (default) |
| `authority=hub` + `board_mirror_local=true` | Legacy path **isolated**: may update **existing** hub-owned mirrors; **do not create new** mirrors on progress (preserve-only). Never weaken B1: once identity attaches, authority becomes external and this path stops |

- Remove `state` derived from `Thread.status` on external and default paths.
- `_forge_after_thread`: no auto-create of new mirrors; wiki refresh may remain.
- Transitional: `mark_done` / `dismiss` must not close remotes.

- [ ] **Step 1: Failing tests with mocked client**

```python
def test_sync_thread_skips_external_and_does_not_patch(monkeypatch, tmp_path):
    ...


def test_external_publish_status_block_only_no_state_title_labels(monkeypatch, tmp_path):
    # publish_hub_status_block=True; capture PATCH JSON
    # assert "state" not in payload and "title" not in payload and "labels" not in payload
    # assert body contains status markers
    ...


def test_board_mirror_local_does_not_create_new_issues(monkeypatch, tmp_path):
    # authority=hub, board_mirror_local=True, no existing forge number → skipped, no POST
    ...


def test_mark_done_does_not_close_remote_after_b2a(monkeypatch, tmp_path):
    ...
```

- [ ] **Step 2–4: TDD implement + pass**

---

### Task 6: Import policy + scoped discover (no close, no PRs, assigned_to_me)

**Files:**
- Modify: `src/adhd_hub/forge/repo_sync.py` (`discover_issues`, `resolve_assigned_to_me_login`)
- Modify: `src/adhd_hub/forge/facade.py` (`import_forge_inbox` / new `import_repo_issues`)
- Modify: `src/adhd_hub/api.py` (default `close_imported=False`)
- Test: `tests/test_repo_sync_b2a.py`

**Behaviour:**

- Resolve forge target per project for **discovery only**.
- `manual` → discover returns empty / skip import.
- `adhd_inbox` → existing hub-label / `[ADHD]` title filter (compatibility).
- `all_open` / `labels` / `assigned_to_me` → list issues for that owner/repo only.
- **Exclude** items with GitHub `pull_request` key (and Gitea PR equivalents).
- `assigned_to_me`: use `forge_account_login` if set; else `GET /user` (cache); **never** inbox authors; if unavailable → `{error: "assigned_to_me_login_unavailable"}`.
- Import via `get_or_create_thread_for_external_identity` (atomic).
- Multi-project ambiguity: skip with `needs_project_disambiguation` (Needs review in B2b).
- Default `close_imported=False`; do not close unless explicit opt-in.

- [ ] **Step 1: Failing tests**

```python
def test_manual_policy_imports_nothing(tmp_path):
    ...


def test_import_does_not_close_by_default(monkeypatch, tmp_path):
    ...


def test_github_pull_requests_excluded_from_discover():
    # raw list with one issue and one PR (pull_request: {}) → only issue becomes snapshot
    ...


def test_assigned_to_me_does_not_use_inbox_authors(tmp_path):
    cfg = ForgeConfig(issue_import_policy=IssueImportPolicy.assigned_to_me, board_inbox_authors=["alice"])
    # no forge_account_login, mock /user failure → assigned_to_me_login_unavailable
    ...


def test_get_or_create_atomic_no_orphan_on_collision(tmp_path):
    ...


def test_migrated_inbox_config_keeps_adhd_inbox_policy(tmp_path):
    ...
```

- [ ] **Step 2–4: TDD implement + pass**

---

### Task 7: Sync now inbound reconcile path (no scheduler)

**Files:**
- Modify: `src/adhd_hub/forge/facade.py` (`sync_forge_now`)
- Test: `tests/test_repo_sync_b2a.py`

Replace “push all open threads via `sync_thread`” with:

1. Wiki/scaffold unchanged.
2. Enumerate **already-linked** external threads and reconcile each from its **stored pinned identity** `(provider, host, owner, repo, number)` — **not** gated on whether the project’s current forge target resolves.
3. Use available credentials only if they safely apply to that pinned provider/host. If not, return `pinned_identity_unreachable`; **never** substitute the project’s current repo.
4. **Separately**, for projects with a resolvable forge target, run **new issue discovery** according to their import policy (still no close-on-import by default).
5. Do **not** create new local Hub mirrors; `board_mirror_local` remains preserve-existing-only compatibility behaviour.

No cron job in B2a (B2b).

- [ ] **Step 1: Failing tests**

```python
def test_sync_now_reconciles_linked_thread_when_project_forge_repo_differs(monkeypatch, tmp_path):
    # pinned identity ownerA/repoA#3; project forge points at ownerB/repoB
    # assert fetch uses A/A#3; discovery (if any) uses B/B separately
    ...


def test_sync_now_pinned_unreachable_without_matching_credentials(monkeypatch, tmp_path):
    ...
```

- [ ] **Step 2–4: TDD implement + pass**

---

### Task 8: Verification + PR notes

**Files:**
- Docs: PR body only (no extra markdown unless operator asks)
- Optional one-line pointer in `docs/plans/thread-outcome-model.md` if that file already tracks Foundation B

- [ ] **Step 1: Focused suite**

`uv run pytest tests/test_repo_sync_b2a.py tests/test_work_identity.py -v`

- [ ] **Step 2: Full checks vs main baseline**

`uv run pytest`  
`uv run ruff check src tests`  
Compare known env failures on Windows to `origin/main` (do not “fix” unrelated baseline noise).

- [ ] **Step 3: `graphify update .`**

- [ ] **Step 4: Open B2a PR against main**

PR must state:

- Implements inbound half of #74 (B2a); **does not close #74**.
- Transitional: `mark_done` no longer closes remotes until B2b.
- Not a release cut between B2a and B2b without documenting that gap.
- Link design spec + this plan.

- [ ] **Step 5: Commit/push only if operator asked; run `/review-bugbot` before push per user rules**

---

## Spec coverage checklist (B2a only)

| Spec item | Task |
|-----------|------|
| No default continuity PATCH on external | 5 |
| Status-block-only when publish opt-in | 5 |
| Preserve-only legacy mirror; no new Hub mirrors | 5 |
| Small projection + NFC fingerprint | 2–3 |
| Pinned-identity reconcile; no repo substitute | 3 |
| Atomic get-or-create import | 3b, 6 |
| Loud write-boundary errors | 4 |
| Split state display OK | 3 |
| Import default `manual` / migrated `adhd_inbox` | 1, 6 |
| Exclude PRs; assigned_to_me login rules | 6 |
| Stop Hub-status→remote state | 5 |
| Transitional mark_done; no release between slices | Constraints + Task 8 |
| Continuity never mutates remote open/closed | 4–5 |
| B2b outbound deferred | Explicit out-of-scope |

## Self-review

- No B2b scheduler/promote/Needs-review persistence in tasks.
- Clear error (not silent ignore) for forbidden continuity mutations.
- Transitional gap documented for release policy and `mark_done`.
- Pinned reconcile, atomic import, PR exclusion, assigned_to_me, status-block control flow, board_mirror_local vs B1, NFC test all covered.
