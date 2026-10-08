# Scheduled transcript indexer (Windows)

This is an **advanced optional setup** for people who want a local transcript backstop. It runs `adhd-hub index` against local Cursor/Codex/Claude transcript roots and posts **summaries only** to the Hub. It does not mark threads done automatically.

## One-shot

```powershell
cd C:\path\to\adhd-hub
uv run adhd-hub index --dry-run
uv run adhd-hub index
```

## Daily Task Scheduler

```powershell
.\scripts\install-indexer-task.ps1
```

Requires `ADHD_HUB_HUB_URL` / a reachable Hub and `ADHD_HUB_AUTH_TOKEN` in `.env`.
