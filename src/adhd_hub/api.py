from __future__ import annotations

import zipfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import ValidationError

from adhd_hub.models import (
    EnergyLevel,
    IndexerBatch,
    MarkDoneRequest,
    PauseRequest,
    ProgressUpsert,
    ProjectRename,
    ProjectUpsert,
    ReminderCreate,
    ThreadStatus,
    ThreadUpsert,
)
from adhd_hub.openclaw_config import OpenClawConfig
from adhd_hub.service import HubService


def build_router(service: HubService, auth_dep) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health():
        return service.health()

    @router.get("/threads", dependencies=[Depends(auth_dep)])
    def list_threads(
        status: ThreadStatus | None = ThreadStatus.open,
        energy: EnergyLevel | None = None,
        project_slug: str | None = None,
        limit: int = Query(100, ge=1, le=500),
        stale: bool = False,
    ):
        return service.list_threads_public(
            status=status,
            energy=energy,
            project_slug=project_slug,
            limit=limit,
            stale=stale,
        )

    @router.get("/threads/{thread_id}", dependencies=[Depends(auth_dep)])
    def get_thread(thread_id: str):
        from adhd_hub.markdown import render_markdown

        thread = service.store.get_thread(thread_id)
        if not thread:
            raise HTTPException(404, "Thread not found")
        data = service.thread_public_dict(thread)
        progress = service.wiki.read_progress(thread.project_slug) if thread.project_slug else None
        data["progress_html"] = render_markdown(progress or "")
        data["resume_step_html"] = render_markdown(thread.resume_step or "")
        return data

    @router.post("/threads/{thread_id}/pause", dependencies=[Depends(auth_dep)])
    def pause_thread(thread_id: str, payload: PauseRequest):
        try:
            thread = service.store.pause_thread(thread_id, payload.next_step)
        except KeyError:
            raise HTTPException(404, "Thread not found") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return service.thread_public_dict(thread)

    @router.get("/overview", dependencies=[Depends(auth_dep)])
    def overview():
        return service.overview()

    @router.get("/prefs", dependencies=[Depends(auth_dep)])
    def get_prefs():
        return service.prefs().public_dict()

    @router.put("/prefs", dependencies=[Depends(auth_dep)])
    def put_prefs(payload: dict):
        from adhd_hub.prefs import HubPrefs
        from adhd_hub.timeutil import validate_timezone

        current = service.prefs().model_dump()
        current.update({k: v for k, v in payload.items() if v is not None})
        try:
            current["timezone"] = validate_timezone(str(current.get("timezone") or "UTC"))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return service.save_prefs(HubPrefs.model_validate(current)).public_dict()

    @router.get("/projects", dependencies=[Depends(auth_dep)])
    def list_projects(limit: int = Query(200, ge=1, le=500)):
        return service.list_projects(limit=limit)

    @router.post("/projects", dependencies=[Depends(auth_dep)])
    def upsert_project(payload: ProjectUpsert):
        return service.upsert_project(payload)

    @router.get("/projects/resolve", dependencies=[Depends(auth_dep)])
    def resolve_project(
        workspace_path: str | None = None,
        project_slug: str | None = None,
        create: bool = False,
    ):
        proj = service.resolve_project(
            workspace_path=workspace_path,
            project_slug=project_slug,
            create_if_missing=create,
        )
        if not proj:
            raise HTTPException(404, "Project not found")
        return proj

    @router.get("/projects/{slug}", dependencies=[Depends(auth_dep)])
    def get_project(slug: str):
        detail = service.get_project_detail(slug)
        if not detail:
            raise HTTPException(404, "Project not found")
        return detail

    @router.post("/projects/{slug}/rename", dependencies=[Depends(auth_dep)])
    def rename_project(slug: str, payload: ProjectRename):
        try:
            return service.rename_project(
                slug, payload.new_slug, title=payload.title
            )
        except KeyError:
            raise HTTPException(404, "Project not found") from None
        except ValueError as exc:
            if str(exc) == "conflict":
                raise HTTPException(409, "Target slug already exists") from exc
            raise HTTPException(400, str(exc)) from exc
        except FileExistsError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.delete("/projects/{slug}", dependencies=[Depends(auth_dep)])
    def delete_project(
        slug: str,
        delete_progress: bool = False,
        delete_remote: bool = False,
    ):
        try:
            return service.delete_project(
                slug,
                delete_progress=delete_progress,
                delete_remote=delete_remote,
            )
        except KeyError:
            raise HTTPException(404, "Project not found") from None

    @router.get("/pending-actions", dependencies=[Depends(auth_dep)])
    def list_pending_actions():
        return service.list_pending_actions()

    @router.post("/pending-actions/{action_id}/approve", dependencies=[Depends(auth_dep)])
    def approve_pending(action_id: str):
        try:
            return service.approve_pending_action(action_id)
        except KeyError:
            raise HTTPException(404, "Pending action not found") from None
        except ValueError as exc:
            if str(exc) == "conflict":
                raise HTTPException(409, "Target slug already exists") from exc
            raise HTTPException(400, str(exc)) from exc

    @router.post("/pending-actions/{action_id}/reject", dependencies=[Depends(auth_dep)])
    def reject_pending(action_id: str):
        try:
            return service.reject_pending_action(action_id)
        except KeyError:
            raise HTTPException(404, "Pending action not found") from None

    @router.post("/threads", dependencies=[Depends(auth_dep)])
    def upsert_thread(payload: ThreadUpsert):
        return service.upsert_thread(payload)

    @router.post("/threads/mark-done", dependencies=[Depends(auth_dep)])
    def mark_done(payload: MarkDoneRequest):
        thread = service.mark_done(payload.id, payload.note)
        if not thread:
            raise HTTPException(404, "Thread not found")
        return thread

    @router.post("/threads/dismiss", dependencies=[Depends(auth_dep)])
    def dismiss(payload: MarkDoneRequest):
        thread = service.mark_dismissed(payload.id, payload.note)
        if not thread:
            raise HTTPException(404, "Thread not found")
        return thread

    @router.get("/overlap", dependencies=[Depends(auth_dep)])
    def overlap(q: str = Query(..., min_length=2), limit: int | None = None):
        return service.check_overlap(q, limit=limit)

    @router.post("/progress", dependencies=[Depends(auth_dep)])
    def progress(payload: ProgressUpsert):
        try:
            return service.upsert_progress(payload)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/digest", dependencies=[Depends(auth_dep)])
    def digest(
        workspace_path: str | None = None,
        q: str | None = None,
        energy: EnergyLevel | None = None,
    ):
        return service.session_digest(
            workspace_path=workspace_path, query=q, energy=energy
        )

    @router.post("/reminders", dependencies=[Depends(auth_dep)])
    def create_reminder(payload: ReminderCreate):
        return service.set_reminder(payload)

    @router.get("/reminders", dependencies=[Depends(auth_dep)])
    def list_reminders(include_handled: bool = False):
        return service.store.list_reminders(include_handled=include_handled)

    @router.post("/indexer/batch", dependencies=[Depends(auth_dep)])
    def indexer_batch(payload: IndexerBatch):
        created = []
        for item in payload.items:
            t = service.upsert_thread(
                ThreadUpsert(
                    summary=item.summary,
                    source_tool=item.source_tool,
                    workspace_path=item.workspace_path,
                    project_slug=item.project_slug,
                    transcript_ref=item.transcript_ref,
                    origin=item.origin,
                    energy=item.energy,
                )
            )
            created.append(t)
        return {"upserted": len(created), "items": created}

    @router.post("/admin/rebuild-wiki", dependencies=[Depends(auth_dep)])
    def rebuild_wiki():
        return {"path": service.rebuild_wiki_index()}

    @router.post("/admin/stale-nudge", dependencies=[Depends(auth_dep)])
    async def stale_nudge():
        return await service.run_stale_nudge()

    @router.get("/openclaw/config", dependencies=[Depends(auth_dep)])
    def get_openclaw_config():
        return service.openclaw_config().public_dict()

    @router.put("/openclaw/config", dependencies=[Depends(auth_dep)])
    def put_openclaw_config(payload: dict):
        current = service.openclaw_config()
        data = current.model_dump()
        supplied_token = payload.pop("token", None)
        clear_token = bool(payload.pop("clear_token", False))
        endpoint_changed = any(
            key in payload
            and str(payload[key] or "").strip().rstrip("/") != getattr(current, key)
            for key in ("webhook_url", "agent_url")
        )
        data.update({k: v for k, v in payload.items() if v is not None})
        if clear_token:
            data["token"] = ""
        elif isinstance(supplied_token, str) and supplied_token.strip():
            data["token"] = supplied_token.strip()
        elif endpoint_changed:
            # Never send a previously saved bearer token to a newly supplied host.
            data["token"] = ""
        try:
            config = OpenClawConfig.model_validate(data)
        except ValidationError as exc:
            detail = "; ".join(
                str(error.get("msg", "Invalid OpenClaw setting")).removeprefix("Value error, ")
                for error in exc.errors(include_input=False)
            )
            raise HTTPException(400, detail) from exc
        return service.save_openclaw_config(config).public_dict()

    @router.post("/openclaw/test", dependencies=[Depends(auth_dep)])
    async def test_openclaw_connection():
        result = await service.test_openclaw_connection()
        if not result["ok"]:
            raise HTTPException(502, str(result["message"]))
        return result

    @router.get("/wiki/{slug}/progress", dependencies=[Depends(auth_dep)])
    def read_progress(slug: str):
        text = service.wiki.read_progress(slug)
        if text is None:
            raise HTTPException(404, "Progress doc not found")
        return {"slug": slug, "content": text}

    @router.get("/forge/config", dependencies=[Depends(auth_dep)])
    def get_forge_config():
        return service.forge_config().public_dict()

    @router.put("/forge/config", dependencies=[Depends(auth_dep)])
    def put_forge_config(payload: dict):
        from adhd_hub.forge.config import ForgeConfig

        current = service.forge_config()
        data = current.model_dump()
        data.update(payload)
        if isinstance(data.get("token"), str) and data["token"].startswith("***"):
            data["token"] = current.token
        cfg = ForgeConfig.model_validate(data)
        service.save_forge_config(cfg)
        return cfg.public_dict()

    @router.post("/forge/sync", dependencies=[Depends(auth_dep)])
    def forge_sync():
        return service.sync_forge_now()

    @router.get("/forge/import/preview", dependencies=[Depends(auth_dep)])
    def forge_import_preview():
        return service.preview_forge_import()

    @router.post("/forge/import", dependencies=[Depends(auth_dep)])
    def forge_import(payload: dict | None = None):
        body = payload or {}
        slugs = body.get("slugs")
        if slugs is not None and not isinstance(slugs, list):
            raise HTTPException(400, "slugs must be a list of strings")
        return service.import_from_forge(
            slugs=slugs,
            overwrite_local=bool(body.get("overwrite_local")),
        )

    @router.get("/admin/export", dependencies=[Depends(auth_dep)])
    def admin_export():
        from fastapi.responses import Response

        data = service.export_backup()
        return Response(
            content=data,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="adhd-hub-backup.zip"'
            },
        )

    @router.post("/admin/import", dependencies=[Depends(auth_dep)])
    async def admin_import(
        file: Annotated[UploadFile, File()],
        replace: bool = True,
    ):
        raw = await file.read()
        if not raw:
            raise HTTPException(400, "empty archive")
        # Keep restores bounded (wiki trees + sqlite); raise if you need larger.
        if len(raw) > 80 * 1024 * 1024:
            raise HTTPException(400, "archive too large (max 80 MiB)")
        try:
            return service.import_backup(raw, replace=replace)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except zipfile.BadZipFile as exc:
            raise HTTPException(400, "not a valid zip archive") from exc

    return router
