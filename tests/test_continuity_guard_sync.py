"""Project-sync continuity-guard hooks merge tests."""

from __future__ import annotations

import json
import stat
from pathlib import Path

from adhd_hub.project_sync import (
    SyncMode,
    sync_project,
    uninstall_continuity_guard,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _seed(tmp_path: Path) -> Path:
    project = tmp_path / "consumer"
    project.mkdir()
    (project / "README.md").write_text("# C\n", encoding="utf-8")
    (project / "AGENTS.md").write_text("# AGENTS\n\nKeep me.\n", encoding="utf-8")
    return project


def test_continuity_guard_fresh_install(tmp_path: Path) -> None:
    project = _seed(tmp_path)
    result = sync_project(
        project, source=REPO_ROOT, mode=SyncMode.apply, continuity_guard=True
    )
    assert result.ok
    script = project / ".cursor" / "hooks" / "adhd-hub-guard.sh"
    assert script.is_file()
    assert script.stat().st_mode & stat.S_IXUSR
    hooks = json.loads((project / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
    assert hooks["version"] == 1
    assert any(
        ".cursor/hooks/adhd-hub-guard.sh" in e.get("command", "")
        for e in hooks["hooks"]["stop"]
    )
    assert hooks["hooks"]["stop"][0].get("loop_limit") == 2


def test_unrelated_hooks_preserved(tmp_path: Path) -> None:
    project = _seed(tmp_path)
    hooks_dir = project / ".cursor"
    hooks_dir.mkdir(parents=True)
    existing = {
        "version": 1,
        "hooks": {
            "afterFileEdit": [{"command": "./hooks/format.sh"}],
            "stop": [{"command": "./hooks/mine.sh"}],
        },
    }
    (hooks_dir / "hooks.json").write_text(
        json.dumps(existing, indent=2) + "\n", encoding="utf-8"
    )
    sync_project(project, source=REPO_ROOT, mode=SyncMode.apply, continuity_guard=True)
    hooks = json.loads((hooks_dir / "hooks.json").read_text(encoding="utf-8"))
    after_edit = hooks["hooks"]["afterFileEdit"]
    assert any(e.get("command") == "./hooks/format.sh" for e in after_edit)
    assert any("adhd-hub-guard.sh" in e.get("command", "") for e in after_edit)
    stop = hooks["hooks"]["stop"]
    assert any(e.get("command") == "./hooks/mine.sh" for e in stop)
    assert any("adhd-hub-guard.sh" in e.get("command", "") for e in stop)


def test_guard_drift_detected_and_repaired(tmp_path: Path) -> None:
    project = _seed(tmp_path)
    sync_project(project, source=REPO_ROOT, mode=SyncMode.apply, continuity_guard=True)
    hooks_path = project / ".cursor" / "hooks.json"
    data = json.loads(hooks_path.read_text(encoding="utf-8"))
    # Remove Hub stop entry to create drift
    data["hooks"]["stop"] = [e for e in data["hooks"]["stop"] if "adhd-hub" not in e.get("command", "")]
    hooks_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    check = sync_project(project, source=REPO_ROOT, mode=SyncMode.check)
    assert check.needs_sync
    sync_project(project, source=REPO_ROOT, mode=SyncMode.apply)
    repaired = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert any("adhd-hub-guard.sh" in e.get("command", "") for e in repaired["hooks"]["stop"])


def test_uninstall_removes_only_hub(tmp_path: Path) -> None:
    project = _seed(tmp_path)
    hooks_dir = project / ".cursor"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "hooks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {"afterFileEdit": [{"command": "./hooks/format.sh"}]},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    sync_project(project, source=REPO_ROOT, mode=SyncMode.apply, continuity_guard=True)
    removed = uninstall_continuity_guard(project)
    assert ".cursor/hooks/adhd-hub-guard.sh" in removed
    assert not (project / ".cursor" / "hooks" / "adhd-hub-guard.sh").exists()
    hooks = json.loads((hooks_dir / "hooks.json").read_text(encoding="utf-8"))
    assert hooks["hooks"]["afterFileEdit"] == [{"command": "./hooks/format.sh"}]
    assert "stop" not in hooks["hooks"] or not any(
        "adhd-hub" in e.get("command", "") for e in hooks["hooks"].get("stop", [])
    )


def test_uninstall_keeps_wrapper_when_hooks_json_malformed(tmp_path: Path) -> None:
    """Malformed hooks.json must not delete the wrapper (avoid half uninstall)."""
    project = _seed(tmp_path)
    sync_project(project, source=REPO_ROOT, mode=SyncMode.apply, continuity_guard=True)
    script = project / ".cursor" / "hooks" / "adhd-hub-guard.sh"
    hooks_path = project / ".cursor" / "hooks.json"
    assert script.is_file()
    assert hooks_path.is_file()
    hooks_path.write_text("{ not valid json\n", encoding="utf-8")

    removed = uninstall_continuity_guard(project)

    assert removed == []
    assert script.is_file(), "wrapper must remain when hooks.json is unreadable"
    assert hooks_path.read_text(encoding="utf-8") == "{ not valid json\n"


def test_uninstall_keeps_wrapper_when_stop_event_is_object(tmp_path: Path) -> None:
    """Non-array event values must not delete the wrapper (Hub refs would dangle)."""
    project = _seed(tmp_path)
    sync_project(project, source=REPO_ROOT, mode=SyncMode.apply, continuity_guard=True)
    script = project / ".cursor" / "hooks" / "adhd-hub-guard.sh"
    hooks_path = project / ".cursor" / "hooks.json"
    assert script.is_file()
    # stop is an object (not a list) that still embeds the Hub command.
    hooks_path.write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {
                    "stop": {
                        "command": ".cursor/hooks/adhd-hub-guard.sh",
                        "loop_limit": 2,
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    removed = uninstall_continuity_guard(project)

    assert removed == []
    assert script.is_file(), "wrapper must remain when stop is an object, not an array"
    data = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert isinstance(data["hooks"]["stop"], dict)
    assert "adhd-hub-guard.sh" in data["hooks"]["stop"]["command"]


def test_idempotent_second_sync(tmp_path: Path) -> None:
    project = _seed(tmp_path)
    sync_project(project, source=REPO_ROOT, mode=SyncMode.apply, continuity_guard=True)
    second = sync_project(
        project, source=REPO_ROOT, mode=SyncMode.apply, continuity_guard=True
    )
    assert second.ok
    assert not second.needs_sync


def test_dry_run_and_check_no_writes_without_enrollment(tmp_path: Path) -> None:
    project = _seed(tmp_path)
    dry = sync_project(
        project, source=REPO_ROOT, mode=SyncMode.dry_run, continuity_guard=True
    )
    assert dry.needs_sync
    assert not (project / ".cursor" / "hooks.json").exists()
    check = sync_project(
        project, source=REPO_ROOT, mode=SyncMode.check, continuity_guard=True
    )
    assert check.needs_sync
    assert not (project / ".cursor" / "hooks.json").exists()
