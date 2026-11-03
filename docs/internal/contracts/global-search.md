# Global search — implementation contract

Public guide: [global-search.md](../../public/global-search.md). Spec:
[2026-11-03-global-search-design.md](../superpowers/specs/2026-11-03-global-search-design.md).

## Surface

- Module: `adhd_hub.search`
- Service: `HubService.search_work(query, *, limit=None, include_done=False)`
- REST: `GET /api/search`
- MCP: `search_work` (readOnly, idempotent, not open-world)

## Invariants

1. Queries shorter than 2 characters after normalize return `{query, hits: []}`.
2. Default thread set is open + blocked only; done/dismissed require `include_done`.
3. Merged source threads (`merged_into` set) are never returned.
4. Snippets pass through `scrub_scan_text`; empty after scrub → `snippet: null`.
5. Wiki reads are capped at 200_000 characters per file; no external index.
6. Hit limit hard-capped at 50.

## Ranking (advisory)

Exact title/slug > prefix > substring. Open/blocked threads get a small status
boost over done when mixed. Ties break by newer `updated_at`, then kind, then
title. Scores are not a productivity metric and must not gate actions.

## Tests

`tests/test_global_search.py` covers goal match, project tags, wiki body,
done exclusion, ranking, REST auth, and MCP `search_work`.
`tests/test_mcp_metadata.py` includes `search_work` in the public catalog.
