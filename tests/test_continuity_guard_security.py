"""Security tests for continuity guard hook/state handling."""

from __future__ import annotations

from pathlib import Path

from adhd_hub.continuity_guard.hooks_protocol import handle_hook_payload, parse_hook_stdin
from adhd_hub.continuity_guard.state import GuardState, load_state, save_state


def test_malicious_strings_remain_data(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / ".git").mkdir()
    payload = {
        "hook_event_name": "preToolUse",
        "tool_name": "Write",
        "tool_input": {
            "path": "evil.py",
            "contents": '"; rm -rf /; echo "ADHD_HUB_AUTH_TOKEN=supersecret\n',
        },
        "conversation_id": "c1",
    }
    # Must not raise / execute; deny or allow as JSON only
    out = handle_hook_payload(
        payload,
        project_dir=project,
        enrolled=True,
    )
    assert isinstance(out, dict)
    assert "permission" in out


def test_secrets_scrubbed_from_state(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / ".git").mkdir()
    state = GuardState()
    state.last_warning = "Bearer " + ("a" * 40)
    state.thread_id = "ADHD_HUB_AUTH_TOKEN=supersecretvaluehere"
    save_state(project, state)
    loaded = load_state(project)
    assert loaded.last_warning is None
    assert loaded.thread_id is None
    text = (project / ".git" / "adhd-hub" / "continuity-guard.json").read_text(
        encoding="utf-8"
    )
    assert "Bearer" not in text
    assert "ADHD_HUB_AUTH_TOKEN" not in text


def test_hook_input_never_evaled() -> None:
    # parse only — no code execution path
    evil = b'{"hook_event_name": "__import__(\'os\').system(\'true\')"}'
    data = parse_hook_stdin(evil)
    assert data["hook_event_name"].startswith("__import__")
