from __future__ import annotations

import logging
import random
from collections.abc import Callable
from datetime import UTC

from adhd_hub.config import Settings
from adhd_hub.forge import ForgeFacade, WikiForgeSync
from adhd_hub.forge.config import ForgeConfig
from adhd_hub.models import (
    EnergyLevel,
    OverlapResult,
    ProgressUpsert,
    Project,
    ProjectUpsert,
    Reminder,
    ReminderCreate,
    ReminderKind,
    SessionDigest,
    Thread,
    ThreadStatus,
    ThreadUpsert,
)
from adhd_hub.openclaw import stale_cutoff
from adhd_hub.openclaw_config import OpenClawConfig
from adhd_hub.openclaw_facade import OpenClawFacade
from adhd_hub.overlap import check_overlap
from adhd_hub.prefs import HubPrefs, load_prefs, save_prefs
from adhd_hub.store import Store, slugify, workspace_basename
from adhd_hub.wiki import Wiki

log = logging.getLogger(__name__)


class HubService:
    def __init__(self, settings: Settings) -> None:
        settings.ensure_dirs()
        self.settings = settings
        self.store = Store(settings.db_path)
        self._prefs = load_prefs(settings.data_dir, default_timezone=settings.timezone)
        self.wiki = Wiki(settings.wiki_dir, timezone=self._prefs.timezone)
        self._forge = ForgeFacade(self)
        self._openclaw_ops = OpenClawFacade(self)

    def _apply_openclaw_config(self, config: OpenClawConfig) -> None:
        self._openclaw_ops._apply_openclaw_config(config)

    def openclaw_config(self) -> OpenClawConfig:
        return self._openclaw_ops.openclaw_config()

    def save_openclaw_config(self, config: OpenClawConfig) -> OpenClawConfig:
        return self._openclaw_ops.save_openclaw_config(config)

    def openclaw_pair_status(self) -> dict:
        return self._openclaw_ops.openclaw_pair_status()

    def start_openclaw_pair(self, *, hub_origin: str) -> dict:
        return self._openclaw_ops.start_openclaw_pair(hub_origin=hub_origin)

    def submit_openclaw_pair(self, payload: dict) -> dict:
        return self._openclaw_ops.submit_openclaw_pair(payload)

    def approve_openclaw_pair(self) -> dict:
        return self._openclaw_ops.approve_openclaw_pair()

    def cancel_openclaw_pair(self) -> dict:
        return self._openclaw_ops.cancel_openclaw_pair()

    def set_stale_schedule_callback(self, callback: Callable[[str], None]) -> None:
        self._openclaw_ops.set_stale_schedule_callback(callback)

    async def test_openclaw_connection(self) -> dict[str, str | bool]:
        return await self._openclaw_ops.test_openclaw_connection()

    def prefs(self) -> HubPrefs:
        return self._prefs

    def save_prefs(self, prefs: HubPrefs) -> HubPrefs:
        self._prefs = prefs
        save_prefs(self.settings.data_dir, prefs)
        self.wiki.set_timezone(prefs.timezone)
        return prefs

    def forge_config(self, project_slug: str | None = None) -> ForgeConfig:
        return self._forge.forge_config(project_slug)

    def save_forge_config(self, config: ForgeConfig) -> ForgeConfig:
        return self._forge.save_forge_config(config)

    def resolve_project(
        self,
        *,
        workspace_path: str | None = None,
        project_slug: str | None = None,
        create_if_missing: bool = False,
        title: str | None = None,
    ) -> Project | None:
        if project_slug:
            proj = self.store.get_project(project_slug)
            if proj:
                if workspace_path:
                    return self.store.ensure_project_for_slug(
                        proj.slug, title=proj.title, workspace_path=workspace_path
                    )
                return proj
            if create_if_missing:
                return self.store.ensure_project_for_slug(
                    slugify(project_slug),
                    title=title or project_slug,
                    workspace_path=workspace_path,
                )
        if workspace_path:
            found = self.store.resolve_project_by_workspace(workspace_path)
            if found:
                return found
            if create_if_missing:
                base = workspace_basename(workspace_path) or "untitled"
                return self.store.ensure_project_for_slug(
                    slugify(base),
                    title=title or base.replace("-", " ").title(),
                    workspace_path=workspace_path,
                )
        return None

    def upsert_project(self, payload: ProjectUpsert) -> Project:
        return self.store.upsert_project(payload)

    def get_project_detail(self, slug: str) -> dict | None:
        from adhd_hub.store import slugify as _slugify

        safe = _slugify(slug)
        proj = self.store.get_project(safe)
        counts = self.store.thread_counts_by_project().get(
            safe, {"open": 0, "blocked": 0, "done": 0, "dismissed": 0}
        )
        threads = [
            self.thread_public_dict(t)
            for t in self.store.list_threads(project_slug=safe, limit=100)
        ]
        open_threads = [t for t in threads if t.get("status") == "open"]
        cfg = self.forge_config(safe)
        progress_rel = f"projects/{safe}/PROGRESS.md"
        forge_folder = cfg.file_web_url(progress_rel)
        data = (
            proj.model_dump(mode="json")
            if proj
            else {
                "slug": safe,
                "title": safe.replace("-", " ").title(),
                "unregistered": True,
            }
        )
        data["counts"] = counts
        data["archived"] = bool(proj.archived_at) if proj else False
        data["threads"] = threads
        data["next_up"] = open_threads[0] if open_threads else None
        data["progress"] = self.wiki.read_progress(safe)
        data["progress_path"] = progress_rel
        data["forge"] = {
            "folder_url": forge_folder,
            "wiki_path": cfg.wiki_path,
            "owner": cfg.owner,
            "repo": cfg.repo,
            "enabled": cfg.enabled(),
        }
        return data

    def rename_project(self, old_slug: str, new_slug: str, *, title: str | None = None) -> dict:
        from adhd_hub.store import slugify as _slugify

        old = _slugify(old_slug)
        new = _slugify(new_slug)
        if not self.store.get_project(old):
            raise KeyError("not_found")
        if old != new and self.store.get_project(new):
            raise ValueError("conflict")
        # Local wiki first (staged); then DB; then forge
        wiki_result = self.wiki.rename_project(old, new)
        try:
            proj = self.store.rename_project(old, new, title=title)
        except Exception:
            # Attempt wiki rollback
            if wiki_result.get("renamed"):
                try:
                    self.wiki.rename_project(new, old)
                except Exception:
                    log.exception("wiki rollback after rename DB failure")
            raise
        self.wiki.rebuild_index(self.store.list_threads(status=ThreadStatus.open, limit=500))
        forge_out: dict = {"uploaded": [], "deleted": [], "errors": []}
        cfg = self.forge_config(proj.slug)
        if cfg.enabled() and cfg.wiki_enabled:
            try:
                content = self.wiki.read_progress(proj.slug) or ""
                old_rel = f"projects/{old}/PROGRESS.md"
                new_rel = f"projects/{new}/PROGRESS.md"
                if content:
                    move = WikiForgeSync(cfg).move_file(old_rel, new_rel, content)
                    forge_out["uploaded"].append(new_rel)
                    if move.get("deleted", {}).get("deleted"):
                        forge_out["deleted"].append(old_rel)
                WikiForgeSync(cfg).push_wiki_tree(self.settings.wiki_dir)
            except Exception as exc:  # noqa: BLE001
                forge_out["errors"].append(str(exc))
        # Resync open threads so labels/bodies pick up new slug
        for thread in self.store.list_threads(
            status=ThreadStatus.open, project_slug=proj.slug, limit=100
        ):
            try:
                self._forge_after_thread(thread)
            except Exception as exc:  # noqa: BLE001
                forge_out["errors"].append(f"thread {thread.id}: {exc}")
        self._refresh_forge_section(proj.slug)
        return {"project": proj.model_dump(mode="json"), "wiki": wiki_result, "forge": forge_out}

    def delete_project(
        self,
        slug: str,
        *,
        delete_progress: bool = False,
        delete_remote: bool = False,
    ) -> dict:
        from adhd_hub.store import slugify as _slugify

        safe = _slugify(slug)
        if not self.store.get_project(safe):
            raise KeyError("not_found")
        forge_out: dict = {"deleted": [], "errors": []}
        cfg = self.forge_config(safe)
        if delete_remote and cfg.enabled() and cfg.wiki_enabled:
            try:
                rel = f"projects/{safe}/PROGRESS.md"
                result = WikiForgeSync(cfg).delete_file(rel)
                if result.get("deleted"):
                    forge_out["deleted"].append(rel)
            except Exception as exc:  # noqa: BLE001
                forge_out["errors"].append(str(exc))
        wiki_result = (
            self.wiki.delete_project(safe)
            if delete_progress
            else {"deleted": False, "skipped": True}
        )
        store_result = self.store.delete_project(safe)
        self.wiki.rebuild_index(self.store.list_threads(status=ThreadStatus.open, limit=500))
        if cfg.enabled() and cfg.wiki_enabled:
            try:
                WikiForgeSync(cfg).push_wiki_tree(self.settings.wiki_dir)
            except Exception as exc:  # noqa: BLE001
                forge_out["errors"].append(str(exc))
        return {
            "store": store_result,
            "wiki": wiki_result,
            "forge": forge_out,
            "delete_progress": delete_progress,
            "delete_remote": delete_remote,
        }

    def request_delete_project(
        self,
        slug: str,
        *,
        delete_progress: bool = False,
        delete_remote: bool = False,
        reason: str | None = None,
        source_tool: str | None = None,
    ) -> dict:
        from adhd_hub.models import PendingActionKind
        from adhd_hub.store import slugify as _slugify

        safe = _slugify(slug)
        if not self.store.get_project(safe):
            raise KeyError("not_found")
        action = self.store.create_pending_action(
            kind=PendingActionKind.delete_project,
            payload={
                "slug": safe,
                "delete_progress": delete_progress,
                "delete_remote": delete_remote,
            },
            reason=reason,
            source_tool=source_tool,
        )
        return {
            "pending": True,
            "action": action.model_dump(mode="json"),
            "message": (
                f"Delete of `{safe}` needs confirmation in /ui (Pending actions). Not deleted yet."
            ),
        }

    def request_rename_project(
        self,
        slug: str,
        new_slug: str,
        *,
        title: str | None = None,
        reason: str | None = None,
        source_tool: str | None = None,
    ) -> dict:
        from adhd_hub.models import PendingActionKind
        from adhd_hub.store import slugify as _slugify

        old = _slugify(slug)
        new = _slugify(new_slug)
        if not self.store.get_project(old):
            raise KeyError("not_found")
        if old != new and self.store.get_project(new):
            raise ValueError("conflict")
        action = self.store.create_pending_action(
            kind=PendingActionKind.rename_project,
            payload={"slug": old, "new_slug": new, "title": title},
            reason=reason,
            source_tool=source_tool,
        )
        return {
            "pending": True,
            "action": action.model_dump(mode="json"),
            "message": (f"Rename `{old}` → `{new}` needs confirmation in /ui. Not renamed yet."),
        }

    def list_pending_actions(self) -> list[dict]:
        return [a.model_dump(mode="json") for a in self.store.list_pending_actions()]

    def approve_pending_action(self, action_id: str) -> dict:
        from adhd_hub.models import PendingActionKind, PendingActionStatus

        action = self.store.get_pending_action(action_id)
        if not action:
            raise KeyError("not_found")
        if action.status != PendingActionStatus.pending:
            return {
                "already_resolved": True,
                "action": action.model_dump(mode="json"),
            }
        result: dict
        if action.kind == PendingActionKind.delete_project:
            result = self.delete_project(
                action.payload["slug"],
                delete_progress=bool(action.payload.get("delete_progress")),
                delete_remote=bool(action.payload.get("delete_remote")),
            )
        elif action.kind == PendingActionKind.rename_project:
            result = self.rename_project(
                action.payload["slug"],
                action.payload["new_slug"],
                title=action.payload.get("title"),
            )
        else:
            raise ValueError(f"unsupported_kind:{action.kind}")
        resolved = self.store.resolve_pending_action(action_id, PendingActionStatus.approved)
        return {
            "approved": True,
            "action": resolved.model_dump(mode="json") if resolved else None,
            "result": result,
        }

    def reject_pending_action(self, action_id: str) -> dict:
        from adhd_hub.models import PendingActionStatus

        action = self.store.get_pending_action(action_id)
        if not action:
            raise KeyError("not_found")
        if action.status != PendingActionStatus.pending:
            return {
                "already_resolved": True,
                "action": action.model_dump(mode="json"),
            }
        resolved = self.store.resolve_pending_action(action_id, PendingActionStatus.rejected)
        return {
            "rejected": True,
            "action": resolved.model_dump(mode="json") if resolved else None,
        }

    def _refresh_forge_section(self, slug: str) -> None:
        self._forge._refresh_forge_section(slug)

    def list_projects(self, limit: int = 200, *, include_archived: bool = False) -> list[dict]:
        counts = self.store.thread_counts_by_project()
        out = []
        for p in self.store.list_projects(limit=limit, include_archived=include_archived):
            data = p.model_dump(mode="json")
            c = counts.get(p.slug, {"open": 0, "blocked": 0, "done": 0, "dismissed": 0})
            data["counts"] = c
            data["archived"] = bool(p.archived_at)
            out.append(data)
        # Include unclassified bucket if threads exist without registry row
        for slug, c in counts.items():
            if slug == "unclassified" or self.store.get_project(slug):
                continue
            if not any(x["slug"] == slug for x in out):
                out.append(
                    {
                        "slug": slug,
                        "title": slug.replace("-", " ").title(),
                        "description": None,
                        "repo_url": None,
                        "workspace_paths": [],
                        "default_energy": "unknown",
                        "forge_owner": None,
                        "forge_repo": None,
                        "forge_wiki_path": None,
                        "forge_project_id": None,
                        "archived_at": None,
                        "archived": False,
                        "counts": c,
                        "unregistered": True,
                    }
                )
        return out

    def archive_project(self, slug: str) -> dict:
        if slugify(slug) == "unclassified":
            raise ValueError("Inbox cannot be archived")
        proj = self.store.set_project_archived(slug, archived=True)
        data = proj.model_dump(mode="json")
        data["archived"] = True
        return data

    def restore_project(self, slug: str) -> dict:
        proj = self.store.set_project_archived(slug, archived=False)
        data = proj.model_dump(mode="json")
        data["archived"] = False
        return data

    def _resolve_slug_for_write(
        self,
        *,
        project_slug: str | None,
        workspace_path: str | None,
        summary_or_title: str | None = None,
    ) -> str:
        proj = self.resolve_project(
            workspace_path=workspace_path,
            project_slug=project_slug,
            create_if_missing=True,
            title=summary_or_title,
        )
        if proj:
            return proj.slug
        if project_slug:
            return slugify(project_slug)
        if workspace_path:
            return slugify(workspace_basename(workspace_path) or "untitled")
        return slugify(summary_or_title or "untitled")

    def thread_public_dict(self, thread: Thread) -> dict:
        data = thread.model_dump(mode="json")
        raw = self.store.get_meta(f"forge_issue:{thread.id}")
        cfg = self.forge_config(thread.project_slug)
        if raw and str(raw).isdigit():
            number = int(raw)
            data["forge_issue_number"] = number
            data["forge_issue_url"] = cfg.issue_web_url(number)
        if thread.project_slug:
            snippet = self.wiki.read_progress(thread.project_slug)
            if snippet:
                data["progress_snippet"] = snippet[-800:]
        return data

    def list_threads_public(
        self,
        *,
        status: ThreadStatus | None = ThreadStatus.open,
        energy: EnergyLevel | None = None,
        project_slug: str | None = None,
        limit: int = 100,
        stale: bool = False,
    ) -> list[dict]:
        if stale:
            threads = self.list_stale_threads()
            if project_slug:
                threads = [t for t in threads if t.project_slug == project_slug]
        elif status is None:
            threads = self.store.list_threads(
                status=None, energy=energy, project_slug=project_slug, limit=limit
            )
        else:
            threads = self.store.list_threads(
                status=status, energy=energy, project_slug=project_slug, limit=limit
            )
        return [self.thread_public_dict(t) for t in threads]

    def overview(self) -> dict:
        open_threads = self.list_open_threads(limit=500)
        stale = self.list_stale_threads()
        blocked = self.store.list_threads(status=ThreadStatus.blocked, limit=100)
        timezone = self.prefs().timezone
        stats = self.store.done_counts(timezone=timezone)
        from adhd_hub.rewards import reward_summary
        return {
            "open": len(open_threads),
            "stale": len(stale),
            "done": stats["done_total"],
            "rewards": reward_summary(stats["done_total"]),
            "next_up": self.thread_public_dict(open_threads[0]) if open_threads else None,
            "blocked": len(blocked),
            "stale_days": self.settings.stale_days,
            "done_today": stats["done_today"],
            "done_week": stats["done_week"],
            "day_streak": stats["day_streak"],
            "added_vs_finished": self.store.analytics_added_done(14, timezone=timezone),
            "projects": self.list_projects(),
            "timezone": self.prefs().timezone,
            "pending_actions": self.list_pending_actions(),
            "due_reminders": [
                r.model_dump(mode="json") for r in self.store.due_reminders()[:20]
            ],
            "reminders": [
                r.model_dump(mode="json")
                for r in self.store.list_reminders(include_handled=False)[:30]
            ],
        }

    def agent_overview(self) -> dict:
        """Compact overview for MCP agents (no rewards chart payload)."""
        full = self.overview()
        next_up = full.get("next_up")
        return {
            "open": full["open"],
            "stale": full["stale"],
            "blocked": full["blocked"],
            "done_today": full["done_today"],
            "projects": len(full.get("projects") or []),
            "pending_actions": len(full.get("pending_actions") or []),
            "timezone": full.get("timezone"),
            "next_up": (
                {
                    "id": next_up.get("id"),
                    "summary": next_up.get("summary"),
                    "project_slug": next_up.get("project_slug"),
                    "resume_step": next_up.get("resume_step"),
                    "paused_at": next_up.get("paused_at"),
                }
                if isinstance(next_up, dict)
                else None
            ),
            "due_reminders": [
                r.model_dump(mode="json") for r in self.store.due_reminders()[:10]
            ],
        }

    def register_workspace(
        self,
        workspace_path: str,
        *,
        title: str | None = None,
        create_open_thread: bool = True,
        summary: str | None = None,
        source_tool: str | None = "mcp",
    ) -> dict:
        """Register a folder as a project; optionally open a default thread."""
        from adhd_hub.store import workspace_basename

        path = str(workspace_path or "").strip()
        if not path:
            raise ValueError("workspace_path required")
        base = workspace_basename(path) or "project"
        display = (title or "").strip() or base.replace("-", " ").replace("_", " ").title()
        proj = self.resolve_project(
            workspace_path=path,
            create_if_missing=True,
            title=display,
        )
        if not proj:
            raise ValueError("could_not_register")
        thread = None
        created_thread = False
        if create_open_thread:
            existing = [
                t
                for t in self.store.list_threads(
                    status=ThreadStatus.open, project_slug=proj.slug, limit=5
                )
            ]
            if existing:
                thread = existing[0]
            else:
                thread_summary = (summary or "").strip() or f"Continue {proj.title}"
                thread = self.upsert_thread(
                    ThreadUpsert(
                        summary=thread_summary[:500],
                        project_slug=proj.slug,
                        workspace_path=path,
                        source_tool=source_tool or "mcp",
                        origin="manual",
                    )
                )
                created_thread = True
        return {
            "project": proj.model_dump(mode="json"),
            "thread": self.thread_public_dict(thread) if thread else None,
            "created_thread": created_thread,
        }

    def openclaw_memory_digest(
        self,
        *,
        project_slug: str | None = None,
        note: str | None = None,
        threads: list[Thread] | None = None,
    ) -> tuple[str, str]:
        """Build a short OpenClaw memory digest (summaries only; no transcripts)."""
        return self._openclaw_ops.openclaw_memory_digest(
            project_slug=project_slug, note=note, threads=threads
        )

    def push_openclaw_memory_sync(
        self,
        *,
        project_slug: str | None = None,
        note: str | None = None,
        threads: list[Thread] | None = None,
    ) -> dict:
        return self._openclaw_ops.push_openclaw_memory_sync(
            project_slug=project_slug, note=note, threads=threads
        )

    async def push_openclaw_memory(
        self,
        *,
        project_slug: str | None = None,
        note: str | None = None,
        threads: list[Thread] | None = None,
    ) -> dict:
        return await self._openclaw_ops.push_openclaw_memory(
            project_slug=project_slug, note=note, threads=threads
        )

    def _forge_after_thread(self, thread: Thread) -> dict:
        return self._forge._forge_after_thread(thread)

    def sync_forge_now(self) -> dict:
        return self._forge.sync_forge_now()

    def import_forge_inbox(self, *, limit: int = 50, close_imported: bool = True) -> dict:
        return self._forge.import_forge_inbox(limit=limit, close_imported=close_imported)

    @staticmethod
    def _title_from_progress(content: str | None, slug: str) -> str:
        if content:
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("# "):
                    title = stripped[2:].strip()
                    if title:
                        return title[:120]
        return slug.replace("-", " ").replace("_", " ").title()

    def preview_forge_import(self) -> dict:
        """Compare remote forge projects/* with local registry + wiki."""
        return self._forge.preview_forge_import()

    def import_from_forge(
        self,
        *,
        slugs: list[str] | None = None,
        overwrite_local: bool = False,
    ) -> dict:
        """Register missing projects and pull PROGRESS.md from forge into local wiki."""
        cfg = self.forge_config()
        if not (cfg.enabled() and cfg.wiki_enabled):
            return {"skipped": True, "reason": "wiki_sync_disabled", "imported": []}
        sync = WikiForgeSync(cfg)
        preview = self.preview_forge_import()
        wanted = {s.strip() for s in (slugs or []) if s and s.strip()}
        imported: list[dict] = []
        skipped: list[dict] = []
        errors: list[str] = []
        for cand in preview.get("candidates") or []:
            slug = cand["slug"]
            if wanted and slug not in wanted:
                continue
            if not cand.get("has_remote_progress"):
                skipped.append({"slug": slug, "reason": "no_remote_progress"})
                continue
            if cand["status"] == "registered" and not overwrite_local:
                skipped.append({"slug": slug, "reason": "already_registered"})
                continue
            try:
                content = sync.read_file_text(f"projects/{slug}/PROGRESS.md")
                if content is None:
                    skipped.append({"slug": slug, "reason": "fetch_failed"})
                    continue
                title = self._title_from_progress(content, slug)
                existing = self.store.get_project(slug)
                if not existing:
                    self.upsert_project(
                        ProjectUpsert(
                            slug=slug,
                            title=title,
                            description="Imported from forge",
                        )
                    )
                should_write = overwrite_local or not cand.get("has_local_progress")
                if should_write:
                    self.wiki.write_progress_raw(slug, content)
                imported.append(
                    {
                        "slug": slug,
                        "title": title,
                        "wrote_progress": should_write,
                        "registered": existing is None,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{slug}: {exc}")
        self.wiki.rebuild_index(self.store.list_threads(status=ThreadStatus.open, limit=500))
        # Pull INDEX.md when missing locally
        index_written = False
        local_index = self.settings.wiki_dir / "INDEX.md"
        if overwrite_local or not local_index.is_file():
            remote_index = sync.read_file_text("INDEX.md")
            if remote_index:
                local_index.write_text(remote_index, encoding="utf-8")
                index_written = True
        return {
            "skipped": False,
            "imported": imported,
            "skipped_items": skipped,
            "errors": errors,
            "index_written": index_written,
        }

    def export_backup(self, *, passphrase: str | None = None) -> bytes:
        from adhd_hub.backup import export_data_dir

        return export_data_dir(self.settings.data_dir, passphrase=passphrase)

    def import_backup(
        self, archive: bytes, *, replace: bool = True, passphrase: str | None = None
    ) -> dict:
        from adhd_hub.backup import import_data_dir

        result = import_data_dir(
            self.settings.data_dir, archive, replace=replace, passphrase=passphrase
        )
        # Re-open store against restored sqlite
        self.store = Store(self.settings.db_path)
        self.wiki = Wiki(self.settings.wiki_dir, timezone=self.prefs().timezone)
        # Sessions are outside the backup zip — revoke so cookies cannot outlive a restore.
        try:
            from adhd_hub.sessions import BrowserSessions

            BrowserSessions(self.settings.data_dir / "browser_sessions.sqlite3").clear()
        except OSError:
            pass
        return result

    def record_indexer_run(self, *, upserted: int, candidates: int) -> None:
        from datetime import UTC, datetime

        self.store.set_meta(
            "indexer_last_run",
            {
                "at": datetime.now(UTC).isoformat(),
                "upserted": upserted,
                "candidates": candidates,
            },
        )

    def indexer_last_run(self) -> dict | None:
        raw = self.store.get_meta("indexer_last_run")
        if not raw:
            return None
        if isinstance(raw, dict):
            return raw
        try:
            import json

            data = json.loads(raw)
            return data if isinstance(data, dict) else {"raw": raw}
        except (TypeError, json.JSONDecodeError):
            return {"raw": str(raw)}

    def upsert_thread(self, payload: ThreadUpsert) -> Thread:
        slug = self._resolve_slug_for_write(
            project_slug=payload.project_slug,
            workspace_path=payload.workspace_path,
            summary_or_title=payload.summary,
        )
        payload = payload.model_copy(update={"project_slug": slug})
        self.store.ensure_project_for_slug(
            slug, title=payload.summary[:80], workspace_path=payload.workspace_path
        )
        thread = self.store.upsert_thread(payload)
        self.wiki.upsert_progress(
            thread.project_slug or slugify(thread.summary),
            content=f"Thread upserted from {thread.source_tool or thread.origin}: {thread.summary}",
            title=thread.summary,
            thread=thread,
        )
        self.wiki.rebuild_index(self.store.list_threads(status=ThreadStatus.open, limit=500))
        self._forge_after_thread(thread)
        return thread

    def list_open_threads(
        self,
        *,
        energy: EnergyLevel | None = None,
        project_slug: str | None = None,
        limit: int = 100,
    ) -> list[Thread]:
        return self.store.list_threads(
            status=ThreadStatus.open,
            energy=energy,
            project_slug=project_slug,
            limit=limit,
        )

    def list_stale_threads(self) -> list[Thread]:
        cutoff = stale_cutoff(self.settings.stale_days)
        remind_cut = stale_cutoff(self.settings.remind_cooldown_days)
        return [
            t
            for t in self.list_open_threads(limit=500)
            if t.updated_at.replace(tzinfo=UTC) <= cutoff
            and (t.last_reminded_at is None or t.last_reminded_at.replace(tzinfo=UTC) <= remind_cut)
        ]

    def check_overlap(self, query: str, limit: int | None = None) -> OverlapResult:
        threads = self.list_open_threads(limit=500)
        return check_overlap(
            query,
            threads,
            limit=limit or self.settings.overlap_limit,
        )

    def upsert_progress(self, payload: ProgressUpsert) -> dict:
        if not payload.project_slug and not payload.workspace_path:
            raise ValueError("project_slug or workspace_path required")
        slug = self._resolve_slug_for_write(
            project_slug=payload.project_slug,
            workspace_path=payload.workspace_path,
            summary_or_title=payload.title,
        )
        self.store.ensure_project_for_slug(
            slug, title=payload.title, workspace_path=payload.workspace_path
        )
        thread = None
        if payload.create_thread_if_missing:
            existing = [
                t
                for t in self.store.list_threads(status=None, project_slug=slug, limit=20)
                if t.status in (ThreadStatus.open, ThreadStatus.blocked)
            ]
            if existing:
                thread = existing[0]
                thread = self.store.upsert_thread(
                    ThreadUpsert(
                        id=thread.id,
                        summary=thread.summary,
                        status=thread.status,
                        energy=thread.energy,
                        source_tool=payload.source_tool or thread.source_tool,
                        workspace_path=payload.workspace_path or thread.workspace_path,
                        project_slug=slug,
                        origin=thread.origin,
                    )
                )
            else:
                title = payload.title or f"In progress: {slug}"
                thread = self.store.upsert_thread(
                    ThreadUpsert(
                        summary=title,
                        status=ThreadStatus.open,
                        source_tool=payload.source_tool,
                        workspace_path=payload.workspace_path,
                        project_slug=slug,
                        origin="progress",
                    )
                )
        path = self.wiki.upsert_progress(
            slug,
            payload.content,
            title=payload.title,
            thread=thread,
        )
        self.store.add_progress_note(slug, payload.content)
        self.wiki.rebuild_index(self.store.list_threads(status=ThreadStatus.open, limit=500))
        forge = {}
        if thread:
            forge = self._forge_after_thread(thread)
        else:
            try:
                forge["wiki"] = WikiForgeSync(self.forge_config(slug)).push_wiki_tree(
                    self.settings.wiki_dir
                )
            except Exception as exc:  # noqa: BLE001
                forge["wiki"] = {"error": str(exc)}
        return {
            "project_slug": slug,
            "progress_path": str(path),
            "thread_id": thread.id if thread else None,
            "forge": forge,
        }

    def mark_done(self, thread_id: str, note: str | None = None) -> Thread | None:
        thread, changed = self.store.transition_status(thread_id, ThreadStatus.done, note=note)
        if thread and changed:
            self.wiki.upsert_progress(
                thread.project_slug or slugify(thread.summary),
                content=note or "Marked done.",
                title=thread.summary,
                thread=thread,
            )
            self.wiki.rebuild_index(self.store.list_threads(status=ThreadStatus.open, limit=500))
            self._forge_after_thread(thread)
        return thread

    def mark_dismissed(self, thread_id: str, note: str | None = None) -> Thread | None:
        thread, changed = self.store.transition_status(thread_id, ThreadStatus.dismissed, note=note)
        if thread and changed:
            self.wiki.rebuild_index(self.store.list_threads(status=ThreadStatus.open, limit=500))
            self._forge_after_thread(thread)
        return thread

    def set_reminder(self, payload: ReminderCreate) -> Reminder:
        return self.store.create_reminder(payload)

    def snooze_reminder(self, reminder_id: str, *, minutes: int = 60) -> Reminder:
        return self.store.snooze_reminder(reminder_id, minutes=minutes)

    def dismiss_reminder(self, reminder_id: str) -> Reminder:
        return self.store.dismiss_reminder(reminder_id)

    def _anti_nag_filter(self, threads: list[Thread]) -> list[Thread]:
        remind_cut = stale_cutoff(self.settings.remind_cooldown_days)
        filtered = [
            t
            for t in threads
            if t.last_reminded_at is None or t.last_reminded_at.replace(tzinfo=UTC) <= remind_cut
        ]
        return filtered[: self.settings.digest_max_nudge]

    def session_digest(
        self,
        *,
        workspace_path: str | None = None,
        query: str | None = None,
        energy: EnergyLevel | None = None,
    ) -> SessionDigest:
        project = self.resolve_project(workspace_path=workspace_path, create_if_missing=False)
        project_slug = project.slug if project else None
        open_threads = self.list_open_threads(energy=energy, project_slug=project_slug, limit=200)
        if not open_threads and project_slug:
            # Fall back to all opens if project has none
            open_threads = self.list_open_threads(energy=energy, limit=200)
        stale = [
            t
            for t in open_threads
            if t.updated_at.replace(tzinfo=UTC) <= stale_cutoff(self.settings.stale_days)
        ]
        ranked = open_threads
        if query or workspace_path:
            q = " ".join(filter(None, [query, workspace_path]))
            hits = check_overlap(q, open_threads, limit=self.settings.digest_limit).hits
            if hits:
                ranked = [h.thread for h in hits]
            else:
                ranked = sorted(open_threads, key=lambda t: t.updated_at)[
                    : self.settings.digest_limit
                ]
        else:
            ranked = sorted(
                open_threads,
                key=lambda t: (
                    0 if t in stale else 1,
                    t.updated_at,
                ),
            )[: self.settings.digest_limit]

        # Prefer stale for nudges, apply cooldown + max
        nudge_pool = [t for t in ranked if t in stale] or ranked
        nudged = self._anti_nag_filter(nudge_pool)
        self.store.touch_reminded([t.id for t in nudged])

        due = self.store.due_reminders()
        filtered: list[Reminder] = []
        for rem in due:
            if rem.kind == ReminderKind.random and random.random() > 0.15:
                continue
            filtered.append(rem)
            if rem.kind != ReminderKind.session:
                self.store.mark_reminder_fired(rem.id)

        if not self.wiki.index_snippet():
            self.wiki.rebuild_index(open_threads)

        return SessionDigest(
            open_count=len(open_threads),
            stale_count=len(stale),
            items=nudged or ranked[: self.settings.digest_limit],
            due_reminders=filtered[:10],
            wiki_index_snippet=self.wiki.index_snippet(),
        )

    def rebuild_wiki_index(self) -> str:
        path = self.wiki.rebuild_index(self.store.list_threads(status=ThreadStatus.open, limit=500))
        return str(path)

    async def run_stale_nudge(self) -> dict:
        return await self._openclaw_ops.run_stale_nudge()

    def health(self) -> dict:
        from adhd_hub import __version__

        overview = self.overview()
        return {
            "status": "ok",
            "version": __version__,
            "open_threads": overview["open"],
            "stale_threads": overview["stale"],
            "done_threads": overview["done"],
            "projects": len(overview["projects"]),
            "wiki_projects": len(self.wiki.list_project_slugs()),
            "indexer_last_run": self.indexer_last_run(),
        }
