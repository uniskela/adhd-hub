# Global search Implementation Plan

> **For agentic workers:** Execute task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship local-first global search (threads + projects + wiki snippets) for v0.22.0 Wave 8 first slice.

**Architecture:** New `search.py` ranks hits; `HubService.search_work` orchestrates store + wiki; REST `GET /api/search` and MCP `search_work`; My work search calls the API.

**Tech Stack:** Python 3.12, FastAPI, SQLite via existing `Store`, vanilla dashboard JS.

## Global Constraints

- No FTS5 / new dependencies this release.
- Auth required; read-only.
- Snippets via `scrub_scan_text`.
- Compaction / capture / energy modes out of scope.

---

### Task 1: Core search module + service

**Files:**
- Create: `src/adhd_hub/search.py`
- Modify: `src/adhd_hub/service.py` (add `search_work`)
- Test: `tests/test_global_search.py`

**Interfaces:**
- Produces: `search_work(query: str, *, limit: int = 25, include_done: bool = False) -> dict`

- [x] **Step 1: Failing tests for ranking and sources**

```python
def test_search_finds_thread_by_goal(service):
    service.upsert_progress(...)  # goal contains unique token
    out = service.search_work("unique-token-xyz")
    assert any(h["kind"] == "thread" and "unique-token-xyz" in (h["snippet"] or "").lower() or "unique-token-xyz" in h["title"].lower() for h in out["hits"])

def test_search_finds_project_and_wiki(service):
    # create project, write progress markdown containing token
    ...

def test_search_min_query_and_excludes_done_by_default(service):
    assert service.search_work("x")["hits"] == []  # too short
    ...
```

- [x] **Step 2: Implement `search.py` + `HubService.search_work`**
  - Normalize query (casefold, strip)
  - Scan threads via store list (open/paused; optional done) matching fields
  - Scan projects title/slug/tags
  - For each project slug with wiki progress, find first match window ≤160 chars
  - Sort by score, truncate to limit
  - Return `{query, hits}`

- [x] **Step 3: `uv run pytest tests/test_global_search.py -v` passes**

---

### Task 2: REST + MCP

**Files:**
- Modify: `src/adhd_hub/api.py`, `src/adhd_hub/mcp_app.py`
- Extend: `tests/test_global_search.py`

- [x] **Step 1: `GET /api/search?q=&limit=&include_done=`** (auth, same validation as overlap)
- [x] **Step 2: MCP `search_work`** with ToolAnnotations readOnly/idempotent; describe params
- [x] **Step 3: REST + MCP tests with TestClient**

---

### Task 3: Dashboard UI

**Files:**
- Modify: `src/adhd_hub/ui/app.js`, `src/adhd_hub/ui/index.html` (hint copy if needed), `src/adhd_hub/ui/app.css` (minimal)

- [x] Debounced API search when `#thread-search` length ≥ 2
- [x] Render mixed hits; empty query → existing `renderThreads(threadsCache)`
- [x] Click handlers: thread → open; project → `selectProject`; wiki → notes/progress for slug

---

### Task 4: Docs + roadmap stamp

**Files:**
- Create: `docs/public/global-search.md`, `docs/internal/contracts/global-search.md`
- Modify: `docs/manifest.json`, `zensical.toml`, `docs/public/plans/improvement-roadmap.md`, `docs/public/dashboard.md` (short link)
- Tests: `tests/test_documentation.py` if nav asserts need updating

- [x] Document REST/MCP table (merge-dedupe style)
- [x] Roadmap: Now = Wave 8; published v0.21.1; Wave 7 shipped

---

### Task 5: Verify

- [x] `uv run pytest`
- [x] `uv run ruff check src tests`
- [x] `graphify update .` if CLI works / graph exists
