from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from adhd_hub.openclaw import parse_cron
from adhd_hub.service import HubService

log = logging.getLogger(__name__)


def start_scheduler(service: HubService) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    settings = service.settings

    stale_kwargs = parse_cron(settings.stale_nudge_cron)
    wiki_kwargs = parse_cron(settings.wiki_index_cron)

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

    scheduler.add_job(
        stale_job,
        CronTrigger(**stale_kwargs),
        id="stale_nudge",
        replace_existing=True,
    )
    scheduler.add_job(
        wiki_job,
        CronTrigger(**wiki_kwargs),
        id="wiki_index",
        replace_existing=True,
    )
    scheduler.start()
    log.info(
        "Scheduler started (stale=%s, wiki=%s)",
        settings.stale_nudge_cron,
        settings.wiki_index_cron,
    )
    return scheduler
