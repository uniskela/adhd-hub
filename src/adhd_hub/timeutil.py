"""Timezone helpers for display and wiki timestamps."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def resolve_zone(name: str | None) -> ZoneInfo:
    label = (name or "UTC").strip() or "UTC"
    if label.upper() == "UTC":
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(label)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def validate_timezone(name: str | None) -> str:
    """Return a normalized IANA name, or raise ValueError if unknown."""
    label = (name or "UTC").strip() or "UTC"
    if label.upper() == "UTC":
        return "UTC"
    try:
        ZoneInfo(label)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {label}") from exc
    return label


def format_timestamp(dt: datetime | None = None, *, timezone: str = "UTC") -> str:
    """Human stamp like `2026-09-08 17:47 AEST` (falls back to UTC)."""
    tz = resolve_zone(timezone)
    when = (dt or datetime.now(UTC)).astimezone(tz)
    # %Z is abbreviation when available; include offset as backup clarity
    abbr = when.strftime("%Z") or tz.key
    return when.strftime(f"%Y-%m-%d %H:%M {abbr}")


def now_in_zone(timezone: str = "UTC") -> datetime:
    return datetime.now(resolve_zone(timezone))
