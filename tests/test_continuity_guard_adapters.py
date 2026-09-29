"""Multi-agent continuity-guard adapter tests."""

from __future__ import annotations

import json
import stat
from pathlib import Path

from adhd_hub.continuity_guard.adapter_protocol import (
    detect_adapter,
    normalize_payload_for_guard,
    translate_response_for_adapter,
)
from adhd_hub.continuity_guard.agent_sync import ADAPTER_STRENGTH, merge_claude_settings
from adhd_hub.continuity_guard.hooks_protocol import handle_hook_payload
from adhd_hub.project_sync import SyncMode, sync_project, uninstall_continuity_guard

REPO_ROOT = Path(__file__).resolve().parents[1]


def _seed(tmp_path: Path) -> Path:
    project = tmp_path / "consumer"
    project.mkdir()
    (project / "README.md").write_text("# C\n", encoding="utf-8")
    (project / "AGENTS.md").write_text("# AGENTS\n\nKeep me.\n", encoding="utf-8")
    return project


def test_adapter_strength_documents_all_surfaces() -> None:
    assert set(ADAPTER_STRENGTH) >= {"cursor", "claude", "codex", "openclaw"}
    assert ADAPTER_STRENGTH["cursor"]["level"] == "strong"
    assert ADAPTER_STRENGTH["claude"]["level"] == "medium"
    assert ADAPTER_STRENGTH["codex"]["level"] == "advisory"
    assert ADAPTER_STRENGTH["openclaw"]["level"] == "advisory"


def test_detect_and_normalize_claude_pretool() -> None:
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess-1",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
    }
    assert detect_adapter(payload) == "claude"
    normalized = normalize_payload_for_guard(payload, adapter="claude")
    assert normalized["hook_event_name"] == "preToolUse"
    assert normalized["conversation_id"] == "sess-1"
    assert normalized["command"] == "echo hi"


def test_translate_deny_and_stop_for_claude() -> None:
    deny = translate_response_for_adapter(
        {
            "permission": "deny",
            "agent_message": "need continuity",
        },
        adapter="claude",
        original_event="PreToolUse",
    )
    assert deny["hookSpecificOutput"]["permissionDecision"] == "deny"
    stop = translate_response_for_adapter(
        {"followup_message": "checkpoint please"},
        adapter="claude",
        original_event="Stop",
    )
    assert stop == {"decision": "block", "reason": "checkpoint please"}


def test_claude_pretool_deny_via_handle_hook(tmp_path: Path) -> None:
    project = _seed(tmp_path)
    sync_project(project, source=REPO_ROOT, mode=SyncMode.apply, continuity_guard=True)
    # Force required_unestablished by beginning then pretending meaningful without evidence.
    from adhd_hub.continuity_guard.config import GuardConfig
    from adhd_hub.continuity_guard.machine import GuardEvent, GuardPhase, apply_event
    from adhd_hub.continuity_guard.state import load_state, save_state

    cfg = GuardConfig(enabled=True, mode="balanced", source="default")
    state = load_state(project)
    apply_event(state, GuardEvent.begin_session, config=cfg, conversation_id="c1")
    state.meaningful_work = True
    state.set_phase(GuardPhase.required_unestablished)
    save_state(project, state)

    claude_payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "c1",
        "tool_name": "Write",
        "tool_input": {"file_path": "src/x.py", "content": "print(1)\n"},
    }
    normalized = normalize_payload_for_guard(claude_payload, adapter="claude")
    response = handle_hook_payload(normalized, project_dir=project, enrolled=True)
    out = translate_response_for_adapter(
        response, adapter="claude", original_event="PreToolUse"
    )
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_sync_installs_claude_and_cursor(tmp_path: Path) -> None:
    project = _seed(tmp_path)
    # Preserve unrelated Claude settings.
    settings_dir = project / ".claude"
    settings_dir.mkdir(parents=True)
    (settings_dir / "settings.json").write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Bash"]},
                "hooks": {
                    "PreToolUse": [
                        {
                            "hooks": [
                                {"type": "command", "command": "./mine.sh"}
                            ]
                        }
                    ]
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = sync_project(
        project, source=REPO_ROOT, mode=SyncMode.apply, continuity_guard=True
    )
    assert result.ok
    cursor_script = project / ".cursor" / "hooks" / "adhd-hub-guard.sh"
    claude_script = project / ".claude" / "hooks" / "adhd-hub-guard.sh"
    assert cursor_script.is_file() and cursor_script.stat().st_mode & stat.S_IXUSR
    assert claude_script.is_file() and claude_script.stat().st_mode & stat.S_IXUSR
    settings = json.loads(
        (project / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert settings["permissions"]["allow"] == ["Bash"]
    pre = settings["hooks"]["PreToolUse"]
    assert any(
        isinstance(e, dict)
        and any(
            isinstance(h, dict) and "adhd-hub-guard.sh" in str(h.get("command", ""))
            for h in (e.get("hooks") or [])
        )
        for e in pre
    )
    assert any(
        isinstance(e, dict)
        and any(
            isinstance(h, dict) and h.get("command") == "./mine.sh"
            for h in (e.get("hooks") or [])
        )
        for e in pre
    )


def test_uninstall_removes_claude_hub_only(tmp_path: Path) -> None:
    project = _seed(tmp_path)
    sync_project(project, source=REPO_ROOT, mode=SyncMode.apply, continuity_guard=True)
    settings_path = project / ".claude" / "settings.json"
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    data["hooks"]["PreToolUse"].insert(
        0, {"hooks": [{"type": "command", "command": "./keep-me.sh"}]}
    )
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    removed = uninstall_continuity_guard(project)
    assert ".claude/hooks/adhd-hub-guard.sh" in removed
    assert not (project / ".claude" / "hooks" / "adhd-hub-guard.sh").exists()
    leftover = json.loads(settings_path.read_text(encoding="utf-8"))
    assert leftover["hooks"]["PreToolUse"] == [
        {"hooks": [{"type": "command", "command": "./keep-me.sh"}]}
    ]


def test_merge_claude_settings_rejects_non_list_event() -> None:
    try:
        merge_claude_settings({"hooks": {"PreToolUse": {"command": "x"}}})
        raise AssertionError("expected TypeError")
    except TypeError:
        pass
