# Contributing

## Dev setup

```bash
uv sync --extra dev --frozen
uv run pytest -q
uv run ruff check src tests
git diff --check
uv run adhd-hub serve --host 127.0.0.1 --port 8787
```

Preview the public docs site locally with `uv run zensical serve` (after `uv sync --extra dev`).

CI runs the full pytest suite and Ruff with Python 3.12 and the frozen `uv.lock`.
The quality workflow is read-only: fixes belong in reviewed source changes.

## UI modules

Edit `src/adhd_hub/ui/js/` directly; the dashboard loads `js/boot.js`.
The old `ui/app.js` IIFE is a historical migration input, not the source of the
current modules. `scripts/split_ui_modules.py` no longer writes files: its legacy
renderer does not know about newer UI features and must not regenerate them.
`uv run python scripts/split_ui_modules.py --check` checks the maintained focus
timer's mutability without writing. `tests/test_ui_module_state.py` also guards
shared-state assignments across all current modules.

## Design notes

- **Hub owns truth** (SQLite + markdown wiki). OpenClaw is optional for nudges/memory.
- **MCP transports (Streamable HTTP + local stdio) + REST** share `HubService` — add tools in `mcp_app.py` and routes in `api.py`.
- **Indexer** posts summaries only; never ship raw transcripts by default.
- Keep files focused; prefer small modules over growing `service.py` forever.

## Public adapters

Document new coding tools under `adapters/` with a minimal MCP/config snippet.

## Cursor Marketplace plugin skills

Hub `skills/` and `adapters/cursor-rule.mdc` are the source of truth for the
[`adhd-hub-cursorskill`](https://github.com/uniskela/adhd-hub-cursorskill) plugin.
Edit skills here; a GitHub Action opens a plugin PR (never pushes plugin `main`).
See [Cursor plugin skill sync](docs/cursor-plugin-skill-sync.md) and
[`.github/cursorskill-sync.md`](.github/cursorskill-sync.md).
