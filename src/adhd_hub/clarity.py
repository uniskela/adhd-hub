"""Wave 6 clarity helpers — short scannable scan-lines for threads.

Heuristic summaries are derived from structured continuity fields only
(focus / resume / goal / next / safe progress snippets). Never invent from
transcripts. Callers must still avoid putting secrets in stored fields;
this module redacts common leak shapes before display.
"""

from __future__ import annotations

import re
from typing import Any

from adhd_hub.models import Thread

SCAN_LINE_MAX = 140
SCAN_LINE_SOURCE_HEURISTIC = "heuristic"

_SECRET_INLINE_RE = re.compile(
    r"(?i)\b[\w-]*(?:password|passwd|secret|token|api[_-]?key|authorization|"
    r"credential|private[_-]?key)\b[\"']?\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_AUTH_RE = re.compile(r"(?i)\b(?:bearer|basic)\s+[^\s,;\"']+")
_ABS_PATH_RE = re.compile(
    r"(^|[\s\"'`=(\[])"
    r"(/[^\s\"'`\])]+|\\\\[^\s\"'`\])]+|[A-Za-z]:[\\/][^\s\"'`\])]+)"
)
_URL_RE = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)
_LOCALHOST_HOST_RE = re.compile(
    r"(^|://)(localhost|127\.0\.0\.1|0\.0\.0\.0|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|"
    r"172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+|100\.\d+\.\d+\.\d+)(:|/|$)",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")


def scrub_scan_text(value: str | None) -> str | None:
    """Return display-safe text, or None if nothing usable remains."""
    if value is None:
        return None
    text = _WHITESPACE_RE.sub(" ", str(value)).strip()
    if not text:
        return None
    text = _AUTH_RE.sub("[redacted]", text)
    text = _SECRET_INLINE_RE.sub("[redacted]", text)
    text = _ABS_PATH_RE.sub(lambda m: f"{m.group(1)}[path]", text)
    def _url_sub(match: re.Match[str]) -> str:
        url = match.group(0)
        if _LOCALHOST_HOST_RE.search(url) or "tailscale" in url.casefold():
            return "[private-url]"
        return "[url]"

    text = _URL_RE.sub(_url_sub, text)
    text = _WHITESPACE_RE.sub(" ", text).strip(" -|;,")
    if not text or text in {"[redacted]", "[path]", "[private-url]", "[url]"}:
        return None
    return text


def _truncate(text: str, *, limit: int = SCAN_LINE_MAX) -> str:
    if len(text) <= limit:
        return text
    cut = text[: max(0, limit - 1)].rstrip()
    # Prefer breaking on a word boundary when close to the end.
    if " " in cut[ max(0, len(cut) - 24) :]:
        cut = cut.rsplit(" ", 1)[0].rstrip()
    return f"{cut}…"


def build_scan_line(
    thread: Thread,
    *,
    progress_snippet: str | None = None,
    max_len: int = SCAN_LINE_MAX,
) -> tuple[str | None, str | None]:
    """Build a heuristic scan-line and its source label.

    Priority: focus → resume_step → goal → first next_steps → progress_snippet.
    Returns ``(scan_line, source)`` where source is ``heuristic`` when a line
    is produced, else ``(None, None)``.
    """
    candidates: list[str | None] = [
        thread.focus,
        thread.resume_step,
        thread.goal,
        (thread.next_steps[0] if thread.next_steps else None),
        progress_snippet,
    ]
    for raw in candidates:
        cleaned = scrub_scan_text(raw)
        if not cleaned:
            continue
        return _truncate(cleaned, limit=max_len), SCAN_LINE_SOURCE_HEURISTIC
    return None, None


def attach_scan_line(
    data: dict[str, Any], thread: Thread, *, progress_snippet: str | None = None
) -> dict[str, Any]:
    """Mutate a public thread dict with scan_line fields; return the same dict."""
    line, source = build_scan_line(
        thread, progress_snippet=progress_snippet
    )
    data["scan_line"] = line
    data["scan_line_source"] = source
    return data
