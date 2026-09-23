"""Opt-in OpenAI-compatible chat completions client (local LLM preferred).

Used only for Wave 6 scan-line rewriting. Never send transcripts or secrets.
Disabled unless ``ADHD_HUB_AI_BASE_URL`` is set.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from adhd_hub.clarity import SCAN_LINE_MAX, scrub_scan_text, truncate_scan_text
from adhd_hub.config import Settings
from adhd_hub.models import Thread

log = logging.getLogger(__name__)


def ai_configured(settings: Settings) -> bool:
    return bool((settings.ai_base_url or "").strip())


def _structured_prompt(thread: Thread) -> str:
    parts = [
        "Write one calm ADHD-friendly scan line (max 140 characters) for this Hub thread.",
        "Use only the structured fields below. No secrets, paths, URLs, or transcripts.",
        "Return plain text only — no quotes or labels.",
        f"Title: {thread.summary}",
    ]
    if thread.focus:
        parts.append(f"Focus: {thread.focus}")
    if thread.resume_step:
        parts.append(f"Resume: {thread.resume_step}")
    if thread.goal:
        parts.append(f"Goal: {thread.goal}")
    if thread.next_steps:
        parts.append("Next: " + "; ".join(thread.next_steps[:3]))
    if thread.blocked_reason:
        parts.append(f"Blocked: {thread.blocked_reason}")
    return "\n".join(parts)


def generate_ai_scan_line(
    settings: Settings,
    thread: Thread,
    *,
    client: httpx.Client | None = None,
) -> str | None:
    """Call an OpenAI-compatible /chat/completions endpoint; return scrubbed text or None."""
    base = (settings.ai_base_url or "").strip().rstrip("/")
    if not base:
        return None
    url = f"{base}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.ai_api_key:
        headers["Authorization"] = f"Bearer {settings.ai_api_key}"
    body: dict[str, Any] = {
        "model": settings.ai_model or "llama3.2",
        "temperature": 0.2,
        "max_tokens": 80,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You rewrite Hub continuity into one short calm scan line. "
                    "Never invent secrets, absolute paths, or private URLs."
                ),
            },
            {"role": "user", "content": _structured_prompt(thread)},
        ],
    }
    timeout = float(settings.ai_timeout_seconds or 2.5)
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    try:
        resp = http.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message") or {}
        content = message.get("content")
        cleaned = scrub_scan_text(content)
        if not cleaned:
            return None
        return truncate_scan_text(cleaned, limit=SCAN_LINE_MAX)
    except Exception as exc:  # noqa: BLE001 — AI is best-effort
        log.info("AI scan-line skipped: %s", exc)
        return None
    finally:
        if owns_client:
            http.close()
