"""Notes feed compaction: classify, scrub ritual content, coalesce milestones."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

# Agent ceremony often stuffed into upsert_progress `content` — not ADHD-readable.
_BOILERPLATE_FREEFORM_RE = re.compile(
    r"^(?:"
    r"thread\s+upserted\s+from\b|"
    r"checkpoint(?:ed)?\s+from\b|"
    r"progress\s+(?:update|note)\s+from\b|"
    r"upsert(?:ed)?\s+from\b|"
    r"autosave\s+from\b"
    r")",
    re.IGNORECASE,
)

_FIELD_BIT_RE = re.compile(
    r"^(?:Title|Goal|Focus|Next|Blocked|Resume|Status)\s*→|^Unblocked$|^Started:\s",
    re.IGNORECASE,
)

_FIELD_LABEL_RE = re.compile(
    r"^(Title|Goal|Focus|Next|Blocked|Resume|Status)\s*→",
    re.IGNORECASE,
)

_STARTED_RE = re.compile(r"^Started:\s", re.IGNORECASE)

# Default UI: keep a short recent window open; older stays recoverable.
NOTES_VISIBLE_ITEMS = 5
NOTES_HIGH_COUNT = 8
DEDUP_WINDOW_SECONDS = 300


def _bits(content: str) -> list[str]:
    text = re.sub(r"\s+", " ", (content or "").strip())
    if not text:
        return []
    return [b.strip() for b in text.split(" — ") if b.strip()]


def is_boilerplate_freeform(text: str | None) -> bool:
    """True when freeform `content` is ritual agent narration."""
    compact = re.sub(r"\s+", " ", (text or "").strip())
    if not compact:
        return False
    if _BOILERPLATE_FREEFORM_RE.match(compact):
        return True
    # Whole milestone line that is only ritual after field bits were stripped.
    bits = _bits(compact)
    return bool(bits and all(_BOILERPLATE_FREEFORM_RE.match(b) for b in bits))


def scrub_progress_content(content: str | None) -> str | None:
    """Drop ritual freeform content; keep human-meaningful notes."""
    if content is None:
        return None
    text = str(content).strip()
    if not text:
        return None
    if is_boilerplate_freeform(text):
        return None
    return text


def is_field_change_bit(bit: str) -> bool:
    return bool(_FIELD_BIT_RE.match((bit or "").strip()))


def is_milestone_note(content: str | None) -> bool:
    """True when content looks like Hub milestone_text / system checkpoint output.

    Full-line ritual freeform (e.g. Codex ``Thread upserted from … — Title — Desc``)
    is milestone even when em-dash title/description bits are not field changes —
    otherwise historical ritual walls stay classified as human and never coalesce.
    """
    if is_boilerplate_freeform(content):
        return True
    bits = _bits(content or "")
    if not bits:
        return False
    fieldish = sum(1 for b in bits if is_field_change_bit(b))
    boilerplate = sum(1 for b in bits if _BOILERPLATE_FREEFORM_RE.match(b))
    if fieldish >= 1:
        # Milestone with optional ritual tail.
        return fieldish + boilerplate == len(bits) or fieldish >= len(bits) / 2
    return boilerplate == len(bits)


def milestone_field_chips(content: str | None) -> list[str]:
    """Ordered unique field labels from a milestone line (for change chips)."""
    seen: set[str] = set()
    chips: list[str] = []
    for bit in _bits(content or ""):
        m = _FIELD_LABEL_RE.match(bit)
        if m:
            label = m.group(1).capitalize()
            if label == "Title":
                label = "Title"
            key = label.lower()
            if key not in seen:
                seen.add(key)
                chips.append(label)
            continue
        if bit.strip().lower() == "unblocked" and "unblocked" not in seen:
            seen.add("unblocked")
            chips.append("Unblocked")
        elif _STARTED_RE.match(bit) and "started" not in seen:
            seen.add("started")
            chips.append("Started")
    return chips


def structural_core(content: str | None) -> str:
    """Field-change bits only — ignores ritual freeform tails for near-dedup."""
    keep = [
        b
        for b in _bits(content or "")
        if is_field_change_bit(b) and not _BOILERPLATE_FREEFORM_RE.match(b)
    ]
    return " — ".join(keep)


def _parse_created_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value))
    except Exception:  # noqa: BLE001
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp


def should_skip_duplicate_note(
    new_note: str,
    recent: list[dict[str, Any]],
    *,
    window_seconds: int = DEDUP_WINDOW_SECONDS,
    now: datetime | None = None,
) -> bool:
    """Skip insert when exact match or near-duplicate milestone within a short window.

    Never skips when the new note's structural field core differs from recent
    notes (distinct Goal/Focus/Resume changes always land).
    """
    text = (new_note or "").strip()
    if not text or not recent:
        return False
    last = recent[0]
    last_content = (last.get("content") or "").strip()
    if last_content == text:
        return True

    new_core = structural_core(text)
    # Pure ritual / empty structural with no human body: treat as noise if last
    # note shares the same (empty or equal) core within the window.
    if not new_core and is_milestone_note(text):
        # Only scrub-level noise left; skip if last is also milestone noise.
        if is_milestone_note(last_content) and not structural_core(last_content):
            return _within_window(last, window_seconds, now=now)
        if last_content == text:
            return True

    if not new_core:
        # Human freeform — never near-dedup against milestones; exact already handled.
        return False

    for row in recent[:5]:
        old = (row.get("content") or "").strip()
        if not old:
            continue
        if structural_core(old) != new_core:
            continue
        if not is_milestone_note(old) and not is_milestone_note(text):
            continue
        if _within_window(row, window_seconds, now=now):
            return True
    return False


def _within_window(
    row: dict[str, Any],
    window_seconds: int,
    *,
    now: datetime | None = None,
) -> bool:
    created = _parse_created_at(row.get("created_at"))
    if created is None:
        return True  # conservative: treat missing stamp as coalescable
    ref = now or datetime.now(UTC)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=UTC)
    try:
        return abs((ref - created).total_seconds()) <= window_seconds
    except Exception:  # noqa: BLE001
        return True


def coalesce_notes_feed(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group consecutive similar milestones (newest-first list).

    Returns items:
      {"kind": "single", "note": dict, "milestone": bool}
      {"kind": "group", "notes": [newest…oldest], "count": N, "latest": dict, "chips": [...]}
    """
    items: list[dict[str, Any]] = []
    bucket: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal bucket
        if not bucket:
            return
        if len(bucket) == 1:
            note = bucket[0]
            items.append(
                {
                    "kind": "single",
                    "note": note,
                    "milestone": is_milestone_note(note.get("content")),
                }
            )
        else:
            latest = bucket[0]
            chips = milestone_field_chips(latest.get("content"))
            # Prefer chips from any note in the group if latest is chip-less ritual.
            if not chips:
                for n in bucket:
                    chips = milestone_field_chips(n.get("content"))
                    if chips:
                        break
            items.append(
                {
                    "kind": "group",
                    "notes": list(bucket),
                    "count": len(bucket),
                    "latest": latest,
                    "chips": chips,
                }
            )
        bucket = []

    for note in notes:
        content = note.get("content") or ""
        if is_milestone_note(content):
            bucket.append(note)
            continue
        flush()
        items.append({"kind": "single", "note": note, "milestone": False})
    flush()
    return items


def default_open_thread_notes(
    notes: list[dict[str, Any]],
    *,
    high_count: int = NOTES_HIGH_COUNT,
) -> bool:
    """Open Thread notes when few notes or clearly human; collapse milestone walls."""
    if not notes:
        return False
    human = sum(1 for n in notes if not is_milestone_note(n.get("content")))
    total = len(notes)
    if total <= 3 and (human > 0 or total <= 2):
        return True
    if human >= 1 and human >= max(1, total * 0.3):
        return True
    if total >= high_count:
        return False
    if human == 0 and total > 3:
        return False
    return human > 0


def is_boilerplate_progress_snippet(snippet: str | None) -> bool:
    """True when Copy-agent Progress would only repeat milestone/boilerplate noise."""
    text = (snippet or "").strip()
    if not text:
        return True
    return is_boilerplate_freeform(text) or is_milestone_note(text)


def group_summary_label(item: dict[str, Any]) -> str:
    """One-line summary for a coalesced checkpoint group."""
    count = int(item.get("count") or 0)
    latest = item.get("latest") or {}
    content = (latest.get("content") or "").strip()
    core = structural_core(content)
    last = core or content
    if len(last) > 120:
        last = last[:117] + "…"
    noun = "checkpoint" if count == 1 else "checkpoints"
    if last:
        return f"{count} {noun} · last: {last}"
    return f"{count} {noun}"
