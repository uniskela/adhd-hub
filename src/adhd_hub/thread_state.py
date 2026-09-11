"""Helpers for outcome-scoped thread state (goal / focus / next / history)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from adhd_hub.models import Thread
from adhd_hub.overlap import jaccard, tokenize

# High bar: prefer a new thread over attaching to an unrelated open outcome.
SAFE_MATCH_MIN = 0.45
MAX_NEXT_STEPS = 3


def normalize_next_steps(value: list[str] | None) -> list[str]:
    if not value:
        return []
    cleaned: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            cleaned.append(text[:500])
        if len(cleaned) >= MAX_NEXT_STEPS:
            break
    return cleaned


def normalize_focus(value: str | None) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    return text[:500] if text else None


def normalize_optional_text(value: str | None, *, limit: int = 2000) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def outcome_blob(thread: Thread) -> str:
    parts = [
        thread.summary,
        thread.goal or "",
        thread.focus or "",
        " ".join(thread.next_steps or []),
        thread.resume_step or "",
        thread.blocked_reason or "",
    ]
    return " ".join(p for p in parts if p)


def score_outcome_match(query_parts: list[str | None], thread: Thread) -> float:
    query = " ".join(p for p in query_parts if p and str(p).strip())
    if not query.strip():
        return 0.0
    title = (thread.summary or "").strip().lower()
    if title and title == query.strip().lower():
        return 1.0
    goal = (thread.goal or "").strip().lower()
    if goal and goal == query.strip().lower():
        return 1.0
    q_tokens = tokenize(query)
    t_tokens = tokenize(outcome_blob(thread))
    score = jaccard(q_tokens, t_tokens)
    shared = {t for t in (q_tokens & t_tokens) if len(t) > 4}
    if len(shared) >= 2:
        score += 0.15
    return score


def pick_safe_matches(
    unfinished: list[Thread],
    query_parts: list[str | None],
    *,
    min_score: float = SAFE_MATCH_MIN,
) -> list[tuple[Thread, float]]:
    scored = [(t, score_outcome_match(query_parts, t)) for t in unfinished]
    return [(t, s) for t, s in scored if s >= min_score]


def state_fingerprint(thread: Thread) -> str:
    payload = {
        "summary": thread.summary,
        "status": thread.status.value,
        "goal": thread.goal or "",
        "focus": thread.focus or "",
        "next_steps": list(thread.next_steps or []),
        "blocked_reason": thread.blocked_reason or "",
        "resume_step": thread.resume_step or "",
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def milestone_text(
    *,
    thread: Thread,
    note: str | None = None,
    previous: Thread | None = None,
) -> str | None:
    """Build a short history line only when something meaningful changed."""
    note_clean = (note or "").strip()
    if previous is not None and state_fingerprint(previous) == state_fingerprint(thread) and not note_clean:
        return None
    bits: list[str] = []
    if previous is None:
        bits.append(f"Started: {thread.summary}")
    else:
        if previous.summary != thread.summary:
            bits.append(f"Title → {thread.summary}")
        if (previous.goal or "") != (thread.goal or "") and thread.goal:
            bits.append(f"Goal → {thread.goal}")
        if (previous.focus or "") != (thread.focus or "") and thread.focus:
            bits.append(f"Focus → {thread.focus}")
        if list(previous.next_steps or []) != list(thread.next_steps or []) and thread.next_steps:
            bits.append("Next → " + "; ".join(thread.next_steps))
        if (previous.blocked_reason or "") != (thread.blocked_reason or ""):
            if thread.blocked_reason:
                bits.append(f"Blocked → {thread.blocked_reason}")
            elif previous.blocked_reason:
                bits.append("Unblocked")
        if (previous.resume_step or "") != (thread.resume_step or "") and thread.resume_step:
            bits.append(f"Resume → {thread.resume_step}")
        if previous.status != thread.status:
            bits.append(f"Status → {thread.status.value}")
    if note_clean:
        # Avoid dumping unchanged Now/Done diaries as the only signal when structured
        # fields already captured the change — still record an explicit note when given.
        compact = re.sub(r"\s+", " ", note_clean)
        if compact.lower() not in {"waiting / blocked: none", "blocked: none", "none"}:
            bits.append(compact[:400])
    if not bits:
        return None
    return " — ".join(bits)[:800]


def compact_thread_dict(thread: Thread) -> dict[str, Any]:
    return {
        "id": thread.id,
        "title": thread.summary,
        "summary": thread.summary,
        "goal": thread.goal,
        "status": thread.status.value,
        "focus": thread.focus,
        "next_steps": list(thread.next_steps or []),
        "blocked_reason": thread.blocked_reason,
        "resume_step": thread.resume_step,
        "updated_at": thread.updated_at.isoformat(),
        "project_slug": thread.project_slug,
    }
