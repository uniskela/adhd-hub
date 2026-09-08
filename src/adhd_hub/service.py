from __future__ import annotations

import logging
import random
from datetime import UTC

from adhd_hub.config import Settings
from adhd_hub.forge import (
    BoardForgeSync,
    WikiForgeSync,
    forge_from_settings,
    load_forge_config,
    save_forge_config,
)
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
from adhd_hub.openclaw import OpenClawBridge, stale_cutoff
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
        self.openclaw = OpenClawBridge(settings)

    def prefs(self) -> HubPrefs:
        return self._prefs

    def save_prefs(self, prefs: HubPrefs) -> HubPrefs:
        self._prefs = prefs
        save_prefs(self.settings.data_dir, prefs)
        self.wiki.set_timezone(prefs.timezone)
        return prefs

    def forge_config(self, project_slug: str | None = None) -> ForgeConfig:
        base = load_forge_config(
            self.settings.data_dir, env_defaults=forge_from_settings(self.settings)
        )
        data = base.model_dump()
        # Primary memory repos mirror at repo root (projects/<slug>/…)
        if data.get("primary_memory_repo") and str(data.get("wiki_path") or "").strip(
            "/"
        ) in ("", "adhd-hub/wiki"):
            data["wiki_path"] = ""
        if not project_slug:
            return ForgeConfig.model_validate(data)
        proj = self.store.get_project(project_slug)
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
        save_forge_config(self.settings.data_dir, config)
        return config

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

    def rename_project(
        self, old_slug: str, new_slug: str, *, title: str | None = None
    ) -> dict:
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
                f"Delete of `{safe}` needs confirmation in /ui "
                "(Pending actions). Not deleted yet."
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
            "message": (
                f"Rename `{old}` → `{new}` needs confirmation in /ui. Not renamed yet."
            ),
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
        resolved = self.store.resolve_pending_action(
            action_id, PendingActionStatus.approved
        )
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
        resolved = self.store.resolve_pending_action(
            action_id, PendingActionStatus.rejected
        )
        return {
            "rejected": True,
            "action": resolved.model_dump(mode="json") if resolved else None,
        }

    def _refresh_forge_section(self, slug: str) -> None:
        cfg = self.forge_config(slug)
        progress_url = cfg.file_web_url(f"projects/{slug}/PROGRESS.md")
        issue_links: list[tuple[str, str]] = []
        for t in self.store.list_threads(status=ThreadStatus.open, project_slug=slug, limit=50):
            pub = self.thread_public_dict(t)
            url = pub.get("forge_issue_url")
            num = pub.get("forge_issue_number")
            if url and num:
                issue_links.append((f"#{num} {t.summary[:60]}", url))
        self.wiki.ensure_forge_section(
            slug, progress_url=progress_url, issue_links=issue_links
        )

    def list_projects(self, limit: int = 200) -> list[dict]:
        counts = self.store.thread_counts_by_project()
        out = []
        for p in self.store.list_projects(limit=limit):
            data = p.model_dump(mode="json")
            c = counts.get(p.slug, {"open": 0, "blocked": 0, "done": 0, "dismissed": 0})
            data["counts"] = c
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
                        "workspace_paths": [],
                        "default_energy": "unknown",
                        "forge_owner": None,
                        "forge_repo": None,
                        "forge_wiki_path": None,
                        "forge_project_id": None,
                        "counts": c,
                        "unregistered": True,
                    }
                )
        return out

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
        done = self.store.list_threads(status=ThreadStatus.done, limit=500)
        blocked = self.store.list_threads(status=ThreadStatus.blocked, limit=100)
        stats = self.store.done_counts()
        return {
            "open": len(open_threads),
            "stale": len(stale),
            "done": len(done),
            "blocked": len(blocked),
            "stale_days": self.settings.stale_days,
            "done_today": stats["done_today"],
            "done_week": stats["done_week"],
            "day_streak": stats["day_streak"],
            "added_vs_finished": self.store.analytics_added_done(14),
            "projects": self.list_projects(),
            "timezone": self.prefs().timezone,
            "pending_actions": self.list_pending_actions(),
        }

    def _forge_after_thread(self, thread: Thread) -> dict:
        cfg = self.forge_config(thread.project_slug)
        out: dict = {}
        try:
            out["board"] = BoardForgeSync(
                cfg,
                self.store.get_meta,
                self.store.set_meta,
                progress_reader=self.wiki.read_progress,
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
            out["wiki"] = WikiForgeSync(cfg).push_wiki_tree(self.settings.wiki_dir)
        except Exception as exc:
            log.exception("wiki sync failed")
            out["wiki"] = {"error": str(exc)}
        return out

    def sync_forge_now(self) -> dict:
        cfg = self.forge_config()
        from adhd_hub.forge.scaffold import push_primary_scaffold

        scaffold = push_primary_scaffold(
            cfg, hub_ui_url=self.settings.resolve_public_url()
        )
        wiki = WikiForgeSync(cfg).push_wiki_tree(self.settings.wiki_dir)
        board_results = []
        for thread in self.list_open_threads(limit=200):
            try:
                tcfg = self.forge_config(thread.project_slug)
                board = BoardForgeSync(
                    tcfg,
                    self.store.get_meta,
                    self.store.set_meta,
                    progress_reader=self.wiki.read_progress,
                )
                board_results.append(board.sync_thread(thread))
            except Exception as exc:  # noqa: BLE001 — continue syncing other threads
                board_results.append({"error": str(exc), "thread_id": thread.id})
        # Also push per-project forge wiki overrides (distinct owner/repo)
        per_project_wiki: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for proj in self.store.list_projects():
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
                            self.settings.wiki_dir
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
        }

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
            and (
                t.last_reminded_at is None
                or t.last_reminded_at.replace(tzinfo=UTC) <= remind_cut
            )
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
        thread = self.store.mark_status(thread_id, ThreadStatus.done, note=note)
        if thread:
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
        thread = self.store.mark_status(thread_id, ThreadStatus.dismissed, note=note)
        if thread:
            self.wiki.rebuild_index(self.store.list_threads(status=ThreadStatus.open, limit=500))
            self._forge_after_thread(thread)
        return thread

    def set_reminder(self, payload: ReminderCreate) -> Reminder:
        return self.store.create_reminder(payload)

    def _anti_nag_filter(self, threads: list[Thread]) -> list[Thread]:
        remind_cut = stale_cutoff(self.settings.remind_cooldown_days)
        filtered = [
            t
            for t in threads
            if t.last_reminded_at is None
            or t.last_reminded_at.replace(tzinfo=UTC) <= remind_cut
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
        open_threads = self.list_open_threads(
            energy=energy, project_slug=project_slug, limit=200
        )
        if not open_threads and project_slug:
            # Fall back to all opens if project has none
            open_threads = self.list_open_threads(energy=energy, limit=200)
        stale = [
            t
            for t in open_threads
            if t.updated_at.replace(tzinfo=UTC)
            <= stale_cutoff(self.settings.stale_days)
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
        stale = self.list_stale_threads()
        if not stale:
            return {"nudged": 0, "openclaw": False}
        limited = stale[: self.settings.digest_max_nudge]
        lines = [
            f"{t.summary} [{t.project_slug or '-'}] (id={t.id}, updated={t.updated_at.date()})"
            for t in limited
        ]
        sent = await self.openclaw.notify_stale_threads(lines)
        self.store.touch_reminded([t.id for t in limited])
        self.rebuild_wiki_index()
        if sent:
            await self.openclaw.sync_memory_note(
                "ADHD Hub open work",
                "\n".join(lines),
            )
        return {"nudged": len(lines), "openclaw": sent}

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
        }
