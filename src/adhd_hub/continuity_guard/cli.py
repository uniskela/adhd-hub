"""CLI helpers for ``adhd-hub guard`` subcommands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from adhd_hub.continuity_guard.audit import audit_project, format_audit_report
from adhd_hub.continuity_guard.config import GuardConfig, load_guard_config
from adhd_hub.continuity_guard.evidence import apply_evidence_to_state, observe_mcp_tool
from adhd_hub.continuity_guard.hooks_protocol import run_hook_cli
from adhd_hub.continuity_guard.machine import GuardEvent, apply_event
from adhd_hub.continuity_guard.state import (
    load_state,
    reset_state,
    save_state,
)
from adhd_hub.project_sync import project_has_continuity_guard


def _effective_config(project: Path) -> tuple[GuardConfig, bool]:
    cfg = load_guard_config(project)
    enrolled = project_has_continuity_guard(project)
    if enrolled and not cfg.enabled:
        cfg = GuardConfig(
            enabled=True,
            mode=cfg.mode if cfg.mode != "off" else "balanced",
            max_stop_retries=cfg.max_stop_retries,
            checkpoint_after_mutations=cfg.checkpoint_after_mutations,
            meaningful_edit_files=cfg.meaningful_edit_files,
            meaningful_mutation_tools=cfg.meaningful_mutation_tools,
            stale_state_hours=cfg.stale_state_hours,
        )
    return cfg, enrolled


def cmd_guard(args: argparse.Namespace) -> int:
    """Dispatch ``adhd-hub guard <subcommand>``."""
    project = Path(getattr(args, "path", ".") or ".").expanduser().resolve()
    action = getattr(args, "guard_command", None)
    if action == "hook":
        return run_hook_cli(project_dir=project, enrolled=True)
    if action == "status":
        return _cmd_status(project)
    if action == "begin":
        return _cmd_begin(project)
    if action == "observe":
        return _cmd_observe(project, args)
    if action == "checkpoint":
        return _cmd_checkpoint(project)
    if action == "finish":
        return _cmd_finish(project)
    if action == "reset":
        reset_state(project)
        print(f"continuity guard state reset: {project}")
        return 0
    if action == "audit":
        report = audit_project(project)
        print(format_audit_report(report), end="")
        return 0 if report.ok else 1
    print(f"unknown guard command: {action}", file=sys.stderr)
    return 2


def _cmd_status(project: Path) -> int:
    cfg, enrolled = _effective_config(project)
    state = load_state(project)
    print(f"project: {project}")
    print(f"enrolled: {enrolled}")
    print(f"config.enabled: {cfg.enabled} mode={cfg.mode}")
    print(f"phase: {state.phase}")
    print(f"meaningful_work: {state.meaningful_work}")
    print(f"files_changed: {state.files_changed}")
    print(f"mutations_since_checkpoint: {state.mutations_since_checkpoint}")
    print(
        "evidence: "
        f"resolve={state.evidence_resolve} digest={state.evidence_digest} "
        f"progress={state.evidence_progress} pause={state.evidence_pause} "
        f"done={state.evidence_done} forge={state.evidence_forge_fallback}"
    )
    if state.thread_id:
        print(f"thread_id: {state.thread_id}")
    if state.project_slug:
        print(f"project_slug: {state.project_slug}")
    if state.last_warning:
        print(f"warning: {state.last_warning}")
    return 0


def _cmd_begin(project: Path) -> int:
    cfg, _enrolled = _effective_config(project)
    state = load_state(project)
    apply_event(state, GuardEvent.begin_session, config=cfg)
    save_state(project, state)
    print(f"phase: {state.phase}")
    return 0


def _cmd_observe(project: Path, args: argparse.Namespace) -> int:
    cfg, _enrolled = _effective_config(project)
    state = load_state(project)
    tool = getattr(args, "tool", None)
    if tool:
        hit = observe_mcp_tool(tool, success=True)
        if hit:
            apply_evidence_to_state(state, hit)
            if hit.kind in {"resolve", "digest", "overlap"}:
                apply_event(
                    state,
                    GuardEvent.continuity_established,
                    config=cfg,
                    continuity_method="mcp",
                )
            elif hit.kind == "progress":
                apply_event(state, GuardEvent.checkpoint_observed, config=cfg)
            elif hit.kind == "pause":
                apply_event(state, GuardEvent.pause_observed, config=cfg)
            elif hit.kind == "done":
                apply_event(state, GuardEvent.done_observed, config=cfg)
            elif hit.kind == "forge_fallback":
                apply_event(state, GuardEvent.forge_fallback_observed, config=cfg)
        else:
            print(f"unrecognized tool for observe: {tool}", file=sys.stderr)
            return 2
    elif getattr(args, "persistence_unavailable", False):
        apply_event(state, GuardEvent.persistence_unavailable, config=cfg)
    else:
        print("Provide --tool <hub_tool> or --persistence-unavailable", file=sys.stderr)
        return 2
    save_state(project, state)
    print(f"phase: {state.phase}")
    return 0


def _cmd_checkpoint(project: Path) -> int:
    cfg, _enrolled = _effective_config(project)
    state = load_state(project)
    apply_event(state, GuardEvent.checkpoint_observed, config=cfg)
    save_state(project, state)
    print(f"phase: {state.phase}")
    return 0


def _cmd_finish(project: Path) -> int:
    cfg, _enrolled = _effective_config(project)
    state = load_state(project)
    apply_event(state, GuardEvent.done_observed, config=cfg)
    save_state(project, state)
    print(f"phase: {state.phase}")
    return 0


def add_guard_parser(sub: argparse._SubParsersAction) -> None:
    guard = sub.add_parser(
        "guard",
        help="Deterministic ADHD Hub continuity guard (Cursor hooks / local state)",
    )
    guard.add_argument(
        "--project",
        dest="path",
        default=".",
        help="Project folder (default: .)",
    )
    gsub = guard.add_subparsers(dest="guard_command", required=True)

    for name, help_text in (
        ("status", "Show guard phase and evidence"),
        ("begin", "Mark a new guard session"),
        ("checkpoint", "Record a checkpoint observation"),
        ("finish", "Record completion (mark_done) evidence"),
        ("reset", "Clear Git-local guard state"),
        ("audit", "CI-safe install/config audit (no runtime state)"),
        ("hook", "Cursor hook entrypoint (JSON stdin → JSON stdout)"),
    ):
        p = gsub.add_parser(name, help=help_text)
        p.add_argument(
            "path",
            nargs="?",
            default=None,
            help="Project folder (default: --project / .)",
        )
        p.set_defaults(func=_guard_entry)

    observe = gsub.add_parser("observe", help="Record Hub/forge evidence manually")
    observe.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Project folder (default: --project / .)",
    )
    observe.add_argument(
        "--tool",
        default=None,
        help="Hub MCP tool name (resolve_project, session_digest, …)",
    )
    observe.add_argument(
        "--persistence-unavailable",
        action="store_true",
        help="Record that Hub and forge persistence are unavailable",
    )
    observe.set_defaults(func=_guard_entry)

    guard.set_defaults(func=_guard_entry)


def _guard_entry(args: argparse.Namespace) -> int:
    # Prefer positional path when provided by subcommand
    if getattr(args, "path", None) in (None, ""):
        args.path = "."
    # Nested: `adhd-hub guard --project X status` vs `adhd-hub guard status X`
    # argparse may leave parent --project; positional overrides when set on child.
    return cmd_guard(args)
