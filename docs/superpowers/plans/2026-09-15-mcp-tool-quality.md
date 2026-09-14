# MCP Tool Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve agent-facing MCP tool definitions and prove representative tools execute correctly over the stdio transport used by local clients and Glama.

**Architecture:** Keep the existing `build_mcp(service)` catalog as the single source of truth. Strengthen only its tool descriptions and tests; the stdio CLI continues to reuse the same catalog. Integration coverage launches the actual CLI subprocess through the MCP Python client so the test exercises initialization, instructions, discovery, and tool execution end to end.

**Tech Stack:** Python 3.12, MCP Python SDK, pytest/pytest-asyncio, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-15-mcp-tool-quality-design.md`

## Global Constraints

- No tool names, arguments, return schemas, persistence semantics, or authentication behavior change.
- Keep descriptions concise and agent-oriented rather than Glama-specific.
- `adhd-hub serve` remains the persistent/shared path; `adhd-hub mcp-stdio` remains optional local/proxy transport.
- No production workaround for upstream proxy metadata loss.

---

### Task 1: Lock in agent-actionable descriptions

**Files:**
- Modify: `tests/test_mcp.py`
- Modify: `src/adhd_hub/mcp_app.py`

**Interfaces:**
- Consumes: MCP `tools/list` output from the existing HTTP test harness.
- Produces: richer MCP `description` strings only; schemas and behavior remain unchanged.

- [ ] **Step 1: Write the failing test**

Add assertions to the existing discovery test that the most ambiguous write tools include short disambiguation guidance. At minimum assert:

```python
assert "pause_thread" in tools["mark_done"]["description"]
assert "mark_done" in tools["pause_thread"]["description"]
assert "upsert_progress" in tools["upsert_thread"]["description"]
assert "thread_id" in tools["upsert_progress"]["description"]
assert "session" in tools["resolve_project"]["description"].lower()
assert "side effect" in tools["register_workspace"]["description"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_mcp.py::test_mcp_discovery_validation_and_progress`
Expected: FAIL because the current terse descriptions do not contain the new guidance.

- [ ] **Step 3: Write minimal implementation**

Expand the relevant tool docstrings in `build_mcp()` so agents can distinguish neighboring operations. Keep each description to a short paragraph or two. Cover the C-rated tools first (`resolve_project`, `upsert_project`, `upsert_thread`, `upsert_progress`, `mark_done`, `pause_thread`, `register_workspace`, `set_reminder`, `list_open_threads`, `push_openclaw_memory`) and lightly normalize related descriptions where doing so prevents ambiguity.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_mcp.py::test_mcp_discovery_validation_and_progress`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/adhd_hub/mcp_app.py tests/test_mcp.py
git commit -m "docs(mcp): improve agent-facing tool guidance"
```

### Task 2: Exercise stdio initialization and tool calls

**Files:**
- Modify: `tests/test_mcp_stdio.py`

**Interfaces:**
- Consumes: CLI command `python -m adhd_hub.cli mcp-stdio` and MCP `ClientSession`.
- Produces: regression coverage only; no runtime code changes.

- [ ] **Step 1: Extend the integration test**

Capture the initialize result, assert the server publishes its Hub instructions, then call representative read tools through the real stdio session:

```python
initialized = await session.initialize()
assert initialized.instructions
assert "resolve_project" in initialized.instructions

overlap = await session.call_tool("check_overlap", {"query": "test"})
reminders = await session.call_tool("list_reminders", {"due_only": True})
overview = await session.call_tool("get_overview", {})
assert overlap.isError is not True
assert reminders.isError is not True
assert overview.isError is not True
```

Use the SDK's actual result attribute spelling/types as present in the pinned dependency.

- [ ] **Step 2: Run the focused stdio test**

Run: `uv run pytest -q tests/test_mcp_stdio.py`
Expected: PASS; this is regression coverage for behavior that should already work.

- [ ] **Step 3: Commit**

```bash
git add tests/test_mcp_stdio.py
git commit -m "test(mcp): exercise stdio tool calls"
```

### Task 3: Full verification

**Files:**
- No production changes expected.

**Interfaces:**
- Consumes: complete branch state.
- Produces: review-ready evidence.

- [ ] **Step 1: Run the full suite**

Run: `uv run pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Run lint**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 3: Check whitespace**

Run: `git diff --check`
Expected: no output.
