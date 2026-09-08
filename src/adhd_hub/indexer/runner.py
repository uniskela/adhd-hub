from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from adhd_hub.config import Settings
from adhd_hub.indexer.parsers import (
    parse_file_with_origins,
    walk_jsonl,
)
from adhd_hub.store import slugify

log = logging.getLogger(__name__)


def _default_paths() -> dict[str, Path]:
    home = Path.home()
    return {
        "cursor": home / ".cursor" / "projects",
        "codex": home / ".codex" / "sessions",
        "claude": home / ".claude" / "projects",
    }


def collect_candidates(settings: Settings) -> list[dict[str, Any]]:
    defaults = _default_paths()
    roots = {
        "cursor": settings.cursor_projects_dir or defaults["cursor"],
        "codex": settings.codex_sessions_dir or defaults["codex"],
        "claude": settings.claude_projects_dir or defaults["claude"],
    }
    items: list[dict[str, Any]] = []
    per_tool = max(1, settings.max_sessions // max(1, len(roots)))
    for tool, root in roots.items():
        files = walk_jsonl(Path(root))[:per_tool]
        for path in files:
            try:
                parsed = parse_file_with_origins(path, tool)
            except Exception:
                log.exception("failed parsing %s", path)
                continue
            workspace_hint = None
            parts = path.parts
            if "agent-transcripts" in parts:
                idx = parts.index("agent-transcripts")
                if idx > 0:
                    workspace_hint = parts[idx - 1]
            for row in parsed:
                items.append(
                    {
                        "summary": row["summary"],
                        "source_tool": tool,
                        "workspace_path": workspace_hint,
                        "project_slug": slugify(workspace_hint or row["summary"][:40]),
                        "transcript_ref": str(path),
                        "origin": row["origin"],
                    }
                )
    return items


def run_indexer(
    settings: Settings, *, dry_run: bool = False, force: bool = False
) -> dict[str, Any]:
    del force  # reserved for mtime cache later
    items = collect_candidates(settings)
    if dry_run:
        return {"dry_run": True, "candidates": len(items), "sample": items[:10]}

    hub_url = (settings.hub_url or f"http://{settings.host}:{settings.port}").rstrip("/")
    token = settings.auth_token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Prefer posting to remote hub; if same process data dir, also allow local upsert
    if not items:
        return {"upserted": 0, "candidates": 0}

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{hub_url}/api/indexer/batch",
                headers=headers,
                json={"items": items},
            )
            resp.raise_for_status()
            body = resp.json()
            return {"upserted": body.get("upserted", 0), "candidates": len(items), "hub": hub_url}
    except (httpx.HTTPError, OSError, ValueError) as exc:
        log.warning("Hub POST failed (%s); writing locally via service", exc)
        from adhd_hub.models import ThreadUpsert
        from adhd_hub.service import HubService

        svc = HubService(settings)
        n = 0
        for item in items:
            svc.upsert_thread(ThreadUpsert(**item))
            n += 1
        return {"upserted": n, "candidates": len(items), "mode": "local"}
