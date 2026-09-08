# Scheduled transcript indexer (Windows)

Runs `adhd-hub index` against local Cursor/Codex/Claude transcript roots and posts **summaries only** to the hub. Does not mark threads done automatically.

## One-shot

```powershell
cd Z:\Projects\adhd-hub
uv run adhd-hub index --dry-run
uv run adhd-hub index
```

## Daily Task Scheduler

```powershell
.\scripts\install-indexer-task.ps1
```

Requires `ADHD_HUB_HUB_URL` / hub reachable and `ADHD_HUB_AUTH_TOKEN` in `.env`.
