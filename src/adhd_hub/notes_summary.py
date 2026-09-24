"""Notes reader AI summarise card (v1).

Structured continuity-style card for one thread. Never rewrites progress notes.
Persisted separately (store meta) so reopen keeps the last card until regenerate.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from adhd_hub.clarity import scrub_scan_text, truncate_scan_text

NOTES_SUMMARY_SOURCE_AI = "ai"

# Field caps — calm, scannable, not a transcript dump.
_DONE_MAX = 280
_PLAN_FOCUS_MAX = 280
_NEXT_ITEM_MAX = 160
_BLOCKED_MAX = 200
_RESUME_MAX = 200
_NEXT_MAX_ITEMS = 3

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


@dataclass(frozen=True)
class NotesSummaryCard:
    """Replaceable AI summary card (not Hub Goal/Focus fields)."""

    done: str | None = None
    plan_focus: str | None = None
    next_steps: list[str] = field(default_factory=list)
    blocked: str | None = None
    resume: str | None = None
    source: str = NOTES_SUMMARY_SOURCE_AI
    updated_at: str | None = None

    def has_content(self) -> bool:
        return bool(
            self.done
            or self.plan_focus
            or self.next_steps
            or self.blocked
            or self.resume
        )

    def to_store_dict(self) -> dict[str, Any]:
        return {
            "done": self.done,
            "plan_focus": self.plan_focus,
            "next": list(self.next_steps[:_NEXT_MAX_ITEMS]),
            "blocked": self.blocked,
            "resume": self.resume,
            "source": self.source,
            "updated_at": self.updated_at or datetime.now(UTC).isoformat(),
        }


def notes_summary_cache_key(thread_id: str) -> str:
    return f"notes_summary:{thread_id}"


def _clean_field(value: object | None, *, limit: int) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return None
    text = scrub_scan_text(str(value))
    if not text:
        return None
    return truncate_scan_text(text, limit=limit)


def _clean_next(raw: object | None) -> list[str]:
    items: list[str] = []
    if isinstance(raw, str):
        # Split on newlines or numbered bullets.
        parts = re.split(r"[\n;]+", raw)
        candidates = parts
    elif isinstance(raw, list):
        candidates = raw
    else:
        return []
    for item in candidates:
        cleaned = _clean_field(item, limit=_NEXT_ITEM_MAX)
        if cleaned and cleaned not in items:
            items.append(cleaned)
        if len(items) >= _NEXT_MAX_ITEMS:
            break
    return items


def parse_notes_summary_payload(raw: object | None) -> NotesSummaryCard | None:
    """Parse a store dict or AI JSON object into a card; None if empty/invalid."""
    if not isinstance(raw, dict):
        return None
    done = _clean_field(raw.get("done") or raw.get("Done"), limit=_DONE_MAX)
    plan = _clean_field(
        raw.get("plan_focus")
        or raw.get("Plan·Focus")
        or raw.get("focus")
        or raw.get("plan"),
        limit=_PLAN_FOCUS_MAX,
    )
    next_steps = _clean_next(raw.get("next") or raw.get("Next") or raw.get("next_steps"))
    blocked = _clean_field(
        raw.get("blocked") or raw.get("Blocked") or raw.get("blocked_reason"),
        limit=_BLOCKED_MAX,
    )
    resume = _clean_field(
        raw.get("resume") or raw.get("Resume") or raw.get("resume_step"),
        limit=_RESUME_MAX,
    )
    source = str(raw.get("source") or NOTES_SUMMARY_SOURCE_AI).strip() or NOTES_SUMMARY_SOURCE_AI
    updated = raw.get("updated_at")
    updated_at = str(updated).strip() if isinstance(updated, str) and updated.strip() else None
    card = NotesSummaryCard(
        done=done,
        plan_focus=plan,
        next_steps=next_steps,
        blocked=blocked,
        resume=resume,
        source=source,
        updated_at=updated_at,
    )
    return card if card.has_content() else None


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort extract of a JSON object from model output."""
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    fence = _JSON_FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    # Prefer outermost braces.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    snippet = cleaned[start : end + 1]
    try:
        data = json.loads(snippet)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def notes_summary_reject_reason(card: NotesSummaryCard | None) -> str | None:
    """Calm fail hint when an AI summary should not be cached."""
    if card is None or not card.has_content():
        return "AI summary was empty after scrubbing — notes unchanged."
    # Require at least one of Done / Plan·Focus / Next so the card is useful.
    if not (card.done or card.plan_focus or card.next_steps):
        return "AI summary lacked Done, Plan·Focus, or Next — notes unchanged."
    return None


def card_from_ai_text(content: str) -> tuple[NotesSummaryCard | None, str | None]:
    """Parse + gate AI text; return (card, reject_reason)."""
    data = extract_json_object(content)
    if data is None:
        return None, "AI reply was not usable JSON — notes unchanged."
    card = parse_notes_summary_payload(data)
    reject = notes_summary_reject_reason(card)
    if reject:
        return None, reject
    assert card is not None
    return (
        NotesSummaryCard(
            done=card.done,
            plan_focus=card.plan_focus,
            next_steps=card.next_steps,
            blocked=card.blocked,
            resume=card.resume,
            source=NOTES_SUMMARY_SOURCE_AI,
            updated_at=datetime.now(UTC).isoformat(),
        ),
        None,
    )


def notes_summary_card_html(card: NotesSummaryCard) -> str:
    """Render the AI summary card for the notes reader (escaped plain text)."""
    from html import escape

    if not card.has_content():
        return ""

    blocks: list[str] = [
        (
            '<header class="notes-summary-head">'
            + '<p class="notes-summary-eyebrow">AI summary</p>'
            + '<p class="notes-summary-hint">Does not change saved notes or Goal / Focus fields.</p>'
            + "</header>"
        )
    ]

    def field(label: str, html: str) -> str:
        return (
            f'<div class="notes-continuity-field">'
            f'<p class="notes-continuity-label">{escape(label)}</p>'
            f'<div class="notes-continuity-value">{html}</div>'
            f"</div>"
        )

    if card.done:
        blocks.append(field("Done", f"<p>{escape(card.done)}</p>"))
    if card.plan_focus:
        blocks.append(field("Plan · Focus", f"<p>{escape(card.plan_focus)}</p>"))
    if card.next_steps:
        items = "".join(f"<li>{escape(step)}</li>" for step in card.next_steps[:_NEXT_MAX_ITEMS])
        blocks.append(field("Next", f"<ol>{items}</ol>"))
    if card.blocked:
        blocks.append(field("Blocked", f"<p>{escape(card.blocked)}</p>"))
    if card.resume:
        blocks.append(field("Resume", f"<p>{escape(card.resume)}</p>"))

    return f'<section class="notes-summary-card" aria-label="AI summary">{"".join(blocks)}</section>'
