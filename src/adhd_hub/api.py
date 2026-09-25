from __future__ import annotations

import zipfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import ValidationError

from adhd_hub.ai_config import AiConfig
from adhd_hub.models import (
    EnergyLevel,
    IndexerBatch,
    MarkDoneRequest,
    OrganiseApplyRequest,
    PauseRequest,
    ProgressUpsert,
    ProjectMove,
    ProjectRename,
    ProjectUpsert,
    ReminderCreate,
    ReminderSnooze,
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
        data["progress_html"] = service.thread_notes_context_html(thread)
        data["resume_step_html"] = render_markdown(thread.resume_step or "")
        data.update(service.notes_summary_status(thread))
        return data

    @router.get("/threads/{thread_id}/source-refresh", dependencies=[Depends(auth_dep)])
    def preview_thread_source_refresh(thread_id: str):
        try:
            return service.refresh_thread_from_source(thread_id, preview_only=True)
        except KeyError:
            raise HTTPException(404, "Thread not found") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/threads/{thread_id}/source-refresh", dependencies=[Depends(auth_dep)])
    def apply_thread_source_refresh(thread_id: str, payload: dict | None = None):
        body = payload or {}
        resolutions = body.get("resolutions") or {}
        manual_values = body.get("manual_values") or {}
        if not isinstance(resolutions, dict) or not isinstance(manual_values, dict):
            raise HTTPException(400, "resolutions and manual_values must be objects")
        allowed_actions = {"forge", "hub", "manual"}
        if any(action not in allowed_actions for action in resolutions.values()):
            raise HTTPException(400, "resolution must be forge, hub, or manual")
        try:
            return service.refresh_thread_from_source(
                thread_id,
                resolutions={str(k): str(v) for k, v in resolutions.items()},
                manual_values={str(k): v for k, v in manual_values.items()},
            )
        except KeyError:
            raise HTTPException(404, "Thread not found") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/threads/{thread_id}/pause", dependencies=[Depends(auth_dep)])
    def pause_thread(thread_id: str, payload: PauseRequest):
        try:
            thread = service.pause_thread(thread_id, payload.next_step)
        except KeyError:
            raise HTTPException(404, "Thread not found") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return service.thread_public_dict(thread)

    @router.post("/threads/{thread_id}/scan-line", dependencies=[Depends(auth_dep)])
    def rewrite_thread_scan_line(thread_id: str, payload: dict | None = None):
        """AI scan-line rewrite. Default force; ``{\"mode\":\"ensure\"}`` hash-skips when fresh."""
        body = payload or {}
        mode = str(body.get("mode") or "force").strip().lower()
        force = mode != "ensure"
        try:
            return service.rewrite_scan_line(thread_id, force=force)
        except KeyError:
            raise HTTPException(404, "Thread not found") from None

    @router.post("/threads/{thread_id}/notes-summary", dependencies=[Depends(auth_dep)])
    def summarise_thread_notes(thread_id: str, payload: dict | None = None):
        """AI Notes summarise card. Default force; ``{\"mode\":\"ensure\"}`` hash-skips when fresh."""
        body = payload or {}
        mode = str(body.get("mode") or "force").strip().lower()
        force = mode != "ensure"
        try:
            return service.summarise_notes(thread_id, force=force)
        except KeyError:
            raise HTTPException(404, "Thread not found") from None

    @router.post("/projects/{slug}/scan-lines", dependencies=[Depends(auth_dep)])
    def rewrite_project_scan_lines(slug: str):
        """Rewrite scan lines for all open threads in a project (sequential, rate-limited)."""
        from adhd_hub.service import ProjectRewriteInProgress

        try:
            return service.rewrite_project_scan_lines(slug)
        except ProjectRewriteInProgress as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/overview", dependencies=[Depends(auth_dep)])
    def overview():
        return service.overview()

    @router.get("/prefs", dependencies=[Depends(auth_dep)])
    def get_prefs():
        return service.prefs().public_dict()

    @router.put("/prefs", dependencies=[Depends(auth_dep)])
    def put_prefs(payload: dict):
        from adhd_hub.prefs import HubPrefs
        from adhd_hub.project_setup import CONNECT_AGENT_CHOICES
        from adhd_hub.timeutil import validate_timezone

        current = service.prefs().model_dump()
        current.update({k: v for k, v in payload.items() if v is not None})
        try:
            current["timezone"] = validate_timezone(str(current.get("timezone") or "UTC"))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if "connect_agents" in payload:
            raw = payload.get("connect_agents")
            if raw is None:
                current["connect_agents"] = []
            elif not isinstance(raw, list):
                raise HTTPException(400, "connect_agents must be a list of agent ids")
            else:
                allowed = set(CONNECT_AGENT_CHOICES)
                cleaned: list[str] = []
                for item in raw:
                    key = str(item).strip().lower()
                    if not key:
                        continue
                    if key not in allowed:
                        raise HTTPException(
                            400,
                            f"Unknown connect agent {key!r}; "
                            f"allowed: {', '.join(CONNECT_AGENT_CHOICES)}",
                        )
                    if key not in cleaned:
                        cleaned.append(key)
                current["connect_agents"] = cleaned
        if "connect_companions" in payload:
            raw_c = payload.get("connect_companions")
            if raw_c is None:
                current["connect_companions"] = []
            elif not isinstance(raw_c, list):
                raise HTTPException(400, "connect_companions must be a list of companion ids")
            else:
                from adhd_hub.prefs import CONNECT_COMPANION_CHOICES

                allowed_c = set(CONNECT_COMPANION_CHOICES)
                cleaned_c: list[str] = []
                for item in raw_c:
                    key = str(item).strip().lower()
                    if not key:
                        continue
                    if key not in allowed_c:
                        raise HTTPException(
                            400,
                            f"Unknown connect companion {key!r}; "
                            f"allowed: {', '.join(CONNECT_COMPANION_CHOICES)}",
                        )
                    if key not in cleaned_c:
                        cleaned_c.append(key)
                current["connect_companions"] = cleaned_c
        return service.save_prefs(HubPrefs.model_validate(current)).public_dict()

    @router.get("/projects", dependencies=[Depends(auth_dep)])
    def list_projects(
        limit: int = Query(200, ge=1, le=500),
        include_archived: bool = False,
    ):
        return service.list_projects(limit=limit, include_archived=include_archived)

    @router.post("/projects", dependencies=[Depends(auth_dep)])
    def upsert_project(payload: ProjectUpsert):
        try:
            return service.upsert_project(payload)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

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

    @router.get("/projects/organise/suggestions", dependencies=[Depends(auth_dep)])
    def organise_suggestions(limit: int = Query(50, ge=1, le=200)):
        return service.suggest_project_organisation(limit=limit)

    @router.post("/projects/organise/apply", dependencies=[Depends(auth_dep)])
    def organise_apply(payload: OrganiseApplyRequest):
        return service.apply_project_organisation(payload)

    @router.get("/projects/{slug}", dependencies=[Depends(auth_dep)])
    def get_project(slug: str):
        detail = service.get_project_detail(slug)
        if not detail:
            raise HTTPException(404, "Project not found")
        return detail

    @router.post("/projects/{slug}/move", dependencies=[Depends(auth_dep)])
    def move_project(slug: str, payload: ProjectMove):
        try:
            return service.move_project(slug, payload)
        except KeyError:
            raise HTTPException(404, "Project not found") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

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

    @router.post("/projects/{slug}/archive", dependencies=[Depends(auth_dep)])
    def archive_project(slug: str):
        try:
            return service.archive_project(slug)
        except KeyError:
            raise HTTPException(404, "Project not found") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/projects/{slug}/restore", dependencies=[Depends(auth_dep)])
    def restore_project(slug: str):
        try:
            return service.restore_project(slug)
        except KeyError:
            raise HTTPException(404, "Project not found") from None

    @router.post("/projects/{slug}/forge/sync", dependencies=[Depends(auth_dep)])
    def sync_project_forge(slug: str):
        if not service.store.get_project(slug):
            raise HTTPException(404, "Project not found")
        return service.enqueue_forge_job("project_sync", project_slug=slug)

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
        try:
            return service.upsert_thread(payload)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/threads/mark-done", dependencies=[Depends(auth_dep)])
    def mark_done(payload: MarkDoneRequest):
        try:
            thread = service.mark_done(payload.id, payload.note)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
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
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
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

    @router.post("/guidance/verify", dependencies=[Depends(auth_dep)])
    def guidance_verify(payload: dict):
        try:
            return service.record_guidance_verification(
                project_slug=payload.get("project_slug"),
                workspace_path=payload.get("workspace_path"),
                agent_guidance_version=payload.get("agent_guidance_version"),
                session_skill_version=payload.get("session_skill_version"),
                cursor_rule_version=payload.get("cursor_rule_version"),
                source=str(payload.get("source") or "api"),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/reminders", dependencies=[Depends(auth_dep)])
    def create_reminder(payload: ReminderCreate):
        return service.set_reminder(payload)

    @router.get("/reminders", dependencies=[Depends(auth_dep)])
    def list_reminders(include_handled: bool = False, due_only: bool = False):
        if due_only:
            return service.store.due_reminders()
        return service.store.list_reminders(include_handled=include_handled)

    @router.post("/reminders/{reminder_id}/snooze", dependencies=[Depends(auth_dep)])
    def snooze_reminder(reminder_id: str, payload: ReminderSnooze | None = None):
        minutes = payload.minutes if payload else 60
        try:
            return service.snooze_reminder(reminder_id, minutes=minutes)
        except KeyError:
            raise HTTPException(404, "Reminder not found") from None

    @router.post("/reminders/{reminder_id}/dismiss", dependencies=[Depends(auth_dep)])
    def dismiss_reminder(reminder_id: str):
        try:
            return service.dismiss_reminder(reminder_id)
        except KeyError:
            raise HTTPException(404, "Reminder not found") from None

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
        service.record_indexer_run(upserted=len(created), candidates=len(payload.items))
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

    @router.get("/ai/config", dependencies=[Depends(auth_dep)])
    def get_ai_config():
        return service.ai_config().public_dict()

    @router.put("/ai/config", dependencies=[Depends(auth_dep)])
    def put_ai_config(payload: dict):
        current = service.ai_config()
        data = current.model_dump()
        supplied_key = payload.pop("api_key", None)
        clear_key = bool(payload.pop("clear_api_key", False))
        url_changed = (
            "base_url" in payload
            and str(payload.get("base_url") or "").strip().rstrip("/") != current.base_url
        )
        data.update({k: v for k, v in payload.items() if v is not None})
        if clear_key:
            data["api_key"] = ""
        elif isinstance(supplied_key, str) and supplied_key.strip():
            data["api_key"] = supplied_key.strip()
        elif url_changed:
            # Never send a previously saved key to a newly supplied host.
            data["api_key"] = ""
        try:
            config = AiConfig.model_validate(data)
        except ValidationError as exc:
            detail = "; ".join(
                str(error.get("msg", "Invalid AI setting")).removeprefix("Value error, ")
                for error in exc.errors(include_input=False)
            )
            raise HTTPException(400, detail) from exc
        if config.enabled and not config.base_url:
            raise HTTPException(
                400, "add an AI base URL before enabling AI scan-lines"
            )
        return service.save_ai_config(config).public_dict()

    @router.post("/ai/models", dependencies=[Depends(auth_dep)])
    def post_ai_models(payload: dict | None = None):
        """Draft-friendly GET {base}/models — does not persist settings."""
        from adhd_hub.ai_client import list_ai_models

        body = payload or {}
        current = service.ai_config()
        base_url = str(body.get("base_url") or current.base_url or "").strip()
        if not base_url:
            raise HTTPException(400, "add a base URL before loading models")
        try:
            validated = AiConfig(base_url=base_url, model=current.model or "llama3.2")
        except ValidationError as exc:
            detail = "; ".join(
                str(error.get("msg", "Invalid AI setting")).removeprefix("Value error, ")
                for error in exc.errors(include_input=False)
            )
            raise HTTPException(400, detail) from exc
        url_changed = validated.base_url != current.base_url
        if "api_key" in body:
            api_key = str(body.get("api_key") or "").strip()
        elif url_changed:
            # Never send a previously saved key to a newly typed host.
            api_key = ""
        else:
            api_key = current.api_key
        timeout_raw = body.get("timeout_seconds")
        try:
            timeout_seconds = (
                float(timeout_raw)
                if timeout_raw is not None
                else float(current.timeout_seconds)
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "timeout must be a number of seconds") from exc
        from adhd_hub.ai_config import MAX_AI_TIMEOUT

        if timeout_seconds <= 0 or timeout_seconds > MAX_AI_TIMEOUT:
            raise HTTPException(
                400, f"timeout must be between 0 and {int(MAX_AI_TIMEOUT)} seconds"
            )
        result = list_ai_models(
            base_url=validated.base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
        if not result["ok"]:
            raise HTTPException(502, str(result["message"]))
        return result

    @router.get("/openclaw/pair", dependencies=[Depends(auth_dep)])
    def get_openclaw_pair():
        return service.openclaw_pair_status()

    @router.post("/openclaw/pair/start", dependencies=[Depends(auth_dep)])
    def start_openclaw_pair(request: Request):
        try:
            base = (
                service.settings.resolve_public_url()
                or str(request.base_url).rstrip("/")
            )
            return service.start_openclaw_pair(hub_origin=base)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/openclaw/pair/submit")
    def submit_openclaw_pair(payload: dict):
        """Public one-time submit — uses pairing code, not Hub auth token."""
        try:
            return service.submit_openclaw_pair(payload)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ValidationError as exc:
            detail = "; ".join(
                str(error.get("msg", "Invalid OpenClaw setting")).removeprefix("Value error, ")
                for error in exc.errors(include_input=False)
            )
            raise HTTPException(400, detail) from exc

    @router.post("/openclaw/pair/approve", dependencies=[Depends(auth_dep)])
    def approve_openclaw_pair():
        try:
            return service.approve_openclaw_pair()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/openclaw/pair/cancel", dependencies=[Depends(auth_dep)])
    def cancel_openclaw_pair():
        return service.cancel_openclaw_pair()

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
        from adhd_hub.forge.config import merge_forge_config_payload

        current = service.forge_config()
        cfg = merge_forge_config_payload(current, payload if isinstance(payload, dict) else {})
        service.save_forge_config(cfg)
        return cfg.public_dict()

    @router.post("/forge/profiles/{profile_id}/test", dependencies=[Depends(auth_dep)])
    def test_forge_profile(profile_id: str, payload: dict | None = None):
        body = payload if isinstance(payload, dict) else {}
        draft = body.get("draft") if isinstance(body.get("draft"), dict) else body or None
        if draft is not None and not draft:
            draft = None
        return service.test_forge_connection_profile(profile_id, draft=draft)

    @router.delete("/forge/profiles/{profile_id}", dependencies=[Depends(auth_dep)])
    def delete_forge_profile(profile_id: str):
        from fastapi import HTTPException

        try:
            return service.delete_forge_connection_profile(profile_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="profile_not_found") from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/forge/sync", dependencies=[Depends(auth_dep)])
    def forge_sync():
        return service.enqueue_forge_job("sync")

    @router.get("/forge/jobs", dependencies=[Depends(auth_dep)])
    def list_forge_jobs(limit: int = 20):
        return {"jobs": service.list_forge_jobs(limit=limit)}

    @router.get("/forge/jobs/{job_id}", dependencies=[Depends(auth_dep)])
    def get_forge_job(job_id: str):
        job = service.get_forge_job(job_id)
        if not job:
            raise HTTPException(404, "Forge job not found")
        return job

    @router.get("/forge/import/preview", dependencies=[Depends(auth_dep)])
    def forge_import_preview():
        return service.preview_forge_import()

    @router.post("/forge/import", dependencies=[Depends(auth_dep)])
    def forge_import(payload: dict | None = None):
        body = payload or {}
        slugs = body.get("slugs")
        if slugs is not None and not isinstance(slugs, list):
            raise HTTPException(400, "slugs must be a list of strings")
        return service.enqueue_forge_job(
            "import",
            payload={
                "slugs": slugs,
                "overwrite_local": bool(body.get("overwrite_local")),
            },
        )

    @router.post("/forge/inbox/import", dependencies=[Depends(auth_dep)])
    def forge_inbox_import(payload: dict | None = None):
        body = payload or {}
        limit = body.get("limit", 50)
        try:
            limit_i = int(limit)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "limit must be an integer") from exc
        if limit_i < 1 or limit_i > 100:
            raise HTTPException(400, "limit must be between 1 and 100")
        close_imported = body.get("close_imported")
        if close_imported is None:
            close = None
        else:
            close = bool(close_imported)
        return service.enqueue_forge_job(
            "inbox_import",
            payload={"limit": limit_i, "close_imported": close},
        )

    @router.get("/admin/export", dependencies=[Depends(auth_dep)])
    def admin_export(request: Request):
        from fastapi.responses import Response

        from adhd_hub.backup import is_encrypted_backup

        secret = (request.headers.get("x-backup-passphrase") or "").strip() or None
        data = service.export_backup(passphrase=secret)
        encrypted = is_encrypted_backup(data)
        filename = "adhd-hub-backup.zip.enc" if encrypted else "adhd-hub-backup.zip"
        media = "application/octet-stream" if encrypted else "application/zip"
        return Response(
            content=data,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/admin/import", dependencies=[Depends(auth_dep)])
    async def admin_import(
        request: Request,
        file: Annotated[UploadFile, File()],
        replace: bool = True,
    ):
        from adhd_hub.backup import is_encrypted_backup

        raw = await file.read()
        if not raw:
            raise HTTPException(400, "empty archive")
        # Keep restores bounded (wiki trees + sqlite); raise if you need larger.
        if len(raw) > 80 * 1024 * 1024:
            raise HTTPException(400, "archive too large (max 80 MiB)")
        secret = (request.headers.get("x-backup-passphrase") or "").strip() or None
        try:
            return service.import_backup(raw, replace=replace, passphrase=secret)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except zipfile.BadZipFile as exc:
            if is_encrypted_backup(raw):
                raise HTTPException(400, "encrypted backup needs a passphrase") from exc
            raise HTTPException(400, "not a valid zip archive") from exc

    @router.get("/sync-health", dependencies=[Depends(auth_dep)])
    def get_sync_health():
        return service.sync_health()

    @router.get("/events", dependencies=[Depends(auth_dep)])
    def list_events(
        limit: int = Query(20, ge=1, le=100),
        after: str | None = None,
        thread_id: str | None = None,
        project_slug: str | None = None,
    ):
        events = service.store.list_activity_events(
            limit=limit,
            after_id=after,
            thread_id=thread_id,
            project_slug=project_slug,
        )
        if after is None and thread_id is None and project_slug is None:
            # Default UI feed: newest first compact history.
            events = service.store.list_recent_activity_events(limit=limit)
        return {"events": [e.public_dict() for e in events]}

    @router.get("/events/stream", dependencies=[Depends(auth_dep)])
    async def events_stream(request: Request, last_event_id: str | None = None):
        """Authenticated same-origin SSE for live UI invalidation (B3.2)."""
        import asyncio

        from fastapi.responses import StreamingResponse

        from adhd_hub.events import ActivityEvent, events_to_json_line

        # Prefer Last-Event-ID header (EventSource reconnect) over query.
        resume_id = request.headers.get("last-event-id") or last_event_id
        loop = asyncio.get_running_loop()
        outbound: asyncio.Queue[ActivityEvent | None] = asyncio.Queue(maxsize=64)

        def _on_event(event: ActivityEvent) -> None:
            def _enqueue() -> None:
                try:
                    outbound.put_nowait(event)
                except asyncio.QueueFull:
                    try:
                        outbound.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        outbound.put_nowait(event)
                    except asyncio.QueueFull:
                        pass

            loop.call_soon_threadsafe(_enqueue)

        unsubscribe = service.event_bus.subscribe(_on_event)

        async def event_generator():
            try:
                # Catch-up: replay recent durable events after Last-Event-ID.
                if resume_id:
                    for event in service.store.list_activity_events(
                        limit=50, after_id=resume_id
                    ):
                        yield (
                            f"id: {event.id}\n"
                            f"event: invalidate\n"
                            f"data: {events_to_json_line(event)}\n\n"
                        )
                else:
                    yield ": connected\n\n"

                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(outbound.get(), timeout=15.0)
                    except TimeoutError:
                        yield ": ping\n\n"
                        continue
                    if event is None:
                        break
                    yield (
                        f"id: {event.id}\n"
                        f"event: invalidate\n"
                        f"data: {events_to_json_line(event)}\n\n"
                    )
            finally:
                unsubscribe()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
