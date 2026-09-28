"""Cursor hook protocol handlers for the continuity guard."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from adhd_hub.continuity_guard.config import GuardConfig, load_guard_config
from adhd_hub.continuity_guard.evidence import (
    apply_evidence_to_state,
    observe_forge_action,
    observe_mcp_tool,
)
from adhd_hub.continuity_guard.heuristics import assess_file_edit, assess_tool
from adhd_hub.continuity_guard.machine import (
    MSG_MUTATION_BLOCK,
    GuardEvent,
    GuardPhase,
    apply_event,
    continuity_established,
    stop_decision,
)
from adhd_hub.continuity_guard.state import (
    is_state_stale,
    load_state,
    save_state,
)

MSG_PRECOMPACT = (
    "Before context compaction, checkpoint the current ADHD Hub thread with: "
    "Goal, one Focus, max 3 Next steps, blocker only if real, concrete Resume cue. "
    "If Hub MCP is unavailable, use the authorised [ADHD] forge fallback."
)


def parse_hook_stdin(raw: bytes | str | None = None) -> dict[str, Any]:
    """Parse untrusted hook JSON from stdin or ``raw``. Never execute content."""
    if raw is None:
        data = sys.stdin.buffer.read()
    elif isinstance(raw, str):
        data = raw.encode("utf-8")
    else:
        data = raw
    if not data or not data.strip():
        return {}
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def resolve_project_root(payload: dict[str, Any], cwd: Path | None = None) -> Path:
    """Pick a project root from workspace_roots or cwd."""
    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and roots:
        first = roots[0]
        if isinstance(first, str) and first.strip():
            return Path(first).expanduser().resolve()
    if cwd is not None:
        return cwd.resolve()
    return Path.cwd().resolve()


def handle_hook_payload(
    payload: dict[str, Any],
    *,
    project_dir: Path | str | None = None,
    config: GuardConfig | None = None,
    enrolled: bool | None = None,
) -> dict[str, Any]:
    """Dispatch one Cursor hook payload → response object (may be empty)."""
    project = (
        Path(project_dir).expanduser().resolve()
        if project_dir
        else resolve_project_root(payload)
    )
    loaded = load_guard_config(project)
    # Explicit TOML disable always wins for real hook runs (no injected config).
    if config is None and loaded.explicitly_disabled:
        return {}
    cfg = config if config is not None else loaded
    if enrolled is False:
        return {}
    # Enrollment without a TOML section → enforce with balanced defaults.
    if config is None and enrolled is True and loaded.source != "file":
        cfg = GuardConfig(
            enabled=True,
            mode="balanced",
            max_stop_retries=loaded.max_stop_retries,
            checkpoint_after_mutations=loaded.checkpoint_after_mutations,
            meaningful_edit_files=loaded.meaningful_edit_files,
            meaningful_mutation_tools=loaded.meaningful_mutation_tools,
            stale_state_hours=loaded.stale_state_hours,
            source="default",
        )
    if not cfg.is_enforcing:
        return {}

    event_name = str(payload.get("hook_event_name") or "").strip()
    state = load_state(project)
    if is_state_stale(state, max_age_hours=cfg.stale_state_hours):
        # Stale previous session must not block — soft reset phase
        apply_event(state, GuardEvent.reset, config=cfg)

    conv = payload.get("conversation_id")
    conv_s = conv.strip() if isinstance(conv, str) else None
    # Soft-reset for every event (including read-only / stop) when conversation changes.
    if conv_s and state.conversation_id and conv_s != state.conversation_id:
        apply_event(
            state,
            GuardEvent.begin_session,
            config=cfg,
            conversation_id=conv_s,
        )
        save_state(project, state)

    if event_name in {"preToolUse", "beforeMCPExecution"}:
        return _handle_pre_tool(project, state, cfg, payload, conv_s, event_name)
    if event_name in {"postToolUse", "afterMCPExecution", "postToolUseFailure"}:
        return _handle_post_tool(project, state, cfg, payload, conv_s, event_name)
    if event_name == "afterFileEdit":
        return _handle_after_file_edit(project, state, cfg, payload, conv_s)
    if event_name == "preCompact":
        return _handle_precompact(project, state, cfg, payload, conv_s)
    if event_name == "stop":
        return _handle_stop(project, state, cfg, payload, conv_s)
    # Unknown events: observe nothing
    return {}


def _handle_pre_tool(
    project: Path,
    state: Any,
    cfg: GuardConfig,
    payload: dict[str, Any],
    conv: str | None,
    event_name: str,
) -> dict[str, Any]:
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str):
        tool_name = None
    tool_input = payload.get("tool_input")
    command = payload.get("command") if isinstance(payload.get("command"), str) else None
    mcp_server = payload.get("mcp_server_name")
    if isinstance(mcp_server, str) and event_name == "beforeMCPExecution":
        # Never block Hub MCP continuity tools
        hit = observe_mcp_tool(tool_name, mcp_server_name=mcp_server, tool_input=tool_input)
        if hit:
            return {"permission": "allow"}

    # Allow authorised [ADHD] forge fallback while continuity is still unestablished.
    if observe_forge_action(tool_name=tool_name, command=command, tool_input=tool_input):
        return {"permission": "allow"}

    assessment = assess_tool(tool_name, tool_input=tool_input, command=command)
    needs_continuity = (
        assessment.is_mutation
        and assessment.is_meaningful
        and not continuity_established(state)
        and not state.persistence_unavailable
    )
    if needs_continuity:
        # Enter required_unestablished without counting denied attempts toward checkpoint.
        if state.phase_enum() in {
            GuardPhase.not_required,
            GuardPhase.paused,
            GuardPhase.completed,
        }:
            state.meaningful_work = True
            if conv and not state.conversation_id:
                state.conversation_id = conv
            state.set_phase(GuardPhase.required_unestablished)
            save_state(project, state)
        return {
            "permission": "deny",
            "agent_message": MSG_MUTATION_BLOCK,
            "user_message": "ADHD Hub continuity required before substantial mutation.",
        }

    # Count only allowed meaningful mutations (single source of truth with afterFileEdit).
    if assessment.is_meaningful:
        apply_event(
            state,
            GuardEvent.meaningful_mutation,
            config=cfg,
            conversation_id=conv,
            path_hint=_path_hint(tool_input),
        )
        save_state(project, state)
    return {"permission": "allow"}


def _handle_post_tool(
    project: Path,
    state: Any,
    cfg: GuardConfig,
    payload: dict[str, Any],
    conv: str | None,
    event_name: str,
) -> dict[str, Any]:
    if event_name == "postToolUseFailure":
        return {}

    tool_name = payload.get("tool_name") if isinstance(payload.get("tool_name"), str) else None
    tool_input = payload.get("tool_input")
    tool_output = payload.get("tool_output") or payload.get("result_json")
    mcp_server = (
        payload.get("mcp_server_name")
        if isinstance(payload.get("mcp_server_name"), str)
        else None
    )
    command = payload.get("command") if isinstance(payload.get("command"), str) else None

    # Hub MCP evidence
    hit = observe_mcp_tool(
        tool_name,
        mcp_server_name=mcp_server,
        tool_input=tool_input,
        success=True,
    )
    # Retry without server name only when none was supplied (Cloud MCP:tool form).
    if hit is None and mcp_server is None:
        hit = observe_mcp_tool(tool_name, tool_input=tool_input, success=True)

    if hit is not None:
        apply_evidence_to_state(state, hit)
        if hit.kind in {"resolve", "digest", "overlap"}:
            # Resolve+digest (or resolve+overlap) establishes continuity
            if continuity_established(state):
                apply_event(
                    state,
                    GuardEvent.continuity_established,
                    config=cfg,
                    conversation_id=conv,
                    continuity_method="mcp",
                    project_slug=hit.project_slug,
                    thread_id=hit.thread_id,
                )
        elif hit.kind == "progress":
            apply_event(
                state,
                GuardEvent.checkpoint_observed,
                config=cfg,
                conversation_id=conv,
                thread_id=hit.thread_id,
                project_slug=hit.project_slug,
            )
        elif hit.kind == "pause":
            apply_event(
                state,
                GuardEvent.pause_observed,
                config=cfg,
                conversation_id=conv,
                thread_id=hit.thread_id,
            )
        elif hit.kind == "done":
            apply_event(
                state,
                GuardEvent.done_observed,
                config=cfg,
                conversation_id=conv,
                thread_id=hit.thread_id,
            )
        save_state(project, state)
        return {}

    forge = observe_forge_action(
        tool_name=tool_name,
        command=command,
        tool_output=tool_output,
        tool_input=tool_input,
    )
    if forge is not None:
        apply_evidence_to_state(state, forge)
        apply_event(
            state,
            GuardEvent.forge_fallback_observed,
            config=cfg,
            conversation_id=conv,
            fallback_issue_number=forge.fallback_issue_number,
            fallback_issue_url=forge.fallback_issue_url,
        )
        save_state(project, state)
        return {}

    # Do not double-count mutations here — preToolUse (allowed) / afterFileEdit own counts.
    return {}


def _handle_after_file_edit(
    project: Path,
    state: Any,
    cfg: GuardConfig,
    payload: dict[str, Any],
    conv: str | None,
) -> dict[str, Any]:
    path = payload.get("file_path") if isinstance(payload.get("file_path"), str) else None
    edits = payload.get("edits") if isinstance(payload.get("edits"), list) else None
    assessment = assess_file_edit(path, edits=edits)
    if assessment.is_mutation:
        event = (
            GuardEvent.file_edit
            if assessment.is_meaningful
            else GuardEvent.trivial_activity
        )
        if assessment.is_meaningful:
            apply_event(
                state,
                GuardEvent.file_edit,
                config=cfg,
                conversation_id=conv,
                path_hint=path,
            )
            save_state(project, state)
        elif event == GuardEvent.trivial_activity:
            # Tiny edits: count gently toward files_changed only after 3
            state.files_changed += 1
            if state.files_changed >= cfg.meaningful_edit_files:
                apply_event(
                    state,
                    GuardEvent.file_edit,
                    config=cfg,
                    conversation_id=conv,
                    path_hint=path,
                )
            save_state(project, state)
    return {}


def _handle_precompact(
    project: Path,
    state: Any,
    cfg: GuardConfig,
    payload: dict[str, Any],
    conv: str | None,
) -> dict[str, Any]:
    del payload, conv  # observational; unused
    phase = state.phase_enum()
    if state.meaningful_work and phase in {
        GuardPhase.active,
        GuardPhase.checkpoint_due,
        GuardPhase.required_unestablished,
    } and (
        state.mutations_since_checkpoint > 0
        or phase == GuardPhase.checkpoint_due
        or not state.evidence_progress
    ):
        return {"user_message": MSG_PRECOMPACT}
    return {}


def _handle_stop(
    project: Path,
    state: Any,
    cfg: GuardConfig,
    payload: dict[str, Any],
    conv: str | None,
) -> dict[str, Any]:
    del conv
    status = payload.get("status")
    if status in {"aborted", "error"}:
        # Don't force follow-ups on abort/error loops
        return {}
    loop_count = payload.get("loop_count")
    try:
        loops = int(loop_count) if loop_count is not None else 0
    except (TypeError, ValueError):
        loops = 0

    # Heuristic: agent said work is done if evidence_done already, else unfinished
    work_complete = bool(state.evidence_done)
    followup, allow = stop_decision(
        state,
        config=cfg,
        loop_count=loops,
        work_looks_complete=work_complete,
    )
    save_state(project, state)
    if allow or not followup:
        if state.last_warning and loops >= cfg.max_stop_retries:
            # Surface warning once via followup empty; user sees last_warning in status
            return {}
        return {}
    return {"followup_message": followup}


def _path_hint(tool_input: Any) -> str | None:
    if isinstance(tool_input, dict):
        for key in ("path", "file_path", "filePath", "target_file"):
            val = tool_input.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def run_hook_cli(
    *,
    project_dir: Path | str | None = None,
    enrolled: bool = True,
) -> int:
    """Read stdin, write JSON response to stdout. Always exit 0 (fail-open)."""
    try:
        payload = parse_hook_stdin()
        response = handle_hook_payload(
            payload,
            project_dir=project_dir,
            enrolled=enrolled,
        )
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — hooks must fail-open
        sys.stdout.write("{}\n")
    return 0
