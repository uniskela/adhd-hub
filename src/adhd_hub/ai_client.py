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

from adhd_hub.clarity import (
    SCAN_LINE_MAX,
    ai_scan_line_reject_reason,
    build_scan_line,
    scrub_scan_text,
    truncate_scan_text,
)
from adhd_hub.config import Settings
from adhd_hub.models import Thread
from adhd_hub.notes_compaction import is_boilerplate_freeform

log = logging.getLogger(__name__)

# Gemini OpenAI-compat ``GET /models`` returns ids like ``models/gemini-2.5-flash``,
# but ``POST /chat/completions`` expects the bare id (``gemini-2.5-flash``).
_MODELS_RESOURCE_PREFIX = "models/"

# Provider/model refs some UIs prepend (e.g. ``google/gemini-2.5-flash``).
_PROVIDER_MODEL_PREFIX_RE = re.compile(r"^google/", re.IGNORECASE)

# Current Gemini flash id for new users (list may still advertise older flash ids).
PREFERRED_GEMINI_FLASH = "gemini-3.6-flash"

# Known Gemini chat ids that 404 for new users while still appearing in ``/models``.
_GEMINI_DEPRECATED_FOR_NEW_USERS = frozenset(
    {
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-preview-05-20",
        "gemini-2.5-flash-preview-04-17",
    }
)

_DEPRECATED_MODEL_HINT_RE = re.compile(
    r"no longer available|deprecated for new users|not available to new",
    re.IGNORECASE,
)

# Room for one complete ~80–140 char sentence (tokens ≠ chars; keep headroom).
_SCAN_LINE_MAX_TOKENS = 220

# Keep AI prompts tiny — huge forge/ritual resume walls cause provider timeouts.
_PROMPT_TITLE_MAX = 80
_PROMPT_FIELD_MAX = 120
_PROMPT_WALL_CHARS = 400
_PROMPT_WALL_LINES = 3
_PROMPT_WALL_EMDASHES = 3

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


def is_gemini_deprecated_for_new_users(
    model_id: str,
    *,
    description: str | None = None,
) -> bool:
    """True when a Gemini id is known-dead for new users or described as unavailable."""
    cleaned = normalize_openai_model_id(model_id).casefold()
    if not cleaned:
        return False
    if cleaned in _GEMINI_DEPRECATED_FOR_NEW_USERS:
        return True
    blob = f"{cleaned} {description or ''}"
    if "gemini" not in blob.casefold():
        return False
    return bool(_DEPRECATED_MODEL_HINT_RE.search(blob))


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


def _raw_looks_like_ritual_wall(text: str) -> bool:
    """True when a continuity field looks like forge/agent ritual dump, not a resume."""
    if len(text) > _PROMPT_WALL_CHARS:
        return True
    if text.count("\n") >= _PROMPT_WALL_LINES:
        return True
    if text.count("—") >= _PROMPT_WALL_EMDASHES:
        return True
    low = text.casefold()
    return (
        "thread upserted from" in low
        or "source_conflicts" in low
        or "checkpointed from" in low
    )


def _first_usable_prompt_line(text: str) -> str | None:
    for line in text.splitlines():
        cleaned = line.strip().lstrip("#*-• ").strip()
        if cleaned and not is_boilerplate_freeform(cleaned):
            return cleaned
    first = text.strip().split("\n", 1)[0].strip()
    return first or None


def _sanitize_prompt_field(value: str | None, *, limit: int) -> str | None:
    """Scrub + tightly cap one continuity field for the AI prompt (never forge walls)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if is_boilerplate_freeform(text):
        return None
    if _raw_looks_like_ritual_wall(text):
        text = _first_usable_prompt_line(text) or ""
        if not text or is_boilerplate_freeform(text) or _raw_looks_like_ritual_wall(text):
            return None
    cleaned = scrub_scan_text(text)
    if not cleaned:
        return None
    return truncate_scan_text(cleaned, limit=limit)


def _hub_preferred_field(thread: Thread, name: str, current: str | None) -> str | None:
    """Prefer Hub side of a forge conflict; never feed forge conflict blobs to AI."""
    conflict = (thread.source_conflicts or {}).get(name)
    if not isinstance(conflict, dict):
        return current
    hub = conflict.get("hub")
    if isinstance(hub, str) and hub.strip():
        return hub
    # Conflict present but no usable Hub value — skip rather than using forge text.
    forge = conflict.get("forge")
    if isinstance(forge, str) and forge.strip():
        return None
    return current


def _next_steps_for_prompt(thread: Thread) -> str | None:
    raw_steps = thread.next_steps[:2] if thread.next_steps else []
    conflict = (thread.source_conflicts or {}).get("next_steps")
    if isinstance(conflict, dict):
        hub = conflict.get("hub")
        if isinstance(hub, list):
            raw_steps = [str(s) for s in hub[:2] if str(s).strip()]
        elif isinstance(hub, str) and hub.strip():
            raw_steps = [hub]
        elif conflict.get("forge") is not None:
            raw_steps = []
    parts: list[str] = []
    for step in raw_steps:
        cleaned = _sanitize_prompt_field(step, limit=_PROMPT_FIELD_MAX)
        if cleaned:
            parts.append(cleaned)
    if not parts:
        return None
    return "; ".join(parts)


def structured_scan_prompt(thread: Thread) -> str:
    """Build a small, scrubbed continuity prompt (no forge conflict / ritual walls)."""
    parts = [
        "Write one complete calm ADHD-friendly scan line for this Hub thread.",
        "Target about 80–140 characters as one finished scannable sentence.",
        "Do not truncate mid-phrase; finish the thought. Prefer a full clause over a stub.",
        "Use only the structured fields below. No secrets, paths, URLs, or transcripts.",
        "Return plain text only — no quotes, labels, or markdown.",
    ]
    fields = [
        ("Title", _hub_preferred_field(thread, "summary", thread.summary), _PROMPT_TITLE_MAX),
        ("Focus", _hub_preferred_field(thread, "focus", thread.focus), _PROMPT_FIELD_MAX),
        (
            "Resume",
            _hub_preferred_field(thread, "resume_step", thread.resume_step),
            _PROMPT_FIELD_MAX,
        ),
        ("Goal", _hub_preferred_field(thread, "goal", thread.goal), _PROMPT_FIELD_MAX),
        ("Next", _next_steps_for_prompt(thread), _PROMPT_FIELD_MAX * 2),
        (
            "Blocked",
            _hub_preferred_field(thread, "blocked_reason", thread.blocked_reason),
            _PROMPT_FIELD_MAX,
        ),
    ]
    for label, value, limit in fields:
        # Redact before crossing the provider boundary. Never send source_conflicts,
        # progress bodies, or transcript references.
        if label == "Next":
            cleaned = value if isinstance(value, str) else None
            if cleaned:
                cleaned = truncate_scan_text(cleaned, limit=limit)
        else:
            cleaned = _sanitize_prompt_field(value, limit=limit)
        if cleaned:
            parts.append(f"{label}: {cleaned}")
    return "\n".join(parts)


def _structured_prompt(thread: Thread) -> str:
    return structured_scan_prompt(thread)


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
    elif snippet and _DEPRECATED_MODEL_HINT_RE.search(snippet):
        hint = (
            f"Model {model!r} is no longer available for new users. "
            f"Try {PREFERRED_GEMINI_FLASH} (or another current Gemini flash id)."
        )
    else:
        hint = (
            f"Chat returned 404 for model {model!r} at {path}. "
            "Confirm the base URL ends at …/v1beta/openai (Gemini) or your "
            "provider’s OpenAI-compat root, the model supports chat, and AI "
            "settings were saved."
        )
        if "gemini" in model.casefold():
            hint = (
                f"{hint} For Gemini, prefer {PREFERRED_GEMINI_FLASH} when older "
                "flash ids 404."
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
        "max_tokens": _SCAN_LINE_MAX_TOKENS,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You rewrite Hub continuity into one complete calm scan line "
                    "(about 80–140 characters). Finish the sentence; never return "
                    "a stub or truncated phrase. Never invent secrets, absolute "
                    "paths, or private URLs. Plain text only."
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
        line = truncate_scan_text(cleaned, limit=SCAN_LINE_MAX)
        heuristic, _ = build_scan_line(thread)
        reject = ai_scan_line_reject_reason(line, heuristic=heuristic)
        if reject:
            return AiScanLineResult(fail_hint=reject)
        return AiScanLineResult(text=line)
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
    skipped_deprecated = 0
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
        description = item.get("description") or item.get("display_name")
        desc = description if isinstance(description, str) else None
        if is_gemini_deprecated_for_new_users(cleaned, description=desc):
            skipped_deprecated += 1
            continue
        seen.add(cleaned)
        ids.append(cleaned)
    ids.sort(key=str.lower)
    count = len(ids)
    noun = "model" if count == 1 else "models"
    message = f"Connected · {count} {noun}"
    extras: list[str] = []
    if skipped_non_chat:
        extras.append(
            f"hid {skipped_non_chat} non-chat "
            f"{'id' if skipped_non_chat == 1 else 'ids'}"
        )
    if skipped_deprecated:
        extras.append(
            f"hid {skipped_deprecated} deprecated-for-new-users "
            f"{'id' if skipped_deprecated == 1 else 'ids'}; "
            f"prefer {PREFERRED_GEMINI_FLASH}"
        )
    if extras:
        message = f"{message} ({'; '.join(extras)})"
    return {
        "ok": True,
        "models": ids,
        "message": message,
    }
