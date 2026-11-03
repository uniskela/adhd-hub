# Global search

My work search finds threads, projects, and local wiki progress snippets without
an external index. Type at least two characters in **Search threads, projects,
notes** on the dashboard. Results stay on your Hub; nothing is sent to a
third-party search service.

See [Dashboard](dashboard.md) for the UI and the
[search contract](https://github.com/uniskela/adhd-hub/blob/main/docs/internal/contracts/global-search.md)
for maintainer details.

## Operations

REST routes require your existing bearer token or browser session. HTTP MCP
uses authenticated `/mcp`; local stdio exposes the same tool.

| Operation | MCP tool | REST |
| --- | --- | --- |
| Search work | `search_work(query, limit=25, include_done=false)` | `GET /api/search?q=…&limit=25&include_done=false` |

Query length is 2–200 characters. Limits are 1–50 (default 25). By default,
finished and dismissed threads are omitted; projects and wiki snippets still
match. Set `include_done=true` when you need finished work too.

Each hit includes `kind` (`thread`, `project`, or `wiki`), a title, a short
scrubbed snippet, optional `project_slug` / `status`, and an advisory `score`.
Search is read-only: it never creates or changes threads.

## What is matched

- **Threads** — summary, goal, focus, resume step, next steps, blocked reason, project slug, id
- **Projects** — title, slug, tags, description
- **Wiki** — project `PROGRESS.md` bodies (capped read; first matching window)

Snippets redact secrets, absolute paths, and private URLs the same way scan
lines do.
