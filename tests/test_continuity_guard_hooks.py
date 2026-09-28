"""Hook payload → Cursor protocol response tests."""

from __future__ import annotations

import json
from pathlib import Path

from adhd_hub.continuity_guard.config import GuardConfig
from adhd_hub.continuity_guard.hooks_protocol import handle_hook_payload, parse_hook_stdin
from adhd_hub.continuity_guard.machine import GuardPhase
from adhd_hub.continuity_guard.state import load_state, save_state

CFG = GuardConfig(enabled=True, mode="balanced", max_stop_retries=2, checkpoint_after_mutations=3)


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "repo"
    project.mkdir()
    (project / ".git").mkdir()
    return project


def test_parse_malformed_json_fails_safe() -> None:
    assert parse_hook_stdin(b"not-json{") == {}
    assert parse_hook_stdin(b"") == {}
    assert parse_hook_stdin(b"[1,2,3]") == {}


def test_read_only_tool_allowed(tmp_path: Path) -> None:
    project = _project(tmp_path)
    out = handle_hook_payload(
        {
            "hook_event_name": "preToolUse",
            "tool_name": "Read",
            "tool_input": {"path": "README.md"},
            "conversation_id": "c1",
        },
        project_dir=project,
        config=CFG,
        enrolled=True,
    )
    assert out.get("permission") == "allow"
    assert load_state(project).phase_enum() == GuardPhase.not_required


def test_mutation_blocked_without_continuity(tmp_path: Path) -> None:
    project = _project(tmp_path)
    out = handle_hook_payload(
        {
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "tool_input": {
                "path": "src/app.py",
                "contents": "def main():\n    return 1\n",
            },
            "conversation_id": "c1",
        },
        project_dir=project,
        config=CFG,
        enrolled=True,
    )
    assert out.get("permission") == "deny"
    assert "continuity" in (out.get("agent_message") or "").lower()
    assert load_state(project).phase_enum() == GuardPhase.required_unestablished


def test_hub_mcp_post_establishes_continuity(tmp_path: Path) -> None:
    project = _project(tmp_path)
    # Seed required_unestablished
    handle_hook_payload(
        {
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "tool_input": {"path": "a.py", "contents": "x = 1\n"},
            "conversation_id": "c1",
        },
        project_dir=project,
        config=CFG,
        enrolled=True,
    )
    handle_hook_payload(
        {
            "hook_event_name": "postToolUse",
            "tool_name": "MCP:resolve_project",
            "tool_input": {"workspace_path": ".", "create_if_missing": False},
            "conversation_id": "c1",
        },
        project_dir=project,
        config=CFG,
        enrolled=True,
    )
    handle_hook_payload(
        {
            "hook_event_name": "postToolUse",
            "tool_name": "MCP:session_digest",
            "tool_input": {"query": "feature work"},
            "conversation_id": "c1",
        },
        project_dir=project,
        config=CFG,
        enrolled=True,
    )
    state = load_state(project)
    assert state.evidence_resolve and state.evidence_digest
    assert state.phase_enum() == GuardPhase.active

    # Mutation now allowed
    out = handle_hook_payload(
        {
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "tool_input": {"path": "b.py", "contents": "y = 2\n"},
            "conversation_id": "c1",
        },
        project_dir=project,
        config=CFG,
        enrolled=True,
    )
    assert out.get("permission") == "allow"


def test_forge_action_observed(tmp_path: Path) -> None:
    project = _project(tmp_path)
    handle_hook_payload(
        {
            "hook_event_name": "postToolUse",
            "tool_name": "Shell",
            "tool_input": {
                "command": 'gh issue create --title "[ADHD] ship guard" --body "Goal"'
            },
            "tool_output": json.dumps(
                {"url": "https://github.com/uniskela/adhd-hub/issues/265"}
            ),
            "conversation_id": "c1",
        },
        project_dir=project,
        config=CFG,
        enrolled=True,
    )
    state = load_state(project)
    assert state.evidence_forge_fallback
    assert state.fallback_issue_number == 265
    assert state.phase_enum() == GuardPhase.active


def test_after_file_edit_counts(tmp_path: Path) -> None:
    project = _project(tmp_path)
    # Establish first so we reach checkpoint_due
    state = load_state(project)
    state.evidence_resolve = True
    state.evidence_digest = True
    state.set_phase(GuardPhase.active)
    save_state(project, state)
    for i in range(3):
        handle_hook_payload(
            {
                "hook_event_name": "afterFileEdit",
                "file_path": f"/tmp/src/mod{i}.py",
                "edits": [
                    {"old_string": "a", "new_string": "a\n" + ("x" * 100)},
                ],
                "conversation_id": "c1",
            },
            project_dir=project,
            config=CFG,
            enrolled=True,
        )
    assert load_state(project).phase_enum() == GuardPhase.checkpoint_due


def test_precompact_user_message_when_due(tmp_path: Path) -> None:
    project = _project(tmp_path)
    state = load_state(project)
    state.meaningful_work = True
    state.mutations_since_checkpoint = 2
    state.set_phase(GuardPhase.checkpoint_due)
    save_state(project, state)
    out = handle_hook_payload(
        {
            "hook_event_name": "preCompact",
            "trigger": "auto",
            "conversation_id": "c1",
        },
        project_dir=project,
        config=CFG,
        enrolled=True,
    )
    assert "checkpoint" in (out.get("user_message") or "").lower()


def test_stop_followup_then_allow_after_cap(tmp_path: Path) -> None:
    project = _project(tmp_path)
    handle_hook_payload(
        {
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "tool_input": {"path": "a.py", "contents": "print(1)\n"},
            "conversation_id": "c1",
        },
        project_dir=project,
        config=CFG,
        enrolled=True,
    )
    out1 = handle_hook_payload(
        {
            "hook_event_name": "stop",
            "status": "completed",
            "loop_count": 0,
            "conversation_id": "c1",
        },
        project_dir=project,
        config=CFG,
        enrolled=True,
    )
    assert out1.get("followup_message")
    out2 = handle_hook_payload(
        {
            "hook_event_name": "stop",
            "status": "completed",
            "loop_count": 2,
            "conversation_id": "c1",
        },
        project_dir=project,
        config=CFG,
        enrolled=True,
    )
    assert out2 == {} or not out2.get("followup_message")


def test_unenrolled_returns_empty(tmp_path: Path) -> None:
    project = _project(tmp_path)
    out = handle_hook_payload(
        {
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "tool_input": {"path": "a.py", "contents": "x"},
        },
        project_dir=project,
        config=GuardConfig(enabled=False),
        enrolled=False,
    )
    assert out == {}
