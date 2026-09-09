from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from adhd_hub.project_setup import (
    BEGIN_MARKER,
    install_agent_guidance,
    install_skills,
    uninstall_agent_guidance,
)


def test_install_creates_agents_file_and_is_idempotent(tmp_path: Path) -> None:
    path, action = install_agent_guidance(tmp_path)
    first = path.read_text(encoding="utf-8")

    assert action == "created"
    assert first.startswith("# AGENTS.md")
    assert first.count(BEGIN_MARKER) == 1
    assert "resolve_project" in first
    assert "full chat transcripts" in first

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
        assert install_skills("./skills") == 0

    run.assert_called_once_with(
        ["npx", "skills", "add", "./skills", "-g"],
        check=False,
    )
