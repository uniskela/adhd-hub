"""Forge orchestration extracted from HubService."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from adhd_hub.forge.board_sync import BoardForgeSync
from adhd_hub.forge.config import (
    ForgeConfig,
    forge_from_settings,
    load_forge_config,
    save_forge_config as persist_forge_config,
)
from adhd_hub.forge.wiki_sync import WikiForgeSync
from adhd_hub.models import Thread, ThreadStatus, ThreadUpsert
from adhd_hub.store import item_id

if TYPE_CHECKING:
    from adhd_hub.service import HubService

log = logging.getLogger(__name__)


class ForgeFacade:
    def __init__(self, hub: HubService) -> None:
        self._hub = hub

    def forge_config(self, project_slug: str | None = None) -> ForgeConfig:
        base = load_forge_config(
            self._hub.settings.data_dir, env_defaults=forge_from_settings(self._hub.settings)
        )
        data = base.model_dump()
        # Primary memory repos mirror at repo root (projects/<slug>/…)
        if data.get("primary_memory_repo") and str(data.get("wiki_path") or "").strip("/") in (
            "",
            "adhd-hub/wiki",
        ):
            data["wiki_path"] = ""
        if not project_slug:
            return ForgeConfig.model_validate(data)
        proj = self._hub.store.get_project(project_slug)
        if not proj:
            return ForgeConfig.model_validate(data)
        if proj.forge_owner:
            data["owner"] = proj.forge_owner
        if proj.forge_repo:
            data["repo"] = proj.forge_repo
        if proj.forge_wiki_path is not None:
            data["wiki_path"] = proj.forge_wiki_path
        if proj.forge_project_id:
            data["project_id"] = proj.forge_project_id
        return ForgeConfig.model_validate(data)

    def save_forge_config(self, config: ForgeConfig) -> ForgeConfig:
        # Persist empty wiki_path for primary memory instead of re-defaulting
        if config.primary_memory_repo and config.wiki_path.strip("/") == "adhd-hub/wiki":
            config = config.model_copy(update={"wiki_path": ""})
        persist_forge_config(self._hub.settings.data_dir, config)
        return config

    def _refresh_forge_section(self, slug: str) -> None:
        cfg = self.forge_config(slug)
        progress_url = cfg.file_web_url(f"projects/{slug}/PROGRESS.md")
        issue_links: list[tuple[str, str]] = []
        for t in self._hub.store.list_threads(
            status=ThreadStatus.open, project_slug=slug, limit=50
        ):
            pub = self._hub.thread_public_dict(t)
            url = pub.get("forge_issue_url")
            num = pub.get("forge_issue_number")
            if url and num:
                issue_links.append((f"#{num} {t.summary[:60]}", url))
        self._hub.wiki.ensure_forge_section(
            slug, progress_url=progress_url, issue_links=issue_links
        )

    def _forge_after_thread(self, thread: Thread) -> dict:
        cfg = self.forge_config(thread.project_slug)
        out: dict = {}
        try:
            out["board"] = BoardForgeSync(
                cfg,
                self._hub.store.get_meta,
                self._hub.store.set_meta,
                progress_reader=self._hub.wiki.read_progress,
            ).sync_thread(thread)
        except Exception as exc:
            log.exception("board sync failed")
            out["board"] = {"error": str(exc)}
        if thread.project_slug:
            try:
                self._refresh_forge_section(thread.project_slug)
            except Exception:
                log.exception("forge section refresh failed")
        try:
            # Global wiki tree still primary; per-project forge may point elsewhere
            # for board, while wiki uses configured wiki_path on that forge target.
            out["wiki"] = WikiForgeSync(cfg).push_wiki_tree(self._hub.settings.wiki_dir)
        except Exception as exc:
            log.exception("wiki sync failed")
            out["wiki"] = {"error": str(exc)}
        return out

    def sync_forge_now(self) -> dict:
        cfg = self.forge_config()
        from adhd_hub.forge.scaffold import push_primary_scaffold

        scaffold = push_primary_scaffold(
            cfg, hub_ui_url=self._hub.settings.resolve_public_url()
        )
        wiki = WikiForgeSync(cfg).push_wiki_tree(self._hub.settings.wiki_dir)
        board_results = []
        for thread in self._hub.list_open_threads(limit=200):
            try:
                tcfg = self.forge_config(thread.project_slug)
                board = BoardForgeSync(
                    tcfg,
                    self._hub.store.get_meta,
                    self._hub.store.set_meta,
                    progress_reader=self._hub.wiki.read_progress,
                )
                board_results.append(board.sync_thread(thread))
            except Exception as exc:  # noqa: BLE001 — continue syncing other threads
                board_results.append({"error": str(exc), "thread_id": thread.id})
        # Also push per-project forge wiki overrides (distinct owner/repo)
        per_project_wiki: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for proj in self._hub.store.list_projects():
            if not (proj.forge_owner and proj.forge_repo):
                continue
            key = (proj.forge_owner, proj.forge_repo, proj.forge_wiki_path or "")
            if key in seen:
                continue
            seen.add(key)
            pcfg = self.forge_config(proj.slug)
            try:
                per_project_wiki.append(
                    {
                        "slug": proj.slug,
                        "result": WikiForgeSync(pcfg).push_wiki_tree(
                            self._hub.settings.wiki_dir
                        ),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                per_project_wiki.append({"slug": proj.slug, "error": str(exc)})
        return {
            "scaffold": scaffold,
            "wiki": wiki,
            "board": board_results,
            "per_project_wiki": per_project_wiki,
            "config": cfg.public_dict(),
            "import_preview": self.preview_forge_import(),
        }

    def import_forge_inbox(self, *, limit: int = 50, close_imported: bool = True) -> dict:
        """Pull cloud-agent forge issues into Hub threads (never deletes remote issues)."""
        cfg = self.forge_config()
        if not (cfg.enabled() and cfg.board_enabled and cfg.board_inbox_enabled):
            return {
                "skipped": True,
                "reason": "board_inbox_disabled",
                "imported": [],
                "skipped_issues": [],
            }
        authors = [
            name.strip()
            for name in (cfg.board_inbox_authors or [])
            if isinstance(name, str) and name.strip()
        ]
        if not authors:
            return {
                "skipped": True,
                "reason": "board_inbox_authors_required",
                "imported": [],
                "skipped_issues": [],
                "hint": "Add allowed forge usernames under Settings → Forge → Inbox authors.",
            }
        board = BoardForgeSync(
            cfg,
            self._hub.store.get_meta,
            self._hub.store.set_meta,
            progress_reader=self._hub.wiki.read_progress,
        )
        mapped_numbers = {
            value: key.removeprefix("forge_issue:")
            for key, value in self._hub.store.list_meta_prefix("forge_issue:").items()
        }
        imported: list[dict] = []
        skipped: list[dict] = []
        try:
            issues = board.list_inbox_issues(limit=limit)
        except Exception as exc:
            log.exception("forge inbox list failed")
            return {"error": str(exc), "imported": [], "skipped_issues": []}

        for issue in issues:
            number = int(issue.get("number") or 0)
            if not number:
                continue
            if str(number) in mapped_numbers:
                skipped.append(
                    {
                        "number": number,
                        "reason": "already_mapped",
                        "thread_id": mapped_numbers[str(number)],
                    }
                )
                continue
            body = issue.get("body") or ""
            existing = re.search(r"\*\*ADHD Hub thread\*\*\s+`([^`]+)`", body)
            if existing:
                thread_id = existing.group(1).strip()
                self._hub.store.set_meta(f"forge_issue:{thread_id}", str(number))
                if close_imported:
                    try:
                        board.mark_issue_imported(number, thread_id=thread_id)
                    except Exception as exc:  # noqa: BLE001
                        skipped.append(
                            {"number": number, "reason": f"link_close_failed:{exc}"}
                        )
                        continue
                skipped.append(
                    {
                        "number": number,
                        "reason": "linked_existing_marker",
                        "thread_id": thread_id,
                    }
                )
                continue

            title = (issue.get("title") or "").strip()
            summary = re.sub(r"^\[ADHD\]\s*", "", title, flags=re.IGNORECASE).strip() or title
            if not summary:
                skipped.append({"number": number, "reason": "empty_title"})
                continue

            project_slug = None
            source_tool = "forge-inbox"
            for lab in issue.get("labels") or []:
                name = lab.get("name") if isinstance(lab, dict) else str(lab)
                if not isinstance(name, str):
                    continue
                if name.startswith("project:"):
                    project_slug = name.split(":", 1)[1].strip() or None
                elif name.startswith("source:"):
                    raw_source = name.split(":", 1)[1].strip().lower()
                    allowed = {
                        "codex",
                        "chatgpt",
                        "cursor",
                        "claude",
                        "claude-code",
                        "openclaw",
                    }
                    if raw_source in allowed:
                        source_tool = raw_source

            payload = ThreadUpsert(
                # Stable per forge issue so same titles do not collide into one thread.
                id=item_id(
                    f"forge-issue:{number}",
                    f"{cfg.owner}/{cfg.repo}",
                ),
                summary=summary[:500],
                project_slug=project_slug,
                source_tool=source_tool,
                origin="forge-inbox",
                chat_ref=f"forge-issue:{number}",
            )
            slug = self._hub._resolve_slug_for_write(
                project_slug=payload.project_slug,
                workspace_path=payload.workspace_path,
                summary_or_title=payload.summary,
            )
            payload = payload.model_copy(update={"project_slug": slug})
            self._hub.store.ensure_project_for_slug(
                slug, title=payload.summary[:80], workspace_path=payload.workspace_path
            )
            thread = self._hub.store.upsert_thread(payload)
            # Map before any outbound board sync so we update issue #N instead of creating another.
            self._hub.store.set_meta(f"forge_issue:{thread.id}", str(number))
            self._hub.wiki.upsert_progress(
                thread.project_slug or slug,
                content=(f"Imported from forge issue #{number}: {thread.summary}"),
                title=thread.summary,
                thread=thread,
            )
            self._hub.wiki.rebuild_index(
                self._hub.store.list_threads(status=ThreadStatus.open, limit=500)
            )

            note = body.strip()
            if note:
                if len(note) > 8000:
                    note = note[:8000].rstrip() + "\n\n…(truncated from forge issue)"
                self._hub.wiki.upsert_progress(
                    thread.project_slug or slug,
                    content=note,
                    title=thread.summary,
                    thread=thread,
                )
                self._hub.store.add_progress_note(thread.project_slug or slug, note)

            close_result = None
            if close_imported:
                try:
                    close_result = board.mark_issue_imported(number, thread_id=thread.id)
                except Exception as exc:  # noqa: BLE001
                    close_result = {"error": str(exc)}
            imported.append(
                {
                    "number": number,
                    "thread_id": thread.id,
                    "project_slug": thread.project_slug,
                    "title": summary,
                    "url": issue.get("html_url") or issue.get("url"),
                    "closed": close_result,
                }
            )
        return {
            "imported": imported,
            "skipped_issues": skipped,
            "count": len(imported),
            "config": {
                "board_inbox_enabled": cfg.board_inbox_enabled,
                "synced_label": cfg.board_inbox_synced_label,
                "authors": authors,
            },
        }

    def preview_forge_import(self) -> dict:
        """Compare remote forge projects/* with local registry + wiki."""
        cfg = self.forge_config()
        if not (cfg.enabled() and cfg.wiki_enabled):
            return {
                "skipped": True,
                "reason": "wiki_sync_disabled",
                "candidates": [],
                "importable_count": 0,
            }
        scan = WikiForgeSync(cfg).list_remote_project_slugs()
        if scan.get("skipped"):
            return {
                "skipped": True,
                "reason": scan.get("reason"),
                "candidates": [],
                "importable_count": 0,
                "errors": scan.get("errors") or [],
            }
        local_slugs = {p.slug for p in self._hub.store.list_projects()}
        candidates: list[dict] = []
        for item in scan.get("projects") or []:
            slug = item["slug"]
            local_progress = self._hub.wiki.read_progress(slug)
            status = "new"
            if slug in local_slugs:
                status = "registered"
            elif local_progress:
                status = "local_wiki_only"
            candidates.append(
                {
                    "slug": slug,
                    "status": status,
                    "has_remote_progress": bool(item.get("has_progress")),
                    "has_local_progress": local_progress is not None,
                    "path": item.get("path"),
                }
            )
        importable = [
            c
            for c in candidates
            if c["status"] in {"new", "local_wiki_only"} and c["has_remote_progress"]
        ]
        return {
            "skipped": False,
            "candidates": candidates,
            "importable_count": len(importable),
            "errors": scan.get("errors") or [],
        }
