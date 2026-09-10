"""Migrate forge wiki_path from legacy ``adhd-hub/wiki`` to repo-root ``projects/``."""

from __future__ import annotations

from typing import Any

from adhd_hub.config import Settings
from adhd_hub.forge.config import ForgeConfig, load_forge_config, save_forge_config
from adhd_hub.models import ProjectUpsert
from adhd_hub.service import HubService

LEGACY_PREFIX = "adhd-hub/wiki"


def _normalize_wiki_path(value: str | None) -> str:
    return (value or "").strip().strip("/")


def plan_forge_wiki_path_cleanup(settings: Settings) -> dict[str, Any]:
    """Describe local config changes needed for the legacy wiki path."""
    service = HubService(settings)
    cfg = service.forge_config()
    changes: list[dict[str, str]] = []
    current = _normalize_wiki_path(cfg.wiki_path)
    if current == LEGACY_PREFIX or current.startswith(f"{LEGACY_PREFIX}/"):
        changes.append(
            {
                "scope": "forge.json",
                "from": cfg.wiki_path or LEGACY_PREFIX,
                "to": "",
                "note": "Blank wiki_path = projects/<slug>/ at repo root (primary memory layout)",
            }
        )

    for proj in service.list_projects(limit=500, include_archived=True):
        path = _normalize_wiki_path(proj.get("forge_wiki_path"))
        if path == LEGACY_PREFIX or path.startswith(f"{LEGACY_PREFIX}/"):
            changes.append(
                {
                    "scope": f"project:{proj['slug']}",
                    "from": proj.get("forge_wiki_path") or LEGACY_PREFIX,
                    "to": "",
                    "note": "Clear per-project override so root projects/ layout is used",
                    "title": proj.get("title") or proj["slug"],
                }
            )

    return {
        "legacy_prefix": LEGACY_PREFIX,
        "changes": changes,
        "count": len(changes),
        "remote_note": (
            "This updates Hub config only. Move remote files from "
            f"`{LEGACY_PREFIX}/projects/` to `projects/` in the forge repo separately "
            "(or re-sync after relocating)."
        ),
    }


def apply_forge_wiki_path_cleanup(settings: Settings, *, dry_run: bool = True) -> dict[str, Any]:
    plan = plan_forge_wiki_path_cleanup(settings)
    if dry_run or not plan["changes"]:
        return {**plan, "applied": False, "dry_run": dry_run}

    service = HubService(settings)
    data_dir = settings.data_dir
    cfg_path_exists = (data_dir / "forge.json").is_file()
    cfg = load_forge_config(data_dir) if cfg_path_exists else service.forge_config()
    if isinstance(cfg, ForgeConfig):
        current = _normalize_wiki_path(cfg.wiki_path)
        if current == LEGACY_PREFIX or current.startswith(f"{LEGACY_PREFIX}/"):
            cfg = cfg.model_copy(update={"wiki_path": ""})
            save_forge_config(data_dir, cfg)

    for change in plan["changes"]:
        if not change["scope"].startswith("project:"):
            continue
        slug = change["scope"].split(":", 1)[1]
        existing = service.store.get_project(slug)
        if existing is None:
            continue
        service.upsert_project(
            ProjectUpsert(
                slug=slug,
                title=existing.title,
                description=existing.description,
                repo_url=existing.repo_url,
                workspace_paths=list(existing.workspace_paths),
                default_energy=existing.default_energy,
                forge_owner=existing.forge_owner,
                forge_repo=existing.forge_repo,
                forge_wiki_path="",
                forge_project_id=existing.forge_project_id,
            )
        )

    return {**plan, "applied": True, "dry_run": False}
