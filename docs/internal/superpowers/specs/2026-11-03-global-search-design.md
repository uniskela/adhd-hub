# Global search (v0.22.0 / Wave 8 first slice) — design

Parent: [#55](https://github.com/uniskela/adhd-hub/issues/55) · Tracker: [#15](https://github.com/uniskela/adhd-hub/issues/15) · Continuity: [#337](https://github.com/uniskela/adhd-hub/issues/337)

## Goal

Ship **local-first global search** so a person (and agents) can find threads, projects, and wiki progress snippets without an external index. This is the only Wave 8 slice in **v0.22.0**.

## Non-goals

- Progress wiki compaction, mobile/share capture, energy/context modes
- FTS5 / embeddings / external search services
- Expanding client-only filter on the loaded 100-thread page as the product answer

## Current gap

My work `#thread-search` filters the latest loaded threads in the browser (`summary` / `scan_line` / slug / snippet). It misses unloaded threads, goal/focus/resume/next, projects, and wiki markdown.

## Approach

**Server-side multi-source `LIKE` / substring scan** (approved). No new dependencies. Add FTS later only if search is measurably slow on real Hub data sizes.

## Behaviour

### Query

- REST: `GET /api/search?q=&limit=&include_done=`
- MCP: `search_work(query, limit=25, include_done=false)`
- `q` / `query`: min length 2, max 200 (trim; empty → empty hits)
- `limit`: 1–50, default 25
- `include_done`: default false (open + blocked threads; always search projects + wiki)

### Match surfaces

| Kind | Fields |
| --- | --- |
| `thread` | summary, goal, focus, resume_step, next_steps, blocked_reason, project_slug, id |
| `project` | title, slug, tags, notes (if present) |
| `wiki` | project `PROGRESS.md` body (capped read + snippet window) |

### Hit shape

```json
{
  "query": "clock off",
  "hits": [
    {
      "kind": "thread",
      "id": "…",
      "title": "Finish Clock-Off docs",
      "snippet": "…wind-down schedule…",
      "project_slug": "adhd-hub",
      "status": "open",
      "score": 12.0
    }
  ]
}
```

- Snippets scrubbed with `scrub_scan_text` (paths / secrets / private URLs).
- Ranking: exact title/slug > field prefix > substring; open threads before done; newer `updated_at` first. Soft score is advisory only.

### UI

Wire existing My work search to the API when the query is ≥2 chars (debounce ~200ms). Show mixed hits with quiet kind labels; clicking a thread opens it as today; project hits select that project; wiki hits open the notes/progress reader for that slug. Empty query restores the normal thread list.

### Docs / release prep

- Public guide + short contract (same pattern as merge-dedupe).
- Stamp `docs/public/plans/improvement-roadmap.md` so **Now = Wave 8**, latest published **v0.21.1**.

## Constraints

- Local-first; authenticated REST / MCP only.
- Preserve one-thread-one-outcome and B1/B2 authority (search is read-only).
- Calm brand; honour reduced-motion (no flashy result animations).
- Reuse store/wiki; do not invent a second history store.

## Verify

- `uv run pytest` (new search tests + regression)
- `uv run ruff check src tests`
- Manual: My work search finds a thread by goal text not in the loaded list title
