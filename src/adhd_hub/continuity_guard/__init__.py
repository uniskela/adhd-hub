"""Deterministic ADHD Hub Continuity Guard (no LLM).

Tracks whether substantial agent work established Hub continuity evidence,
using Git-local ephemeral state and Cursor lifecycle hooks.
"""

from __future__ import annotations

from adhd_hub.continuity_guard.config import GuardConfig, load_guard_config
from adhd_hub.continuity_guard.machine import GuardPhase, apply_event
from adhd_hub.continuity_guard.state import (
    GuardState,
    clear_state,
    load_state,
    reset_state,
    save_state,
    state_path_for,
)

__all__ = [
    "GuardConfig",
    "GuardPhase",
    "GuardState",
    "apply_event",
    "clear_state",
    "load_guard_config",
    "load_state",
    "reset_state",
    "save_state",
    "state_path_for",
]
