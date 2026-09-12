from __future__ import annotations

import logging
import threading
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from adhd_hub.openclaw import parse_cron
from adhd_hub.service import HubService

log = logging.getLogger(__name__)

_reconcile_lock = threading.Lock()
_reconcile_backoff_until = 0.0


def start_scheduler(service: HubService) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    settings = service.settings

    stale_kwargs = parse_cron(settings.stale_nudge_cron)
    wiki_kwargs = parse_cron(settings.wiki_index_cron)
    inbox_kwargs = parse_cron(settings.forge_inbox_cron)
    reconcile_kwargs = parse_cron(settings.forge_reconcile_cron)

    async def stale_job() -> None:
        try:
            result = await service.run_stale_nudge()
            log.info("stale nudge job: %s", result)
        except Exception:
            log.exception("stale nudge job failed")

    def wiki_job() -> None:
        try:
            path = service.rebuild_wiki_index()
            log.info("wiki index rebuilt: %s", path)
        except Exception:
            log.exception("wiki index job failed")

    def forge_inbox_job() -> None:
        try:
            cfg = service.forge_config()
            if not (cfg.enabled() and cfg.board_enabled and cfg.board_inbox_enabled):
                return
            result = service.import_forge_inbox()
            log.info("forge inbox job: %s", result.get("count", result))
        except Exception:
            log.exception("forge inbox job failed")

    def forge_repo_reconcile_job() -> None:
        global _reconcile_backoff_until
        now = time.monotonic()
        if now < _reconcile_backoff_until:
            log.info("forge reconcile skipped (backoff)")
            return
        if not _reconcile_lock.acquire(blocking=False):
            log.info("forge reconcile skipped (overlap lock)")
            return
        try:
            cfg = service.forge_config()
            if not (cfg.enabled() and cfg.board_enabled):
                return
            result = service.sync_forge_now()
            log.info(
                "forge reconcile job: reconcile=%s discovery=%s",
                len(result.get("reconcile") or []),
                len(result.get("discovery") or []),
            )
        except Exception as exc:
            log.exception("forge reconcile job failed")
            # Simple backoff on provider/rate-limit style failures
            msg = str(exc).lower()
            if "429" in msg or "rate" in msg or "5" in msg[:3]:
                _reconcile_backoff_until = time.monotonic() + 300
        finally:
            _reconcile_lock.release()

    scheduler.add_job(
        stale_job,
        CronTrigger(**stale_kwargs),
        id="stale_nudge",
        replace_existing=True,
    )
    service.set_stale_schedule_callback(
        lambda expr: scheduler.reschedule_job(
            "stale_nudge", trigger=CronTrigger(**parse_cron(expr))
        )
    )
    scheduler.add_job(
        wiki_job,
        CronTrigger(**wiki_kwargs),
        id="wiki_index",
        replace_existing=True,
    )
    scheduler.add_job(
        forge_inbox_job,
        CronTrigger(**inbox_kwargs),
        id="forge_inbox",
        replace_existing=True,
    )
    scheduler.add_job(
        forge_repo_reconcile_job,
        CronTrigger(**reconcile_kwargs),
        id="forge_repo_reconcile",
        replace_existing=True,
    )
    scheduler.start()
    log.info(
        "Scheduler started (stale=%s, wiki=%s, forge_inbox=%s, forge_reconcile=%s)",
        settings.stale_nudge_cron,
        settings.wiki_index_cron,
        settings.forge_inbox_cron,
        settings.forge_reconcile_cron,
    )
    return scheduler
