"""Opt-in OpenAI-compatible chat completions client (local LLM preferred).

Used only for Wave 6 scan-line rewriting. Never send transcripts or secrets.
Disabled unless AI is enabled and a base URL is configured (Settings and/or
``ADHD_HUB_AI_BASE_URL``). Soft default: off until enabled.
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
    """True when AI scan-lines may run (enabled flag + non-empty base URL)."""
    enabled = getattr(settings, "ai_enabled", None)
    has_url = bool((settings.ai_base_url or "").strip())
    if enabled is None:
        return has_url
    return bool(enabled) and has_url


def _structured_prompt(thread: Thread) -> str:
    parts = [
        "Write one calm ADHD-friendly scan line (max 140 characters) for this Hub thread.",
        "Use only the structured fields below. No secrets, paths, URLs, or transcripts.",
        "Return plain text only — no quotes or labels.",
    ]
    fields = [
        ("Title", thread.summary),
        ("Focus", thread.focus),
        ("Resume", thread.resume_step),
        ("Goal", thread.goal),
        ("Next", "; ".join(thread.next_steps[:3])),
        ("Blocked", thread.blocked_reason),
    ]
    for label, value in fields:
        # Redact before crossing the provider boundary and before truncating
        # quoted secrets. Do not read progress bodies or transcript references.
        cleaned = scrub_scan_text(value)
        if cleaned:
            parts.append(f"{label}: {truncate_scan_text(cleaned, limit=500)}")
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
        resp = http.post(url, headers=headers, json=body, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            return None
        cleaned = scrub_scan_text(content)
        if not cleaned:
            return None
        return truncate_scan_text(cleaned, limit=SCAN_LINE_MAX)
    except Exception as exc:  # noqa: BLE001 — AI is best-effort
        log.info("AI scan-line skipped (%s)", type(exc).__name__)
        return None
    finally:
        if owns_client:
            http.close()


def list_ai_models(
    *,
    base_url: str,
    api_key: str = "",
    timeout_seconds: float = 2.5,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """GET OpenAI-compatible ``/models``; return calm ok/models/message (no secrets)."""
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return {
            "ok": False,
            "models": [],
            "message": "Add a base URL before loading models.",
        }
    url = f"{base}/models"
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    timeout = float(timeout_seconds or 2.5)
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    try:
        resp = http.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — surface calm message only
        log.info("AI models list failed (%s)", type(exc).__name__)
        return {
            "ok": False,
            "models": [],
            "message": "Could not load models from that base URL.",
        }
    finally:
        if owns_client:
            http.close()

    raw_items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(raw_items, list):
        return {
            "ok": False,
            "models": [],
            "message": "The models endpoint returned an unexpected response.",
        }
    ids: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str):
            continue
        cleaned = model_id.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ids.append(cleaned)
    ids.sort(key=str.lower)
    count = len(ids)
    noun = "model" if count == 1 else "models"
    return {
        "ok": True,
        "models": ids,
        "message": f"Connected · {count} {noun}",
    }
