from __future__ import annotations

import base64
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from adhd_hub.backlog.models import (
    VERSION,
    AiRequest,
    CancelReceipt,
    DraftPatch,
    DraftPlan,
    DraftRequest,
    IssueKind,
    JobReceipt,
    ScanPage,
    ScanReceipt,
    ScanRequest,
    ScanSummary,
)
from adhd_hub.backlog.service import BacklogError, BacklogService


def _call(operation, *args):
    try:
        return operation(*args)
    except BacklogError as exc:
        raise HTTPException(exc.status, exc.code) from None


def _cursor(scan_id: str, number: int) -> str:
    return base64.urlsafe_b64encode(f"{scan_id}:{number}".encode()).decode()


def _read_cursor(cursor: str, scan_id: str) -> int:
    try:
        scope, raw = base64.b64decode(cursor, altchars=b"-_", validate=True).decode().split(":")
        number = int(raw)
        if scope == scan_id and 0 < number < 2**63:
            return number
    except (ValueError, UnicodeError):
        pass
    raise HTTPException(422, "invalid_cursor")


def build_backlog_router(backlog: BacklogService, auth_dep) -> APIRouter:
    router = APIRouter(prefix="/backlog", dependencies=[Depends(auth_dep)])

    @router.post("/scans", status_code=202, response_model=ScanReceipt)
    def create_scan(request: ScanRequest):
        return _call(backlog.create_scan, request)

    @router.get("/scans/{scan_id}", response_model=ScanSummary)
    def get_scan(scan_id: str):
        return _call(backlog.get_scan, scan_id)

    @router.get("/scans/{scan_id}/items", response_model=ScanPage)
    def scan_items(
        scan_id: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=160)] = None,
        kind: IssueKind | None = None,
        cluster: Annotated[int | None, Query(gt=0, lt=2**63)] = None,
    ):
        _call(backlog.get_scan, scan_id)
        after = _read_cursor(cursor, scan_id) if cursor else 0
        rows = backlog.storage.items(
            scan_id, after=after, limit=limit + 1, kind=kind, cluster=cluster
        )
        return {
            "schema_version": VERSION,
            "items": rows[:limit],
            "next_cursor": _cursor(scan_id, rows[limit - 1].issue.identity.number)
            if len(rows) > limit
            else None,
        }

    @router.post("/scans/{scan_id}/ai-suggestions", status_code=202, response_model=JobReceipt)
    def ai_suggestions(scan_id: str, request: AiRequest | None = None):
        return _call(backlog.create_ai_job, scan_id, request or AiRequest())

    @router.post("/jobs/{job_id}/cancel", status_code=202, response_model=CancelReceipt)
    def cancel(job_id: str):
        if not backlog.hub.cancel_backlog_job(job_id):
            raise HTTPException(404, "backlog_job_not_found")
        return {"schema_version": VERSION, "cancel_requested": True}

    @router.post("/plans", status_code=201, response_model=DraftPlan)
    def create_plan(request: DraftRequest):
        return _call(backlog.create_plan, request.scan_id)

    @router.get("/plans/{plan_id}", response_model=DraftPlan)
    def get_plan(plan_id: str):
        return _call(backlog.get_plan, plan_id)

    @router.patch("/plans/{plan_id}", response_model=DraftPlan)
    def patch_plan(plan_id: str, request: DraftPatch):
        return _call(backlog.patch_plan, plan_id, request)

    return router
