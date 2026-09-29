"""Multi-agent continuity-guard sync helpers (Claude Code; Codex/OpenClaw docs-only).

Cursor hooks stay in ``hooks_sync.py``. This module merges Hub-owned Claude Code
hooks into ``.claude/settings.json`` without replacing unrelated settings.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

CLAUDE_SETTINGS_REL = ".claude/settings.json"
CLAUDE_GUARD_SCRIPT_REL = ".claude/hooks/adhd-hub-guard.sh"
# Substring match: recognizes both relative and $CLAUDE_PROJECT_DIR-anchored forms.
HUB_CLAUDE_COMMAND_MARKER = ".claude/hooks/adhd-hub-guard.sh"
# Anchor to project root — Claude hooks may run with cwd below the project.
HUB_CLAUDE_HOOK_COMMAND = '"$CLAUDE_PROJECT_DIR/.claude/hooks/adhd-hub-guard.sh"'

# Claude Code events we enroll (honest strength: PreToolUse can deny; Stop can nudge).
CLAUDE_HUB_EVENTS: tuple[str, ...] = (
    "PreToolUse",
    "PostToolUse",
    "Stop",
)


def expected_claude_guard_script() -> str:
    """Thin wrapper → ``adhd-hub guard hook --adapter claude``; fail-open."""
    return """#!/usr/bin/env bash
# ADHD Hub Continuity Guard — Hub-owned Claude Code hook wrapper.
# Managed by: adhd-hub sync-project --continuity-guard
set -euo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

run_guard() {
  if command -v adhd-hub >/dev/null 2>&1; then
    adhd-hub guard hook --adapter claude "$ROOT"
    return $?
  fi
  # Fail-open: never brick Claude Code if the CLI is missing.
  echo '{}'
  return 0
}

run_guard
"""


def hub_claude_hook_block() -> dict[str, Any]:
    """One Claude matcher block that invokes the Hub wrapper for all tools."""
    return {
        "hooks": [
            {
                "type": "command",
                "command": HUB_CLAUDE_HOOK_COMMAND,
            }
        ]
    }


def is_hub_claude_hook_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    hooks = entry.get("hooks")
    if not isinstance(hooks, list):
        # Flat command form (rare)
        command = entry.get("command")
        return isinstance(command, str) and HUB_CLAUDE_COMMAND_MARKER in command.replace("\\", "/")
    for hook in hooks:
        if not isinstance(hook, dict):
            continue
        command = hook.get("command")
        if isinstance(command, str) and HUB_CLAUDE_COMMAND_MARKER in command.replace("\\", "/"):
            return True
    return False


def claude_settings_has_hub_entries(settings_path: Path) -> bool:
    if not settings_path.is_file():
        return False
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
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
        if any(is_hub_claude_hook_entry(e) for e in entries):
            return True
    return False


def merge_claude_settings(current: dict[str, Any] | None) -> dict[str, Any]:
    """Upsert Hub Claude hook blocks; preserve unrelated settings/hooks."""
    if current is None:
        base: dict[str, Any] = {}
    elif not isinstance(current, dict):
        raise TypeError(".claude/settings.json root must be a JSON object")
    else:
        base = deepcopy(current)
    hooks = base.get("hooks")
    if hooks is None:
        hooks = {}
        base["hooks"] = hooks
    elif not isinstance(hooks, dict):
        raise TypeError(".claude/settings.json 'hooks' must be an object")
    for event_name in CLAUDE_HUB_EVENTS:
        entries = hooks.get(event_name)
        if entries is None:
            hooks[event_name] = [hub_claude_hook_block()]
            continue
        if not isinstance(entries, list):
            raise TypeError(f".claude/settings.json hooks.{event_name} must be an array")
        kept = [e for e in entries if not is_hub_claude_hook_entry(e)]
        kept.append(hub_claude_hook_block())
        hooks[event_name] = kept
    return base


def remove_claude_hub_hooks(current: dict[str, Any] | None) -> dict[str, Any] | None:
    """Remove Hub-owned Claude hook entries. Returns None if file should be deleted."""
    if current is None:
        return None
    if not isinstance(current, dict):
        raise TypeError(".claude/settings.json root must be a JSON object")
    base = deepcopy(current)
    hooks = base.get("hooks")
    if not isinstance(hooks, dict):
        return base
    empty_events: list[str] = []
    for event_name, entries in list(hooks.items()):
        if not isinstance(entries, list):
            continue
        kept = [e for e in entries if not is_hub_claude_hook_entry(e)]
        if kept:
            hooks[event_name] = kept
        else:
            empty_events.append(event_name)
    for event_name in empty_events:
        del hooks[event_name]
    if not hooks:
        base.pop("hooks", None)
    # If nothing remains except empty object, signal delete.
    if not base:
        return None
    return base


def dumps_claude_settings(obj: dict[str, Any]) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def plan_claude_settings_merge(settings_path: Path) -> list[str]:
    current_obj: dict[str, Any] | None = None
    if settings_path.is_file():
        try:
            parsed = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed .claude/settings.json: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("malformed .claude/settings.json: root must be object")
        current_obj = parsed
    desired = merge_claude_settings(current_obj)
    current_text = (
        json.dumps(current_obj, indent=2, ensure_ascii=False) + "\n"
        if current_obj is not None
        else ""
    )
    desired_text = dumps_claude_settings(desired)
    if current_text == desired_text:
        return []
    if current_obj is None:
        return ["create .claude/settings.json with Hub continuity guard hooks"]
    return ["update Hub-owned entries in .claude/settings.json (preserve others)"]


# Honest per-agent strength (documented in adapters + continuity-guard.md).
ADAPTER_STRENGTH: dict[str, dict[str, str]] = {
    "cursor": {
        "level": "strong",
        "summary": (
            "Lifecycle command hooks can deny mutations, count edits, and "
            "follow up on stop (loop_limit)."
        ),
    },
    "claude": {
        "level": "medium",
        "summary": (
            "Claude Code PreToolUse can deny; PostToolUse observes evidence; "
            "Stop can block-nudge up to the configured retry limit "
            "(default max_stop_retries=2). SessionStart/End are not used for enforcement."
        ),
    },
    "codex": {
        "level": "advisory",
        "summary": (
            "No Hub-managed lifecycle deny hooks. Continuity relies on skills, "
            "AGENTS guidance, MCP, and optional ``adhd-hub guard observe``."
        ),
    },
    "openclaw": {
        "level": "advisory",
        "summary": (
            "No coding-agent tool deny hooks. Hub↔OpenClaw reminder hooks are a "
            "separate direction; continuity for coding sessions is skills/MCP/forge."
        ),
    },
}
