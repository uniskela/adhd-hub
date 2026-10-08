"""Global advisory Clock-Off windows; all comparisons use UTC instants."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from adhd_hub.timeutil import ensure_aware_utc, resolve_zone, to_iso_utc


class ClockOffSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    active_days: list[Annotated[int, Field(strict=True, ge=0, le=6)]] = [0, 1, 2, 3, 4]
    clock_off_time: str = Field(default="22:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    wind_down_minutes: int = Field(default=15, strict=True, ge=0, le=240)

    @field_validator("active_days")
    @classmethod
    def normalize_days(cls, days: list[int]) -> list[int]:
        return sorted(set(days))


class ClockOffState(BaseModel):
    enabled: bool = False
    state: Literal["normal", "winding_down", "clocked_off", "overridden"] = "normal"
    timezone: str = "UTC"
    clock_off_at: str | None = None
    wind_down_at: str | None = None
    resumes_at: str | None = None
    minutes_remaining: int | None = None
    override_until: str | None = None
    guidance: list[str] = []


_GUIDANCE = {
    "winding_down": [
        (
            "Clock-Off is approaching. Avoid substantial new work, broad tasks, refactors, "
            "audits, new PRs and unrelated debugging; keep scope small."
        ),
        (
            "Finish the current small safe step where practical, then use upsert_progress "
            "to checkpoint and pause_thread with a concrete resume step."
        ),
        (
            "Mention the approaching boundary once, calmly. This is advisory; the user "
            "can explicitly override temporarily and remains in control."
        ),
    ],
    "clocked_off": [
        (
            "Clock-Off is active. Avoid starting substantial new work; limit work to "
            "trivial or necessary safe wrap-up unless the user explicitly overrides."
        ),
        (
            "Use upsert_progress to checkpoint unfinished work, then pause_thread with "
            "a concrete resume step and give a short safely parked summary."
        ),
        (
            "This is advisory, with no forced shutdown or mandatory Continuity Guard. "
            "The user remains in control; avoid repeated reminders."
        ),
    ],
    "overridden": [
        (
            "The user explicitly overrode Clock-Off temporarily. Respect their choice; "
            "scheduled advisory guidance resumes when override_until expires."
        ),
    ],
}


def _local_instant(day: date, clock: time, zone: ZoneInfo) -> datetime:
    # First occurrence in a fold; a missing wall time moves forward by the DST gap.
    local = datetime.combine(day, clock, tzinfo=zone).replace(fold=0)
    return local.astimezone(UTC)


def clock_off_state(
    schedule: ClockOffSchedule,
    *,
    timezone: str,
    override_until: str | None = None,
    now: datetime | None = None,
) -> ClockOffState:
    """Active days name the activation date; reset is the next local 06:00.

    Wind-down is elapsed minutes before the resolved clock-off instant. Ambiguous
    local times use the first occurrence; nonexistent times shift by the gap.
    """
    zone = resolve_zone(timezone)
    result = ClockOffState(enabled=schedule.enabled, timezone=zone.key)
    if not schedule.enabled:
        return result
    instant = ensure_aware_utc(now if now is not None else datetime.now(UTC))
    assert instant is not None
    today = instant.astimezone(zone).date()
    clock = time.fromisoformat(schedule.clock_off_time)
    windows = []
    for offset in range(-2, 9):
        day = today + timedelta(days=offset)
        if day.weekday() not in schedule.active_days:
            continue
        off = _local_instant(day, clock, zone)
        reset = _local_instant(day, time(6), zone)
        if reset <= off:
            reset = _local_instant(day + timedelta(days=1), time(6), zone)
        wind = off - timedelta(minutes=schedule.wind_down_minutes)
        windows.append((wind, off, reset))

    # An existing clocked-off window takes precedence over tomorrow's wind-down.
    active = [window for window in windows if window[1] <= instant < window[2]]
    selected = (
        max(active, key=lambda w: w[1])
        if active
        else next((window for window in windows if instant < window[1]), None)
    )
    if selected:
        wind, off, reset = selected
        result.state = (
            "clocked_off" if active else ("winding_down" if instant >= wind else "normal")
        )
        result.clock_off_at = to_iso_utc(off)
        result.wind_down_at = to_iso_utc(wind)
        result.resumes_at = to_iso_utc(reset)
        result.minutes_remaining = max(0, math.ceil((off - instant).total_seconds() / 60))
    expiry = ensure_aware_utc(override_until)
    if expiry is not None and instant < expiry:
        result.state = "overridden"
        result.override_until = to_iso_utc(expiry)
    result.guidance = _GUIDANCE.get(result.state, [])
    return result
