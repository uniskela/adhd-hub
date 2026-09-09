from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

log = logging.getLogger(__name__)


class OpenClawBridge:
    """Optional outbound bridge to OpenClaw webhooks."""

    def __init__(
        self,
        *,
        webhook_url: str = "",
        agent_url: str = "",
        token: str = "",
        alerts_enabled: bool = False,
    ) -> None:
        self.webhook_url = webhook_url
        self.agent_url = agent_url
        self.token = token
        self.alerts_enabled = alerts_enabled

    @property
    def enabled(self) -> bool:
        return self.alerts_enabled and bool(self.webhook_url or self.agent_url)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def wake(self, text: str) -> bool:
        url = self.webhook_url
        if not url:
            return False
        payload = {"text": text, "mode": "now"}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
                resp.raise_for_status()
            log.info("OpenClaw wake sent (%s)", resp.status_code)
            return True
        except Exception:
            log.exception("OpenClaw wake failed")
            return False

    async def agent(self, prompt: str) -> bool:
        url = self.agent_url
        if not url:
            # Fall back to wake with the prompt text
            return await self.wake(prompt)
        payload = {
            "message": prompt,
            "name": "ADHD Hub stale digest",
            "wakeMode": "now",
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
                resp.raise_for_status()
            log.info("OpenClaw agent hook sent (%s)", resp.status_code)
            return True
        except Exception:
            log.exception("OpenClaw agent hook failed")
            return False

    async def notify_stale_threads(self, lines: list[str]) -> bool:
        if not lines or not self.enabled:
            return False
        body = (
            "ADHD Hub — unfinished work still open:\n"
            + "\n".join(f"- {line}" for line in lines)
            + "\n\nReply or open Cursor/Codex and call check_overlap / session_digest."
        )
        if self.agent_url:
            return await self.agent(
                "Gently remind the user about these half-finished projects. "
                "Keep it short and non-nagging. Suggest one next step each if obvious.\n\n"
                + body
            )
        return await self.wake(body)

    async def sync_memory_note(self, title: str, content: str) -> bool:
        """Ask OpenClaw to retain a short memory note (best-effort via agent hook)."""
        if not self.enabled:
            return False
        prompt = (
            "Save this short ADHD Hub digest to long-term memory. "
            "Keep only the bullets; do not invent tasks; never store secrets or raw chats.\n"
            f"Title: {title}\n\n{content}\n\n"
            "Reply with a one-line ack only, e.g. 'Saved N open items.'"
        )
        return await self.agent(prompt)

    def sync_memory_note_sync(self, title: str, content: str) -> bool:
        """Sync variant of sync_memory_note for MCP / non-async callers."""
        if not self.enabled:
            return False
        url = self.agent_url or self.webhook_url
        if not url:
            return False
        prompt = (
            "Save this short ADHD Hub digest to long-term memory. "
            "Keep only the bullets; do not invent tasks; never store secrets or raw chats.\n"
            f"Title: {title}\n\n{content}\n\n"
            "Reply with a one-line ack only, e.g. 'Saved N open items.'"
        )
        if self.agent_url:
            payload: dict[str, Any] = {
                "message": prompt,
                "name": "ADHD Hub memory digest",
                "wakeMode": "now",
            }
        else:
            payload = {"text": prompt, "mode": "now"}
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload, headers=self._headers())
                resp.raise_for_status()
            log.info("OpenClaw memory sync sent (%s)", resp.status_code)
            return True
        except Exception:
            log.exception("OpenClaw memory sync failed")
            return False

    async def push_memory_roundtrip(self, *, title: str, digest: str) -> dict[str, Any]:
        """Push a short digest and return a simple ack status (no chat transcript)."""
        sent = await self.sync_memory_note(title, digest)
        return {
            "ok": sent,
            "ack": "saved" if sent else "not_sent",
            "title": title,
        }

    def push_memory_roundtrip_sync(self, *, title: str, digest: str) -> dict[str, Any]:
        sent = self.sync_memory_note_sync(title, digest)
        return {
            "ok": sent,
            "ack": "saved" if sent else "not_sent",
            "title": title,
        }

    async def test_connection(self) -> dict[str, str | bool]:
        target = "agent" if self.agent_url else "webhook"
        if not (self.agent_url or self.webhook_url):
            return {"ok": False, "target": target, "message": "Add an endpoint first."}
        sent = await self.agent(
            "ADHD Hub connection test. Reply only with a short confirmation; no action is needed."
        )
        return {
            "ok": sent,
            "target": target,
            "message": "Test alert sent." if sent else "OpenClaw did not accept the test alert.",
        }


def parse_cron(expr: str) -> dict[str, str]:
    """Parse classic 5-field cron into APScheduler kwargs."""
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"Expected 5-field cron, got: {expr!r}")
    minute, hour, day, month, day_of_week = parts
    return {
        "minute": minute,
        "hour": hour,
        "day": day,
        "month": month,
        "day_of_week": day_of_week,
    }


def stale_cutoff(days: int, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now - timedelta(days=days)
