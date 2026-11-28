from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime
from threading import Lock
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx

from adhd_hub.backlog.ai_recommend import recommend_with_ai
from adhd_hub.backlog.classify import SAFE_DISPOSITIONS, classify
from adhd_hub.backlog.models import (
    AiRequest,
    ClusterDestination,
    Disposition,
    DraftFields,
    DraftItem,
    DraftPatch,
    DraftPlan,
    ExistingThread,
    ScanRequest,
    ScanSummary,
)
from adhd_hub.backlog.scanner import (
    ForgeReader,
    digest,
    repository_for,
    scan_repository,
    trusted_authors,
)
from adhd_hub.backlog.storage import BacklogStorage
from adhd_hub.models import ThreadStatus
from adhd_hub.work_identity import WorkSource, resolve_work_source

if TYPE_CHECKING:
    from adhd_hub.forge.jobs import ForgeJob
    from adhd_hub.service import HubService


log = logging.getLogger(__name__)


class BacklogError(Exception):
    def __init__(self, status: int, code: str):
        self.status = status
        self.code = code
        super().__init__(code)


class BacklogService:
    def __init__(self, hub: HubService):
        self.hub = hub
        self.storage = BacklogStorage(hub.store)
        self._ai_lock = Lock()
        self._ai_in_flight: set[str] = set()

    def _target(self, project_slug):
        project = self.hub.store.get_project(project_slug)
        if not project or project.archived_at or not project.forge_connection_profile_id:
            raise BacklogError(400, "forge_target_unresolved")
        cfg = self.hub.forge_config(project.slug)
        try:
            repository = repository_for(cfg)
        except ValueError:
            raise BacklogError(400, "forge_target_unresolved") from None
        profile = cfg.profile_by_id(project.forge_connection_profile_id)
        if (
            profile is None
            or bool(project.forge_owner) != bool(project.forge_repo)
            or (not project.forge_owner and not (profile.owner and profile.repo))
        ):
            raise BacklogError(400, "forge_target_unresolved")
        return project, cfg, repository

    def _policy_hash(self, project, cfg):
        return digest(
            {
                "version": 1,
                "profile": project.forge_connection_profile_id,
                "api": cfg.api_root(),
                "web": cfg.web_browse_root(),
                "authors": sorted(trusted_authors(cfg)),
                "inbox": cfg.board_inbox_enabled,
                "hub_labels": sorted(cfg.issue_labels),
                "select_labels": sorted(cfg.issue_import_labels),
                "operator": cfg.forge_account_login,
                "ai": project.slug in self.hub.settings.backlog_ai_projects,
                "private": project.slug in self.hub.settings.backlog_ai_private_projects,
            }
        )

    def create_scan(self, request: ScanRequest):
        project, cfg, repo = self._target(request.project_slug)
        if request.selector == "adhd_inbox" and (
            not cfg.board_inbox_enabled or not trusted_authors(cfg)
        ):
            raise BacklogError(400, "board_inbox_authors_required")
        scan = ScanSummary(
            scan_id=uuid4().hex,
            project_slug=project.slug,
            repository=repo,
            include_closed=request.include_closed,
            selector=request.selector,
            status="queued",
            policy_hash=self._policy_hash(project, cfg),
            created_at=datetime.now(UTC),
        )
        if not self.storage.add_scan(scan, digest(repo.model_dump())):
            raise BacklogError(409, "scan_running")
        job = self.hub.enqueue_forge_job(
            "backlog_scan",
            project_slug=project.slug,
            payload={"scan_id": scan.scan_id},
            label="Scan forge backlog",
        )
        return {
            "schema_version": scan.schema_version,
            "scan_id": scan.scan_id,
            "job_id": job["job_id"],
        }

    def get_scan(self, scan_id):
        scan = self.storage.scan(scan_id)
        if scan is None:
            raise BacklogError(404, "scan_not_found")
        return scan

    def _current_target(self, scan):
        try:
            project, cfg, repo = self._target(scan.project_slug)
        except BacklogError:
            raise BacklogError(409, "stale_snapshot") from None
        if repo != scan.repository or self._policy_hash(project, cfg) != scan.policy_hash:
            raise BacklogError(409, "stale_snapshot")
        return project, cfg

    def _find_thread(self, identity):
        return self.hub.store.get_thread_by_external_identity(
            identity.provider,
            identity.host,
            identity.owner,
            identity.repo,
            identity.number,
        )

    def _local_threads(self, project):
        legacy = self.hub.store.list_meta_prefix("forge_issue:")
        threads = []
        for status in (ThreadStatus.open, ThreadStatus.blocked):
            after_id = None
            while True:
                page = self.hub.store.list_threads(
                    project_slug=project.slug,
                    status=status,
                    order_by_id=True,
                    after_id=after_id,
                    limit=500,
                )
                threads.extend(
                    thread
                    for thread in page
                    if self._is_local_destination(project, thread)
                    and f"forge_issue:{thread.id}" not in legacy
                )
                if len(page) < 500:
                    break
                after_id = page[-1].id
        return threads

    @staticmethod
    def _is_local_destination(project, thread):
        return (
            thread is not None
            and thread.project_slug == project.slug
            and thread.status in {ThreadStatus.open, ThreadStatus.blocked}
            and not thread.merged_into
            and not thread.external_provider
            and not thread.external_issue_number
            and not thread.source_issue_url
            and not thread.source_imported_at
            and not thread.source_snapshot
            and not thread.source_content_hash
            and thread.origin not in {"forge-inbox", "forge-import"}
            and resolve_work_source(project, thread) == WorkSource.local
        )

    def run_scan(self, job: ForgeJob):
        scan = self.get_scan(job.payload["scan_id"])
        scan.status = "running"
        scan.started_at = datetime.now(UTC)
        self.storage.save_scan(scan)
        items = []
        try:
            project, cfg = self._current_target(scan)
            with httpx.Client() as client:
                result = scan_repository(
                    ForgeReader(cfg, client, job.cancel_requested.is_set), scan, self._find_thread
                )
            scan.pages_read = result.pages_read
            scan.detail_limited_count = result.detail_limited_count
            scan.truncated = result.truncated
            scan.private = result.private
            scan.repository_id = result.repository_id
            if result.error:
                scan.error_code = result.error.code
                scan.retry_after_seconds = result.error.retry_after
            items = classify(
                result.items, now=scan.started_at, local_threads=self._local_threads(project)
            )
            scan.issue_count = len(items)
            scan.counts_by_kind = dict(Counter(item.issue.kind for item in items))
            scan.protected_count = sum(bool(item.issue.protection_flags) for item in items)
            scan.cluster_count = len({item.deterministic.cluster_key for item in items} - {None})
            if job.cancel_requested.is_set() or scan.error_code == "cancelled":
                scan.status = "cancelled"
            elif scan.error_code:
                scan.status = "partial" if result.pages_read else "failed"
            else:
                scan.status = "completed"
        except BacklogError as exc:
            scan.status = "failed"
            scan.error_code = exc.code
        except Exception as exc:  # noqa: BLE001 — provider data can appear in exception details
            log.warning("Backlog scan failed (%s)", type(exc).__name__)
            scan.status = "failed"
            scan.error_code = "scan_failed"
        finally:
            scan.finished_at = datetime.now(UTC)
            self.storage.save_scan(scan, items)
        return {"scan_id": scan.scan_id, "status": scan.status, "count": scan.issue_count}

    def _ready(self, scan):
        if scan.status not in {"completed", "partial"}:
            raise BacklogError(409, "scan_not_ready")
        project, cfg = self._current_target(scan)
        if self.storage.stale(scan.scan_id):
            raise BacklogError(409, "stale_snapshot")
        return project, cfg

    def _ai_enabled(self, scan):
        ai = self.hub.ai_config()
        return (
            ai.is_active()
            and ai.backlog_suggestions
            and scan.project_slug in self.hub.settings.backlog_ai_projects
            and (
                not scan.private
                or scan.project_slug in self.hub.settings.backlog_ai_private_projects
            )
        )

    def create_ai_job(self, scan_id, request: AiRequest):
        scan = self.get_scan(scan_id)
        self._ready(scan)
        if not self._ai_enabled(scan):
            raise BacklogError(403, "ai_not_opted_in")
        with self._ai_lock:
            items = self.storage.items(scan_id)
            if scan_id in self._ai_in_flight:
                raise BacklogError(409, "ai_running")
            selected = (
                set(request.issue_numbers)
                if request.issue_numbers is not None
                else {item.issue.identity.number for item in items}
            )
            if not selected.issubset({item.issue.identity.number for item in items}):
                raise BacklogError(422, "issue_not_in_scan")
            if not selected:
                raise BacklogError(422, "no_scan_items")
            self.storage.save_advice(
                scan_id,
                [
                    (item.model_copy(update={"ai_status": "queued", "ai": None}), None)
                    for item in items
                    if item.issue.identity.number in selected
                ],
            )
            self._ai_in_flight.add(scan_id)
            job = self.hub.enqueue_forge_job(
                "backlog_ai",
                project_slug=scan.project_slug,
                payload={"scan_id": scan_id},
                label="Suggest backlog recommendations",
            )
        return {"schema_version": scan.schema_version, "job_id": job["job_id"]}

    def run_ai(self, job: ForgeJob):
        scan = self.get_scan(job.payload["scan_id"])
        config = self.hub.ai_config()
        selected = [item for item in self.storage.items(scan.scan_id) if item.ai_status == "queued"]

        def active():
            if job.cancel_requested.is_set():
                return "cancelled"
            if self.hub.ai_config() != config or not self._ai_enabled(scan):
                return "ai_not_opted_in"
            try:
                self._current_target(scan)
            except BacklogError as exc:
                return exc.code
            return None

        final_status = "interrupted"
        try:
            _, cfg = self._ready(scan)
            if status := active():
                final_status = status
                return {"status": status}
            secrets = (
                self.hub.settings.auth_token,
                config.api_key,
                cfg.token,
                getattr(self.hub.settings, "openclaw_token", None) or "",
                *(profile.token for profile in cfg.connection_profiles),
            )
            with httpx.Client() as forge_http, httpx.Client() as ai_http:
                return recommend_with_ai(
                    self.storage,
                    scan,
                    selected,
                    forge=ForgeReader(cfg, forge_http, job.cancel_requested.is_set),
                    config=config,
                    active=active,
                    secrets=secrets,
                    client=ai_http,
                    private_allowed=scan.project_slug
                    in self.hub.settings.backlog_ai_private_projects,
                )
        except BacklogError as exc:
            final_status = exc.code
            return {"status": exc.code}
        except Exception as exc:  # noqa: BLE001 — provider replies are untrusted
            log.warning("Backlog suggestions unavailable (%s)", type(exc).__name__)
            final_status = "ai_unavailable"
            return {"status": final_status}
        finally:
            with self._ai_lock:
                self.storage.save_advice(
                    scan.scan_id,
                    [
                        (item.model_copy(update={"ai_status": final_status}), None)
                        for item in self.storage.items(scan.scan_id)
                        if item.ai_status == "queued"
                    ],
                )
                self._ai_in_flight.discard(scan.scan_id)

    def create_plan(self, scan_id: str):
        scan = self.get_scan(scan_id)
        self._ready(scan)
        plan_items = []
        for item in self.storage.items(scan_id):
            flags = sorted(set(item.issue.protection_flags) | set(item.ai_protection_flags))
            disposition = item.deterministic.disposition
            if flags and disposition not in SAFE_DISPOSITIONS:
                disposition = Disposition.skip
            plan_items.append(
                DraftItem(
                    issue_number=item.issue.identity.number,
                    source_revision=item.issue.source_revision,
                    disposition=disposition,
                    destination=(
                        item.deterministic.destination if disposition != Disposition.skip else None
                    ),
                    protection_flags=flags,
                    ai_status=item.ai_status,
                    ai=item.ai,
                )
            )
        self._skip_unavailable_clusters({item.issue_number: item for item in plan_items})
        plan = DraftPlan(
            plan_id=uuid4().hex,
            scan_id=scan_id,
            project_slug=scan.project_slug,
            policy_hash=scan.policy_hash,
            items=plan_items,
        )
        self.storage.add_plan(plan)
        return plan

    def get_plan(self, plan_id):
        plan = self.storage.plan(plan_id)
        if plan is None:
            raise BacklogError(404, "plan_not_found")
        return plan

    def patch_plan(self, plan_id, request: DraftPatch):
        plan = self.get_plan(plan_id)
        if plan.version != request.expected_version:
            raise BacklogError(409, "version_conflict")
        scan = self.get_scan(plan.scan_id)
        project, _ = self._ready(scan)
        items = {item.issue_number: item for item in plan.items}
        for snapshot in self.storage.items(scan.scan_id):
            item = items[snapshot.issue.identity.number]
            item.protection_flags = sorted(
                set(item.protection_flags)
                | set(snapshot.issue.protection_flags)
                | set(snapshot.ai_protection_flags)
            )
            if (
                item.protection_flags
                and item.disposition not in SAFE_DISPOSITIONS
                and not item.protection_override
            ):
                item.disposition = Disposition.skip
                item.destination = None
        self._skip_unavailable_clusters(items)
        seen = set()
        for edit in request.items:
            item = items.get(edit.issue_number)
            if item is None or edit.issue_number in seen:
                raise BacklogError(422, "invalid_plan_item")
            seen.add(edit.issue_number)
            if edit.accept_ai:
                if not item.ai or not self._ai_enabled(scan):
                    raise BacklogError(422, "ai_suggestion_unavailable")
                if (
                    item.protection_flags
                    and item.ai.suggestion.disposition not in SAFE_DISPOSITIONS
                ):
                    raise BacklogError(422, "protected_requires_override")
                suggestion = item.ai.suggestion
                item.disposition = suggestion.disposition
                item.destination = item.ai.destination
                item.proposed_fields = DraftFields(
                    **(
                        suggestion.suggested_continuity.model_dump()
                        if suggestion.suggested_continuity
                        else {}
                    ),
                    title=suggestion.suggested_title or None,
                    labels=suggestion.proposed_labels,
                    workstream=suggestion.workstream,
                )
                item.disposition_source = "ai_accepted"
            if edit.disposition is not None:
                item.disposition = edit.disposition
                item.disposition_source = "operator"
            if "destination" in edit.model_fields_set:
                item.destination = edit.destination
                item.disposition_source = "operator"
            if edit.proposed_fields is not None:
                item.proposed_fields = edit.proposed_fields
                item.disposition_source = "operator"
            if "protection_override" in edit.model_fields_set:
                reason = (
                    edit.protection_override.reason.strip() if edit.protection_override else None
                )
                if reason == "":
                    raise BacklogError(422, "override_reason_required")
                item.protection_override = reason
            if item.disposition == Disposition.skip:
                item.destination = None
            if (
                item.protection_flags
                and item.disposition not in SAFE_DISPOSITIONS
                and not item.protection_override
            ):
                raise BacklogError(422, "protected_requires_override")
            if isinstance(item.destination, ExistingThread):
                dest_id = item.destination.thread_id
                thread = self.hub.store.get_thread(dest_id)
                if not self._is_local_destination(project, thread) or self.hub.store.get_meta(
                    f"forge_issue:{dest_id}"
                ):
                    raise BacklogError(422, "invalid_destination")
        self._validate_clusters(items)
        plan.version += 1
        if not self.storage.update_plan(plan, request.expected_version):
            raise BacklogError(409, "version_conflict")
        return plan

    @staticmethod
    def _cluster_has_destination(number, items):
        item = items[number]
        chain = {number}
        while isinstance(item.destination, ClusterDestination):
            target = item.destination.issue_number
            if target not in items or target in chain:
                return False
            chain.add(target)
            item = items[target]
        return item.destination is not None and item.disposition in {
            Disposition.migrate,
            Disposition.consolidate,
        }

    def _skip_unavailable_clusters(self, items):
        for number, item in items.items():
            if isinstance(
                item.destination, ClusterDestination
            ) and not self._cluster_has_destination(number, items):
                item.disposition = Disposition.skip
                item.destination = None

    def _validate_clusters(self, items):
        for number, item in items.items():
            if isinstance(
                item.destination, ClusterDestination
            ) and not self._cluster_has_destination(number, items):
                raise BacklogError(422, "invalid_destination")
