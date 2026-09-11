from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from adhd_hub.project_setup import (
    BEGIN_MARKER,
    agent_block,
    install_agent_guidance,
    install_skills,
    uninstall_agent_guidance,
)


def test_agent_block_requires_loud_mcp_down() -> None:
    text = agent_block()
    assert "first line" in text.lower()
    assert "not available" in text.lower()
    assert "Hub MCP" in text
    assert "ADHD_HUB_AUTH_TOKEN" in text
    assert "/mcp" in text
    assert "invent Hub state" in text
    assert "leave a concise local handoff instead of claiming" not in text
    assert "adhd-hub:guidance-version:" in text


def test_session_skill_requires_loud_mcp_down() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    text = (repo_root / "skills/adhd-hub-session/SKILL.md").read_text(encoding="utf-8")
    assert "first line" in text.lower()
    assert "not available" in text.lower()
    assert "say so briefly" not in text.lower()
    assert "Do not call Hub tools for trivial/read-only questions" in text
    assert "Repeat the warning only if Hub status changes" in text
    assert "One thread = one independently finishable outcome" in text
    assert "force_new_thread" in text
    assert "Use the forge mailbox only when forge issue-write access is available" in text
    assert "safe for the repository's visibility" in text
    assert "absolute local workspace paths" in text
    assert "thread_id" in text
    assert "../../docs/writing.md" not in text


def test_install_creates_agents_file_and_is_idempotent(tmp_path: Path) -> None:
    path, action = install_agent_guidance(tmp_path)
    first = path.read_text(encoding="utf-8")

    assert action == "created"
    assert first.startswith("# AGENTS.md")
    assert first.count(BEGIN_MARKER) == 1
    assert "resolve_project" in first
    assert "Skip Hub for trivial" in first
    assert "independently finishable outcome" in first
    assert "thread_id" in first
    assert "transcripts" in first

    same_path, second_action = install_agent_guidance(tmp_path)
    assert same_path == path
    assert second_action == "unchanged"
    assert path.read_text(encoding="utf-8") == first


def test_install_preserves_existing_content_and_uninstall_removes_only_block(
    tmp_path: Path,
) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Team rules\n\n- Keep this.\n", encoding="utf-8")

    install_agent_guidance(tmp_path)
    installed = agents.read_text(encoding="utf-8")
    assert installed.startswith("# Team rules\n\n- Keep this.")

    path, action = uninstall_agent_guidance(tmp_path)
    assert action == "removed"
    assert path.read_text(encoding="utf-8") == "# Team rules\n\n- Keep this.\n"


def test_install_rejects_incomplete_managed_block(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(BEGIN_MARKER + "\nbroken\n", encoding="utf-8")

    with pytest.raises(ValueError, match="incomplete ADHD Hub managed block"):
        install_agent_guidance(tmp_path)


def test_install_skills_uses_argument_list_without_shell() -> None:
    completed = Mock(returncode=0)
    with (
        patch("adhd_hub.project_setup.shutil.which", side_effect=lambda name: "npx" if name == "npx" else None),
        patch("adhd_hub.project_setup.subprocess.run", return_value=completed) as run,
    ):
        assert install_skills("./skills", agents=["cursor"]) == 0

    run.assert_called_once_with(
        [
            "npx",
            "skills",
            "add",
            "./skills",
            "-g",
            "-y",
            "--skill",
            "*",
            "-a",
            "cursor",
        ],
        check=False,
    )


def test_install_skills_maps_claude_alias_to_claude_code() -> None:
    completed = Mock(returncode=0)
    with (
        patch("adhd_hub.project_setup.shutil.which", side_effect=lambda name: "npx" if name == "npx" else None),
        patch("adhd_hub.project_setup.subprocess.run", return_value=completed) as run,
    ):
        assert install_skills("./skills", agents=["claude", "cursor"]) == 0

    run.assert_called_once_with(
        [
            "npx",
            "skills",
            "add",
            "./skills",
            "-g",
            "-y",
            "--skill",
            "*",
            "-a",
            "claude-code",
            "-a",
            "cursor",
        ],
        check=False,
    )


def test_install_skills_requires_agents_when_not_all() -> None:
    with (
        patch("adhd_hub.project_setup.shutil.which", side_effect=lambda name: "npx" if name == "npx" else None),
        patch("adhd_hub.project_setup.subprocess.run") as run,
    ):
        assert install_skills("./skills", agents=[]) == 2
    run.assert_not_called()


def test_normalize_skills_agents_aliases() -> None:
    from adhd_hub.project_setup import normalize_skills_agents

    assert normalize_skills_agents(["Claude", "claude-code", "*"]) == ["claude-code"]
