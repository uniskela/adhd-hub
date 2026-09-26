"""Calm cross-project Next-up ranking (Wave 7 / #54).

Picks one unfinished open thread for “what now?” — stale + resume-first,
optional energy match, optional focus-project preference (honour drift /
focus mode). Never auto-starts work; never dismisses.
"""

from __future__ import annotations

from datetime import UTC, datetime

from adhd_hub.models import EnergyLevel, Thread

_ENERGY_CALM_ORDER = {
    EnergyLevel.low: 0,
    EnergyLevel.unknown: 1,
    EnergyLevel.medium: 2,
    EnergyLevel.high: 3,
}


def next_up_sort_key(
    thread: Thread,
    *,
    stale_ids: set[str],
    prefer_energy: EnergyLevel | None = None,
    focus_project_slug: str | None = None,
) -> tuple:
    """Lower tuple sorts first (better Next-up candidate)."""
    focus = (focus_project_slug or "").strip()
    same_focus = 0 if focus and (thread.project_slug or "") == focus else (0 if not focus else 1)
    if prefer_energy is not None:
        energy_key = 0 if thread.energy == prefer_energy else 1
    else:
        energy_key = _ENERGY_CALM_ORDER.get(thread.energy, 1)
    updated = thread.updated_at.replace(tzinfo=UTC) if thread.updated_at.tzinfo is None else thread.updated_at
    return (
        same_focus,
        0 if thread.id in stale_ids else 1,
        0 if (thread.resume_step or "").strip() else 1,
        energy_key,
        updated,
        thread.id,
    )


def rank_next_up(
    threads: list[Thread],
    *,
    stale_ids: set[str] | None = None,
    prefer_energy: EnergyLevel | None = None,
    focus_project_slug: str | None = None,
    limit: int = 1,
) -> list[Thread]:
    """Rank open threads for Next-up; return up to ``limit`` (best first)."""
    if not threads:
        return []
    ids = stale_ids or set()
    ranked = sorted(
        threads,
        key=lambda t: next_up_sort_key(
            t,
            stale_ids=ids,
            prefer_energy=prefer_energy,
            focus_project_slug=focus_project_slug,
        ),
    )
    return ranked[: max(1, int(limit))]


def pick_next_up(
    threads: list[Thread],
    *,
    stale_ids: set[str] | None = None,
    prefer_energy: EnergyLevel | None = None,
    focus_project_slug: str | None = None,
) -> Thread | None:
    """Single calm Next-up pick, or None when there is no open work."""
    ranked = rank_next_up(
        threads,
        stale_ids=stale_ids,
        prefer_energy=prefer_energy,
        focus_project_slug=focus_project_slug,
        limit=1,
    )
    return ranked[0] if ranked else None


def is_stale_for_next_up(
    thread: Thread,
    *,
    stale_cutoff: datetime,
) -> bool:
    """Quiet unfinished work for ranking (no snooze/remind filters)."""
    updated = thread.updated_at.replace(tzinfo=UTC) if thread.updated_at.tzinfo is None else thread.updated_at
    return updated <= stale_cutoff
