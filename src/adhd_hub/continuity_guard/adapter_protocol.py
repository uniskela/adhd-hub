"""Thin agent adapters: normalize inbound hook payloads / outbound decisions.

Cursor remains the strongest enforcement surface. Claude Code maps to the same
guard machine via event-name + decision-shape translation. Codex and OpenClaw
have no equivalent lifecycle deny hooks — document advisory strength only.
"""

from __future__ import annotations

from typing import Any

from adhd_hub.continuity_guard.evidence import parse_claude_mcp_tool_name

# Claude Code uses PascalCase event names; Cursor uses camelCase.
_CLAUDE_TO_CURSOR_EVENT: dict[str, str] = {
    "PreToolUse": "preToolUse",
    "PostToolUse": "postToolUse",
    "PostToolUseFailure": "postToolUseFailure",
    "Stop": "stop",
    "SubagentStop": "stop",
    "SessionStart": "begin_session_noop",  # observational only — no Cursor equivalent
    "SessionEnd": "begin_session_noop",
}

_CURSOR_TO_CLAUDE_EVENT: dict[str, str] = {
    "preToolUse": "PreToolUse",
    "postToolUse": "PostToolUse",
    "postToolUseFailure": "PostToolUseFailure",
    "stop": "Stop",
}


def detect_adapter(payload: dict[str, Any], explicit: str | None = None) -> str:
    """Return ``cursor``, ``claude``, or ``auto``-detected adapter id."""
    if explicit and explicit not in {"", "auto"}:
        return explicit.strip().lower()
    event = payload.get("hook_event_name")
    if isinstance(event, str) and event in _CLAUDE_TO_CURSOR_EVENT:
        return "claude"
    # Claude Stop payloads often include stop_hook_active.
    if "stop_hook_active" in payload:
        return "claude"
    # Claude often sets cwd / CLAUDE_PROJECT_DIR via session_id + transcript_path.
    if (
        isinstance(payload.get("transcript_path"), str)
        and isinstance(payload.get("session_id"), str)
        and isinstance(event, str)
        and event[:1].isupper()
    ):
        return "claude"
    return "cursor"


def normalize_payload_for_guard(
    payload: dict[str, Any],
    *,
    adapter: str,
) -> dict[str, Any]:
    """Copy payload into Cursor-shaped fields the core handler understands."""
    out = dict(payload)
    event = out.get("hook_event_name")
    if not isinstance(event, str):
        event = ""
    if adapter == "claude":
        mapped = _CLAUDE_TO_CURSOR_EVENT.get(event, event)
        if mapped == "begin_session_noop":
            out["hook_event_name"] = ""  # ignore SessionStart/End for enforcement
        else:
            out["hook_event_name"] = mapped
        # Claude session id → conversation_id for soft-reset semantics.
        if not out.get("conversation_id") and isinstance(out.get("session_id"), str):
            out["conversation_id"] = out["session_id"]
        # Bash command may live only under tool_input.
        tool_input = out.get("tool_input")
        if (
            not out.get("command")
            and isinstance(tool_input, dict)
            and isinstance(tool_input.get("command"), str)
        ):
            out["command"] = tool_input["command"]
        # Claude MCP: mcp__<server>__<tool> → bare tool + mcp_server_name.
        tool_name = out.get("tool_name")
        if isinstance(tool_name, str):
            server, bare = parse_claude_mcp_tool_name(tool_name)
            if bare:
                out["tool_name"] = bare
                if server and not out.get("mcp_server_name"):
                    out["mcp_server_name"] = server
        # stop_hook_active → treat like Cursor loop re-entry (allow stop).
        if out.get("stop_hook_active") is True and mapped == "stop":
            out["status"] = "aborted"
    return out


def translate_response_for_adapter(
    response: dict[str, Any],
    *,
    adapter: str,
    original_event: str | None = None,
) -> dict[str, Any]:
    """Map Cursor-shaped guard responses into the agent-native hook schema."""
    if adapter != "claude":
        return response
    if not response:
        return {}

    claude_event = None
    if isinstance(original_event, str) and original_event in _CLAUDE_TO_CURSOR_EVENT:
        claude_event = original_event
    elif isinstance(original_event, str):
        claude_event = _CURSOR_TO_CLAUDE_EVENT.get(original_event, original_event)

    permission = response.get("permission")
    if permission == "deny":
        reason = (
            response.get("agent_message")
            or response.get("user_message")
            or "ADHD Hub continuity required."
        )
        return {
            "hookSpecificOutput": {
                "hookEventName": claude_event or "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    if permission == "allow":
        # Empty object → leave normal Claude permission flow (fail-open style).
        return {}

    followup = response.get("followup_message")
    if isinstance(followup, str) and followup.strip():
        # Claude Stop: block with reason (nudges one more turn).
        return {"decision": "block", "reason": followup}

    user_message = response.get("user_message")
    if isinstance(user_message, str) and user_message.strip():
        # No native preCompact on Claude — surface as systemMessage if present.
        return {
            "systemMessage": user_message,
        }
    return {}
