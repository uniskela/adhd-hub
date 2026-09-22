"""Timezone helpers for display and wiki timestamps."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NAIVE_DT = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$")


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


def ensure_aware_utc(value: datetime | date | str | None) -> datetime | None:
    """Coerce Hub stamps to timezone-aware UTC.

    Naive datetimes and date-only strings are treated as UTC (Hub storage
    contract). Aware values are converted to UTC.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    if " " in text and "T" not in text[:11]:
        text = text.replace(" ", "T", 1)
    if _DATE_ONLY.match(text):
        text = f"{text}T00:00:00+00:00"
    elif _NAIVE_DT.match(text):
        text = f"{text}+00:00"
    elif text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def to_iso_utc(value: datetime | date | str | None) -> str:
    """Serialize a stamp as UTC ISO-8601 with a trailing ``Z`` (empty if unset)."""
    aware = ensure_aware_utc(value)
    if aware is None:
        return ""
    # Keep millis when present; strip +00:00 → Z for stable JS Date parsing.
    text = aware.isoformat().replace("+00:00", "Z")
    return text


def format_timestamp(dt: datetime | None = None, *, timezone: str = "UTC") -> str:
    """Human stamp like `2026-09-08 17:47 AEST` (falls back to UTC)."""
    tz = resolve_zone(timezone)
    when = (dt or datetime.now(UTC)).astimezone(tz)
    # %Z is abbreviation when available; include offset as backup clarity
    abbr = when.strftime("%Z") or tz.key
    return when.strftime(f"%Y-%m-%d %H:%M {abbr}")


def now_in_zone(timezone: str = "UTC") -> datetime:
    return datetime.now(resolve_zone(timezone))


def normalize_public_timestamps(data: dict[str, Any]) -> dict[str, Any]:
    """Rewrite common thread timestamp fields to UTC ``Z`` ISO strings in-place."""
    for key in (
        "created_at",
        "updated_at",
        "paused_at",
        "last_reminded_at",
        "source_imported_at",
        "external_updated_at",
        "due_at",
    ):
        if key in data and data[key] is not None and data[key] != "":
            data[key] = to_iso_utc(data[key])
    return data


def latest_iso(*values: datetime | date | str | None) -> str:
    """Return the chronologically latest stamp as UTC ``Z`` ISO (empty if none)."""
    best: datetime | None = None
    for value in values:
        aware = ensure_aware_utc(value)
        if aware is None:
            continue
        if best is None or aware > best:
            best = aware
    return to_iso_utc(best) if best else ""
