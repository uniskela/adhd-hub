"""Opt-in OpenAI-compatible chat completions client (local LLM preferred).

Used only for Wave 6 scan-line rewriting. Never send transcripts or secrets.
Disabled unless AI is enabled and a base URL is configured (Settings and/or
``ADHD_HUB_AI_BASE_URL``). Soft default: off until enabled.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from adhd_hub.clarity import SCAN_LINE_MAX, scrub_scan_text, truncate_scan_text
from adhd_hub.config import Settings
from adhd_hub.models import Thread

log = logging.getLogger(__name__)

# Gemini OpenAI-compat ``GET /models`` returns ids like ``models/gemini-2.5-flash``,
# but ``POST /chat/completions`` expects the bare id (``gemini-2.5-flash``).
_MODELS_RESOURCE_PREFIX = "models/"


def normalize_openai_model_id(model_id: str) -> str:
    """Strip a leading ``models/`` resource prefix from an OpenAI-compat model id."""
    cleaned = (model_id or "").strip()
    if cleaned.lower().startswith(_MODELS_RESOURCE_PREFIX):
        stripped = cleaned[len(_MODELS_RESOURCE_PREFIX) :].strip()
        return stripped or cleaned
    return cleaned


@dataclass(frozen=True)
class AiScanLineResult:
    """Outcome of a best-effort AI scan-line rewrite (no secrets)."""

    text: str | None = None
    fail_hint: str | None = None


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
) -> AiScanLineResult:
    """Call an OpenAI-compatible /chat/completions endpoint; return scrubbed text or a calm hint."""
    base = (settings.ai_base_url or "").strip().rstrip("/")
    if not base:
        return AiScanLineResult(fail_hint="AI base URL is not configured.")
    url = f"{base}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.ai_api_key:
        headers["Authorization"] = f"Bearer {settings.ai_api_key}"
    model = normalize_openai_model_id(settings.ai_model or "llama3.2")
    body: dict[str, Any] = {
        "model": model or "llama3.2",
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
            return AiScanLineResult(
                fail_hint="AI returned no choices — showing the heuristic line."
            )
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            return AiScanLineResult(
                fail_hint="AI returned an empty reply — showing the heuristic line."
            )
        cleaned = scrub_scan_text(content)
        if not cleaned:
            return AiScanLineResult(
                fail_hint="AI reply was empty after scrubbing — showing the heuristic line."
            )
        return AiScanLineResult(text=truncate_scan_text(cleaned, limit=SCAN_LINE_MAX))
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code == 404:
            log.info(
                "AI scan-line skipped (HTTP 404 — model not found or chat endpoint missing)"
            )
            return AiScanLineResult(
                fail_hint=(
                    "Model not found (404) — check the model id "
                    "(use gemini-… without a models/ prefix)."
                )
            )
        log.info("AI scan-line skipped (HTTP %s)", code)
        return AiScanLineResult(
            fail_hint=f"AI unavailable (HTTP {code}) — showing the heuristic line."
        )
    except Exception as exc:  # noqa: BLE001 — AI is best-effort
        log.info("AI scan-line skipped (%s)", type(exc).__name__)
        return AiScanLineResult(
            fail_hint="AI unavailable — showing the heuristic line."
        )
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
        cleaned = normalize_openai_model_id(model_id)
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
