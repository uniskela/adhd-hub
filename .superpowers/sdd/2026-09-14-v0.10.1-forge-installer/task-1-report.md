# Task 1 report: Stop redundant forge commits

## Status

Complete.

## Files changed

- `src/adhd_hub/forge/wiki_sync.py`
- `src/adhd_hub/forge/scaffold.py`
- `src/adhd_hub/wiki.py`
- `src/adhd_hub/service.py`
- `tests/test_forge_idempotency.py`
- `tests/test_wiki_batch_commit.py`

## Behavior

- Individual Contents API writes now compare remote UTF-8 content before PUT. When inline content is unavailable, supported 40-character SHA-1 and 64-character SHA-256 Git blob IDs are compared. Missing files are created; malformed, unsupported, or unreadable remote state raises instead of writing blindly.
- Unchanged individual files return `{skipped: true, reason: "unchanged", path: ...}`.
- Batch change-detection errors now switch to sequential per-file reads and writes. Batch commit failures also recheck each changed file before a Contents API write.
- Wiki, scaffold, move, and rename aggregates count only actual uploads, expose `unchanged_files`, and report `unchanged: true` only when there were no writes or errors. A rename that only deletes the old path is correctly treated as a write.
- `INDEX.md` keeps its existing timestamp and exact bytes when regeneration changes only the generated timestamp line.
- Tests cover GitHub and Gitea unchanged/changed/missing files, blob-SHA comparison, indeterminate/read failures, scaffold idempotency and URL changes, both batch fallback paths, rename/move accounting, and timestamp stability.

## Verification

- `rtk uv --cache-dir /tmp/uv-cache-v0101 run pytest -q tests/test_forge_idempotency.py tests/test_wiki_batch_commit.py tests/test_forge.py tests/test_forge_wiki_paths.py tests/test_wiki_forge_target.py tests/test_projects.py` — **39 passed in 2.99s**.
- `rtk uv --cache-dir /tmp/uv-cache-v0101 run ruff check src/adhd_hub/forge/wiki_sync.py src/adhd_hub/forge/scaffold.py src/adhd_hub/wiki.py src/adhd_hub/service.py tests/test_forge_idempotency.py tests/test_wiki_batch_commit.py` — **All checks passed**.
- `rtk git diff --check` — **passed with no output**.

## Commit

- `e5d8f35` (`fix: stop redundant forge file commits`)

## Concerns

- `uv.lock` was already modified before this task and was deliberately left unstaged and untouched.
- Graphify could not orient because `graphify-out/graph.json` is absent. Per the task brief, no graph generation or refresh was performed; final integration owns that step.

## Round 1 fixes

- Same-slug/title-only renames now skip remote move/delete operations.
- Rename responses merge wiki sync uploads, unchanged files, and errors before computing `forge.unchanged`.
- Added rename tests for title-only same-slug behavior and upload/error aggregation.

Verification after fixes:

- `rtk uv --cache-dir /tmp/uv-cache-v0101 run pytest -q tests/test_forge_idempotency.py tests/test_wiki_batch_commit.py tests/test_forge.py tests/test_forge_wiki_paths.py tests/test_wiki_forge_target.py tests/test_projects.py` — **41 passed in 4.17s**.
- `rtk uv --cache-dir /tmp/uv-cache-v0101 run ruff check src/adhd_hub/service.py tests/test_forge_idempotency.py` — initially found one import-order issue; `ruff check --fix` corrected it, and the rerun reported **All checks passed**.
