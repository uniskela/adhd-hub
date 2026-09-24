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
SCAN_LINE_MIN_CHARS = 24
SCAN_LINE_MIN_WORDS = 4
SCAN_LINE_SOURCE_HEURISTIC = "heuristic"
SCAN_LINE_SOURCE_AI = "ai"

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
# Markdown **bold** only — never unwrap __dunder__ tokens.
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
# Single-asterisk italics with word boundaries (skips globs like test_* / *.py).
_MD_ITALIC_RE = re.compile(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)")
# Orphan emphasis left by truncation — edges only; keep globs like test_* / *.py.
_MD_ORPHAN_LEADING_RE = re.compile(r"^\*{1,3}")
_MD_ORPHAN_TRAILING_RE = re.compile(r"\*{2,3}$|(?<=\s)\*$")
# Clear incomplete cut-offs only — omit on/in/from (valid “log in” / “move on”).
_MID_PHRASE_ENDERS = frozenset(
    {
        "a",
        "an",
        "and",
        "for",
        "into",
        "of",
        "or",
        "the",
        "to",
        "with",
        "without",
    }
)


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
    text = _MD_BOLD_RE.sub(r"\1", text)
    text = _MD_ITALIC_RE.sub(r"\1", text)
    text = _MD_ORPHAN_LEADING_RE.sub("", text)
    text = _MD_ORPHAN_TRAILING_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip(" -|;,")
    if not text or text in {"[redacted]", "[path]", "[private-url]", "[url]"}:
        return None
    alnum = sum(1 for ch in text if ch.isalnum())
    if alnum < 2 or alnum / max(len(text), 1) < 0.35:
        return None
    return text


def scan_line_word_count(text: str) -> int:
    return len([part for part in text.split() if any(ch.isalnum() for ch in part)])


def ends_mid_phrase(text: str) -> bool:
    """True when the line looks cut off mid-thought (e.g. ends with \"to\")."""
    stripped = text.rstrip()
    # Complete sentences with terminal punctuation are never mid-phrase cuts.
    if stripped.endswith((".", "!", "?")):
        return False
    cleaned = stripped.rstrip(" …")
    if not cleaned:
        return True
    last = cleaned.rsplit(None, 1)[-1].casefold().strip("\"'`")
    return last in _MID_PHRASE_ENDERS


def ai_scan_line_reject_reason(
    text: str,
    *,
    heuristic: str | None = None,
) -> str | None:
    """Return a calm fail hint when an AI scan line should not be cached."""
    cleaned = (text or "").strip()
    if not cleaned:
        return "AI reply was empty after scrubbing — showing the heuristic line."
    words = scan_line_word_count(cleaned)
    if len(cleaned) < SCAN_LINE_MIN_CHARS or words < SCAN_LINE_MIN_WORDS:
        return "AI reply too short — showing the heuristic line."
    if ends_mid_phrase(cleaned):
        return "AI reply looked incomplete — showing the heuristic line."
    alnum = sum(1 for ch in cleaned if ch.isalnum())
    if alnum / max(len(cleaned), 1) < 0.5:
        return "AI reply too short — showing the heuristic line."
    if heuristic:
        heur = heuristic.strip()
        # Prefer heuristic when AI is much shorter for the same fields.
        if len(heur) >= SCAN_LINE_MIN_CHARS and len(cleaned) * 2 < len(heur):
            return "AI reply too short — showing the heuristic line."
    return None


def truncate_scan_text(text: str, *, limit: int = SCAN_LINE_MAX) -> str:
    if len(text) <= limit:
        return text
    cut = text[: max(0, limit - 1)].rstrip()
    if " " in cut[ max(0, len(cut) - 24) :]:
        cut = cut.rsplit(" ", 1)[0].rstrip()
    return f"{cut}…"


def _truncate(text: str, *, limit: int = SCAN_LINE_MAX) -> str:
    return truncate_scan_text(text, limit=limit)


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
    data: dict[str, Any],
    thread: Thread,
    *,
    progress_snippet: str | None = None,
    cached_line: str | None = None,
    cached_source: str | None = None,
    cached_fingerprint: str | None = None,
    fingerprint: str | None = None,
) -> dict[str, Any]:
    """Mutate a public thread dict with scan_line fields; return the same dict.

    Prefer a fingerprint-matched AI/heuristic cache entry when provided; otherwise
    compute a heuristic line. Does not call remote AI itself (service owns that).
    """
    if (
        cached_line
        and fingerprint
        and cached_fingerprint
        and fingerprint == cached_fingerprint
    ):
        data["scan_line"] = cached_line
        data["scan_line_source"] = cached_source or SCAN_LINE_SOURCE_HEURISTIC
        return data
    line, source = build_scan_line(
        thread, progress_snippet=progress_snippet
    )
    data["scan_line"] = line
    data["scan_line_source"] = source
    return data
