"""Opt-in OpenAI-compatible chat completions client (local LLM preferred).

Used only for Wave 6 scan-line rewriting. Never send transcripts or secrets.
Disabled unless AI is enabled and a base URL is configured (Settings and/or
``ADHD_HUB_AI_BASE_URL``). Soft default: off until enabled.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from adhd_hub.clarity import SCAN_LINE_MAX, scrub_scan_text, truncate_scan_text
from adhd_hub.config import Settings
from adhd_hub.models import Thread

log = logging.getLogger(__name__)

# Gemini OpenAI-compat ``GET /models`` returns ids like ``models/gemini-2.5-flash``,
# but ``POST /chat/completions`` expects the bare id (``gemini-2.5-flash``).
_MODELS_RESOURCE_PREFIX = "models/"

# Provider/model refs some UIs prepend (e.g. ``google/gemini-2.5-flash``).
_PROVIDER_MODEL_PREFIX_RE = re.compile(r"^google/", re.IGNORECASE)

# OpenAI-compat ``/models`` lists embeddings, Imagen, etc. that cannot chat.
_NON_CHAT_MODEL_MARKERS = (
    "embedding",
    "imagen",
    "aqa",
    "gecko",
    "whisper",
    "realtime",
    "computer-use",
    "-image",
    "-video",
    "-tts",
)

_PROVIDER_SNIPPET_MAX = 160
_KEYISH_RE = re.compile(
    r"(?i)\b("
    r"sk-[A-Za-z0-9_-]{8,}"
    r"|AIza[A-Za-z0-9_-]{8,}"
    r"|Bearer\s+\S+"
    r")"
)
_KEY_ASSIGN_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|key|token|secret|authorization)\b\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)


def normalize_openai_model_id(model_id: str) -> str:
    """Strip leading ``models/`` / ``google/`` resource prefixes from a model id."""
    cleaned = (model_id or "").strip()
    if cleaned.lower().startswith(_MODELS_RESOURCE_PREFIX):
        stripped = cleaned[len(_MODELS_RESOURCE_PREFIX) :].strip()
        cleaned = stripped or cleaned
    cleaned = _PROVIDER_MODEL_PREFIX_RE.sub("", cleaned).strip() or cleaned
    return cleaned


def is_likely_chat_model(model_id: str) -> bool:
    """True when a listed model id looks usable for ``/chat/completions``."""
    cleaned = normalize_openai_model_id(model_id).casefold()
    if not cleaned:
        return False
    return not any(marker in cleaned for marker in _NON_CHAT_MODEL_MARKERS)


def openai_compat_url(base_url: str, suffix: str) -> str:
    """Join ``base_url`` + ``suffix`` without a double slash (trailing slash safe)."""
    base = (base_url or "").strip().rstrip("/")
    path = (suffix or "").strip().lstrip("/")
    if not base:
        return f"/{path}" if path else ""
    return f"{base}/{path}" if path else base


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


def _provider_error_snippet(response: httpx.Response) -> str | None:
    """Short scrubbed provider error text for logs/UI (never secrets)."""
    raw: str | None = None
    try:
        data = response.json()
    except Exception:  # noqa: BLE001 — body may be HTML/plain
        data = None
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
            if isinstance(msg, str) and msg.strip():
                raw = msg.strip()
        elif isinstance(err, str) and err.strip():
            raw = err.strip()
        else:
            msg = data.get("message")
            if isinstance(msg, str) and msg.strip():
                raw = msg.strip()
    if raw is None:
        raw = (response.text or "").strip() or None
    if not raw:
        return None
    text = _KEY_ASSIGN_RE.sub("[redacted]", raw)
    text = _KEYISH_RE.sub("[redacted]", text)
    scrubbed = scrub_scan_text(text)
    if not scrubbed:
        return None
    return truncate_scan_text(scrubbed, limit=_PROVIDER_SNIPPET_MAX)


def _request_path_for_log(url: str) -> str:
    """Host + path only (no query/fragment) for failure logs."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "(invalid-url)"
    host = parts.netloc or ""
    path = parts.path or "/"
    return f"{host}{path}" if host else path


def _http_fail_hint(
    status_code: int,
    *,
    model: str,
    url: str,
    snippet: str | None,
) -> str:
    """Calm UI hint; only mention ``models/`` when the outbound id still has it."""
    path = _request_path_for_log(url)
    if status_code != 404:
        base = f"AI unavailable (HTTP {status_code}) — showing the heuristic line."
        if snippet:
            return f"{base} Provider: {snippet}"
        return base

    if model.lower().startswith(_MODELS_RESOURCE_PREFIX):
        hint = (
            "Model not found (404) — outbound model id still has a models/ prefix; "
            "use the bare id (gemini-…)."
        )
    else:
        hint = (
            f"Chat returned 404 for model {model!r} at {path}. "
            "Confirm the base URL ends at …/v1beta/openai (Gemini) or your "
            "provider’s OpenAI-compat root, the model supports chat, and AI "
            "settings were saved."
        )
    if snippet:
        return f"{hint} Provider: {snippet}"
    return hint


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
    url = openai_compat_url(base, "chat/completions")
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
        snippet = _provider_error_snippet(exc.response)
        outbound = model or "llama3.2"
        log.info(
            "AI scan-line skipped (HTTP %s model=%s path=%s body=%s)",
            code,
            outbound,
            _request_path_for_log(url),
            snippet or "-",
        )
        return AiScanLineResult(
            fail_hint=_http_fail_hint(
                code, model=outbound, url=url, snippet=snippet
            )
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
    url = openai_compat_url(base, "models")
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
    skipped_non_chat = 0
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str):
            continue
        cleaned = normalize_openai_model_id(model_id)
        if not cleaned or cleaned in seen:
            continue
        if not is_likely_chat_model(cleaned):
            skipped_non_chat += 1
            continue
        seen.add(cleaned)
        ids.append(cleaned)
    ids.sort(key=str.lower)
    count = len(ids)
    noun = "model" if count == 1 else "models"
    message = f"Connected · {count} {noun}"
    if skipped_non_chat:
        message = (
            f"{message} (hid {skipped_non_chat} non-chat "
            f"{'id' if skipped_non_chat == 1 else 'ids'})"
        )
    return {
        "ok": True,
        "models": ids,
        "message": message,
    }
