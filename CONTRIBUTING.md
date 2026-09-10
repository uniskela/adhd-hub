# Contributing

## Dev setup

```bash
uv sync --all-extras
uv run pytest
uv run ruff check src tests
uv run adhd-hub serve --host 127.0.0.1 --port 8787
```

Preview the public docs site locally with `uv run zensical serve` (after `uv sync --extra dev`).

## Design notes

- **Hub owns truth** (SQLite + markdown wiki). OpenClaw is optional for nudges/memory.
- **MCP + REST** share `HubService` — add tools in `mcp_app.py` and routes in `api.py`.
- **Indexer** posts summaries only; never ship raw transcripts by default.
- Keep files focused; prefer small modules over growing `service.py` forever.

## Public adapters

Document new coding tools under `adapters/` with a minimal MCP/config snippet.
