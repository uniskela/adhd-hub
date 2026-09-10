"""OpenClaw orchestration extracted from HubService."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from adhd_hub.models import Thread
from adhd_hub.openclaw import OpenClawBridge
from adhd_hub.openclaw_config import (
    OpenClawConfig,
    load_openclaw_config,
    openclaw_from_settings,
)
from adhd_hub.openclaw_config import (
    save_openclaw_config as persist_openclaw_config,
)
from adhd_hub.openclaw_pair import OpenClawPairStore, openclaw_pair_prompt

if TYPE_CHECKING:
    from adhd_hub.service import HubService


class OpenClawFacade:
    def __init__(self, hub: HubService) -> None:
        self._hub = hub
        self._stale_schedule_callback: Callable[[str], None] | None = None
        self._pair_store = OpenClawPairStore(hub.settings.data_dir)
        config = load_openclaw_config(
            hub.settings.data_dir,
            env_defaults=openclaw_from_settings(hub.settings),
            auth_token=hub.settings.auth_token,
        )
        self._apply_openclaw_config(config)

    def _apply_openclaw_config(self, config: OpenClawConfig) -> None:
        self._openclaw_config = config
        self._hub.settings.stale_nudge_cron = config.stale_nudge_cron
        self._hub.settings.stale_days = config.stale_days
        self._hub.settings.remind_cooldown_days = config.remind_cooldown_days
        self._hub.settings.digest_max_nudge = config.digest_max_nudge
        self._hub.openclaw = OpenClawBridge(
            webhook_url=config.webhook_url,
            agent_url=config.agent_url,
            token=config.token,
            alerts_enabled=config.alerts_enabled,
        )

    def openclaw_config(self) -> OpenClawConfig:
        return self._openclaw_config

    def save_openclaw_config(self, config: OpenClawConfig) -> OpenClawConfig:
        persist_openclaw_config(
            self._hub.settings.data_dir,
            config,
            auth_token=self._hub.settings.auth_token,
        )
        self._apply_openclaw_config(config)
        if self._stale_schedule_callback:
            self._stale_schedule_callback(config.stale_nudge_cron)
        return config

    def openclaw_pair_status(self) -> dict:
        return self._pair_store.status().public_dict()

    def start_openclaw_pair(self, *, hub_origin: str) -> dict:
        state = self._pair_store.start()
        out = state.public_dict()
        out["prompt"] = openclaw_pair_prompt(
            hub_origin=hub_origin,
            user_code=state.user_code,
        )
        return out

    def submit_openclaw_pair(self, payload: dict) -> dict:
        state = self._pair_store.submit(
            user_code=str(payload.get("user_code") or ""),
            webhook_url=str(payload.get("webhook_url") or ""),
            agent_url=str(payload.get("agent_url") or ""),
            token=str(payload.get("token") or ""),
            alerts_enabled=bool(payload.get("alerts_enabled", True)),
            stale_nudge_cron=payload.get("stale_nudge_cron"),
            stale_days=payload.get("stale_days"),
            remind_cooldown_days=payload.get("remind_cooldown_days"),
            digest_max_nudge=payload.get("digest_max_nudge"),
        )
        return state.public_dict()

    def approve_openclaw_pair(self) -> dict:
        config = self._pair_store.approve_config(current=self.openclaw_config())
        saved = self.save_openclaw_config(config)
        return saved.public_dict()

    def cancel_openclaw_pair(self) -> dict:
        self._pair_store.cancel()
        return self._pair_store.status().public_dict()

    def set_stale_schedule_callback(self, callback: Callable[[str], None]) -> None:
        self._stale_schedule_callback = callback

    async def test_openclaw_connection(self) -> dict[str, str | bool]:
        return await self._hub.openclaw.test_connection()

    def openclaw_memory_digest(
        self,
        *,
        project_slug: str | None = None,
        note: str | None = None,
        threads: list[Thread] | None = None,
    ) -> tuple[str, str]:
        """Build a short OpenClaw memory digest (summaries only; no transcripts)."""
        if threads is None:
            threads = self._hub.list_open_threads(project_slug=project_slug, limit=8)
        else:
            threads = threads[:8]
        out: list[str] = []
        for t in threads:
            step = ""
            if t.resume_step:
                parts = [ln.strip() for ln in t.resume_step.splitlines() if ln.strip()]
                step = parts[0] if parts else ""
            bit = f"- {t.summary}"
            if t.project_slug:
                bit += f" [{t.project_slug}]"
            if step:
                bit += f" → {step[:120]}"
            out.append(bit)
        if not out:
            out.append("- No open Hub threads right now.")
        extra = (note or "").strip()
        if extra:
            out.append(f"- Note: {extra[:240]}")
        title = f"ADHD Hub · {project_slug}" if project_slug else "ADHD Hub · open work"
        body = "\n".join(out[:10])
        return title, body

    def push_openclaw_memory_sync(
        self,
        *,
        project_slug: str | None = None,
        note: str | None = None,
        threads: list[Thread] | None = None,
    ) -> dict:
        title, body = self.openclaw_memory_digest(
            project_slug=project_slug, note=note, threads=threads
        )
        result = self._hub.openclaw.push_memory_roundtrip_sync(title=title, digest=body)
        result["digest_lines"] = len(body.splitlines())
        return result

    async def push_openclaw_memory(
        self,
        *,
        project_slug: str | None = None,
        note: str | None = None,
        threads: list[Thread] | None = None,
    ) -> dict:
        title, body = self.openclaw_memory_digest(
            project_slug=project_slug, note=note, threads=threads
        )
        result = await self._hub.openclaw.push_memory_roundtrip(title=title, digest=body)
        result["digest_lines"] = len(body.splitlines())
        return result

    async def run_stale_nudge(self) -> dict:
        stale = self._hub.list_stale_threads()
        if not stale:
            return {"nudged": 0, "openclaw": False, "memory": None}
        limited = stale[: self._hub.settings.digest_max_nudge]
        lines = [
            f"{t.summary} [{t.project_slug or '-'}] (id={t.id}, updated={t.updated_at.date()})"
            for t in limited
        ]
        sent = await self._hub.openclaw.notify_stale_threads(lines)
        self._hub.rebuild_wiki_index()
        memory = None
        if sent:
            self._hub.store.touch_reminded([t.id for t in limited])
            # Digest the nudged (often older) threads — not only recently updated opens.
            # Call through HubService so tests/callers can mock the public method.
            memory = await self._hub.push_openclaw_memory(
                threads=limited,
                note="After stale nudge",
            )
        return {
            "nudged": len(lines) if sent else 0,
            "openclaw": sent,
            "memory": memory,
        }
