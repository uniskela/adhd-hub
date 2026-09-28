"""Continuity guard configuration (balanced defaults; optional project TOML)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Optional TOML — stdlib tomllib on 3.11+
try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


@dataclass(frozen=True)
class GuardConfig:
    """Per-project guard knobs. V1 focuses on ``balanced`` behaviour."""

    enabled: bool = False
    mode: str = "balanced"
    max_stop_retries: int = 2
    checkpoint_after_mutations: int = 5
    # Meaningful-work thresholds (conservative)
    meaningful_edit_files: int = 2
    meaningful_mutation_tools: int = 1
    stale_state_hours: float = 48.0
    # "default" = no adhd-hub.toml section; "file" = section was present
    source: str = "default"

    @property
    def is_enforcing(self) -> bool:
        return self.enabled and self.mode not in {"off", "disabled"}

    @property
    def explicitly_disabled(self) -> bool:
        """True when project TOML explicitly disables the guard."""
        return self.source == "file" and not self.is_enforcing


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_guard_config(project_dir: Path | str) -> GuardConfig:
    """Load optional ``adhd-hub.toml`` ``[continuity_guard]`` section.

    Missing or malformed files fall back to safe defaults (``enabled=False``).
    Enrollment via sync-project also sets enabled when hooks are installed —
    callers may OR that with this config.
    """
    project = Path(project_dir).expanduser().resolve()
    path = project / "adhd-hub.toml"
    if not path.is_file() or tomllib is None:
        return GuardConfig()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return GuardConfig()
    section = raw.get("continuity_guard")
    if not isinstance(section, dict):
        return GuardConfig()
    mode = str(section.get("mode", "balanced") or "balanced").strip().lower()
    return GuardConfig(
        enabled=_coerce_bool(section.get("enabled"), False),
        mode=mode if mode in {"off", "gentle", "balanced", "strict"} else "balanced",
        max_stop_retries=max(0, _coerce_int(section.get("max_stop_retries"), 2)),
        checkpoint_after_mutations=max(
            1, _coerce_int(section.get("checkpoint_after_mutations"), 5)
        ),
        meaningful_edit_files=max(
            1, _coerce_int(section.get("meaningful_edit_files"), 2)
        ),
        meaningful_mutation_tools=max(
            1, _coerce_int(section.get("meaningful_mutation_tools"), 1)
        ),
        stale_state_hours=max(
            1.0, _coerce_float(section.get("stale_state_hours"), 48.0)
        ),
        source="file",
    )
