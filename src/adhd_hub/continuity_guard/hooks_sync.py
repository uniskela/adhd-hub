"""Canonical Cursor hooks merge helpers for continuity guard (project-sync)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

# Command marker used to identify Hub-owned hook entries.
HUB_GUARD_COMMAND_MARKER = ".cursor/hooks/adhd-hub-guard.sh"

# Cloud-safe events (also work locally).
CLOUD_SAFE_EVENTS: tuple[str, ...] = (
    "preToolUse",
    "postToolUse",
    "afterFileEdit",
    "preCompact",
    "stop",
)

# Local-only enrichment (not relied on for Cloud Agents).
LOCAL_ONLY_EVENTS: tuple[str, ...] = (
    "beforeMCPExecution",
    "afterMCPExecution",
)

ALL_HUB_EVENTS: tuple[str, ...] = CLOUD_SAFE_EVENTS + LOCAL_ONLY_EVENTS

GUARD_SCRIPT_REL = ".cursor/hooks/adhd-hub-guard.sh"
HOOKS_JSON_REL = ".cursor/hooks.json"


def expected_guard_script() -> str:
    """Thin wrapper: invoke ``adhd-hub guard hook``; fail-open if missing.

    Does not use unpinned ``uvx --from adhd-hub`` (PyPI name may be unclaimed /
    untrusted). Prefer ``adhd-hub`` on PATH from an installed package or checkout.
    """
    return """#!/usr/bin/env bash
# ADHD Hub Continuity Guard — Hub-owned Cursor hook wrapper.
# Managed by: adhd-hub sync-project --continuity-guard
set -euo pipefail
ROOT="$(pwd)"

run_guard() {
  if command -v adhd-hub >/dev/null 2>&1; then
    # Positional project path (subcommand parser has no --project flag).
    adhd-hub guard hook "$ROOT"
    return $?
  fi
  # Fail-open: never block the agent if the CLI is unavailable.
  # Do not uvx an unpinned PyPI package name (supply-chain risk).
  echo '{}'
  return 0
}

run_guard
"""


def hub_hook_entry(event_name: str) -> dict[str, Any]:
    """Return the Hub-owned hook definition for ``event_name``."""
    entry: dict[str, Any] = {
        "command": HUB_GUARD_COMMAND_MARKER,
    }
    if event_name == "stop":
        entry["loop_limit"] = 2
    return entry


def is_hub_hook_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    command = entry.get("command")
    if not isinstance(command, str):
        return False
    return HUB_GUARD_COMMAND_MARKER in command.replace("\\", "/")


def hooks_json_has_hub_entries(hooks_path: Path) -> bool:
    if not hooks_path.is_file():
        return False
    try:
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False
    for entries in hooks.values():
        if not isinstance(entries, list):
            continue
        if any(is_hub_hook_entry(e) for e in entries):
            return True
    return False


def merge_hooks_json(
    current: dict[str, Any] | None,
    *,
    include_local_mcp: bool = True,
) -> dict[str, Any]:
    """Merge Hub guard hooks into an existing hooks.json structure.

    Preserves unrelated entries. Upserts Hub entries per event by command marker.
    """
    if current is None:
        base: dict[str, Any] = {"version": 1, "hooks": {}}
    elif not isinstance(current, dict):
        raise TypeError("hooks.json root must be a JSON object")
    else:
        base = deepcopy(current)
    if "version" not in base:
        base["version"] = 1
    hooks = base.get("hooks")
    if hooks is None:
        hooks = {}
        base["hooks"] = hooks
    if not isinstance(hooks, dict):
        raise TypeError("hooks.json 'hooks' must be an object")

    events = list(CLOUD_SAFE_EVENTS)
    if include_local_mcp:
        events.extend(LOCAL_ONLY_EVENTS)

    for event_name in events:
        desired = hub_hook_entry(event_name)
        existing = hooks.get(event_name)
        if existing is None:
            hooks[event_name] = [desired]
            continue
        if not isinstance(existing, list):
            raise TypeError(f"hooks.json hooks.{event_name} must be an array")
        found = False
        new_list: list[Any] = []
        for entry in existing:
            if is_hub_hook_entry(entry):
                if not found:
                    new_list.append(desired)
                    found = True
                # Drop duplicate Hub entries
            else:
                new_list.append(entry)
        if not found:
            new_list.append(desired)
        hooks[event_name] = new_list
    return base


def remove_hub_hooks(current: dict[str, Any] | None) -> dict[str, Any] | None:
    """Remove only Hub-owned hook entries. Returns None if nothing remains."""
    if current is None:
        return None
    if not isinstance(current, dict):
        raise TypeError("hooks.json root must be a JSON object")
    base = deepcopy(current)
    hooks = base.get("hooks")
    if not isinstance(hooks, dict):
        return base
    empty_events: list[str] = []
    for event_name, entries in list(hooks.items()):
        if not isinstance(entries, list):
            continue
        kept = [e for e in entries if not is_hub_hook_entry(e)]
        if kept:
            hooks[event_name] = kept
        else:
            empty_events.append(event_name)
    for event_name in empty_events:
        del hooks[event_name]
    if not hooks:
        return None
    return base


def plan_hooks_merge(hooks_path: Path, *, include_local_mcp: bool = True) -> list[str]:
    """Return human-readable drift descriptions (empty when current)."""
    current_obj: dict[str, Any] | None = None
    if hooks_path.is_file():
        try:
            parsed = json.loads(hooks_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed .cursor/hooks.json: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("malformed .cursor/hooks.json: root must be object")
        current_obj = parsed
    desired = merge_hooks_json(current_obj, include_local_mcp=include_local_mcp)
    current_text = (
        json.dumps(current_obj, indent=2, ensure_ascii=False) + "\n"
        if current_obj is not None
        else ""
    )
    desired_text = json.dumps(desired, indent=2, ensure_ascii=False) + "\n"
    if current_text == desired_text:
        return []
    if current_obj is None:
        return ["create .cursor/hooks.json with Hub continuity guard hooks"]
    return ["update Hub-owned entries in .cursor/hooks.json (preserve others)"]


def dumps_hooks(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
