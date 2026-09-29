"""End-to-end continuity guard lifecycle simulation."""

from __future__ import annotations

import json
from pathlib import Path

from adhd_hub.continuity_guard.config import GuardConfig
from adhd_hub.continuity_guard.hooks_protocol import handle_hook_payload
from adhd_hub.continuity_guard.machine import GuardPhase
from adhd_hub.continuity_guard.state import load_state

CFG = GuardConfig(enabled=True, mode="balanced", max_stop_retries=2, checkpoint_after_mutations=3)


def test_full_lifecycle_mcp_path(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / ".git").mkdir()
    conv = "lifecycle-1"

    def hook(payload: dict) -> dict:
        payload = {**payload, "conversation_id": conv}
        return handle_hook_payload(
            payload, project_dir=project, config=CFG, enrolled=True
        )

    # 1. Substantial change begins → blocked
    out = hook(
        {
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "tool_input": {"path": "src/feature.py", "contents": "def f():\n    return 1\n"},
        }
    )
    assert out["permission"] == "deny"

    # 2–3. Hub continuity
    hook({"hook_event_name": "postToolUse", "tool_name": "MCP:resolve_project", "tool_input": {}})
    hook({"hook_event_name": "postToolUse", "tool_name": "MCP:session_digest", "tool_input": {}})
    assert load_state(project).phase_enum() == GuardPhase.active

    # 4. Mutations allowed + several edits
    assert (
        hook(
            {
                "hook_event_name": "preToolUse",
                "tool_name": "Write",
                "tool_input": {"path": "src/feature.py", "contents": "def f():\n    return 2\n"},
            }
        )["permission"]
        == "allow"
    )
    for i in range(3):
        hook(
            {
                "hook_event_name": "afterFileEdit",
                "file_path": f"/x/src/f{i}.py",
                "edits": [{"old_string": "a", "new_string": "a\n" + ("body" * 30)}],
            }
        )
    assert load_state(project).phase_enum() == GuardPhase.checkpoint_due

    # 5. preCompact reminder
    compact = hook({"hook_event_name": "preCompact", "trigger": "auto"})
    assert "checkpoint" in compact["user_message"].lower()

    # 6. Checkpoint observed
    hook(
        {
            "hook_event_name": "postToolUse",
            "tool_name": "MCP:upsert_progress",
            "tool_input": {"thread_id": "t1", "goal": "ship"},
        }
    )
    assert load_state(project).phase_enum() == GuardPhase.active

    # 7. Stop requests pause
    stop1 = hook({"hook_event_name": "stop", "status": "completed", "loop_count": 0})
    assert stop1.get("followup_message")

    # 8. Pause evidence
    hook(
        {
            "hook_event_name": "postToolUse",
            "tool_name": "MCP:pause_thread",
            "tool_input": {"thread_id": "t1", "next_step": "resume tests"},
        }
    )
    assert load_state(project).phase_enum() == GuardPhase.paused

    # 9. Stop allowed
    stop2 = hook({"hook_event_name": "stop", "status": "completed", "loop_count": 0})
    assert not stop2.get("followup_message")


def test_full_lifecycle_forge_fallback(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / ".git").mkdir()
    conv = "forge-1"

    def hook(payload: dict) -> dict:
        payload = {**payload, "conversation_id": conv}
        return handle_hook_payload(
            payload, project_dir=project, config=CFG, enrolled=True
        )

    hook(
        {
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "tool_input": {"path": "a.py", "contents": "print('hi')\n"},
        }
    )
    assert load_state(project).phase_enum() == GuardPhase.required_unestablished

    hook(
        {
            "hook_event_name": "postToolUse",
            "tool_name": "Shell",
            "tool_input": {"command": 'gh issue create --title "[ADHD] guard work"'},
            "tool_output": json.dumps(
                {"html_url": "https://github.com/uniskela/adhd-hub/issues/265", "number": 265}
            ),
        }
    )
    state = load_state(project)
    assert state.phase_enum() == GuardPhase.active
    assert state.continuity_method == "forge"

    hook(
        {
            "hook_event_name": "postToolUse",
            "tool_name": "MCP:mark_done",
            "tool_input": {"thread_id": "ignored-when-forge"},
        }
    )
    # mark_done still records done even on forge path
    assert load_state(project).phase_enum() == GuardPhase.completed
    stop = hook({"hook_event_name": "stop", "status": "completed", "loop_count": 0})
    assert not stop.get("followup_message")
