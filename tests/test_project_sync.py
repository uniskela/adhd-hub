"""Regression tests for deterministic project-sync + distribution layouts."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from adhd_hub.guidance_health import (
    AGENT_GUIDANCE_VERSION,
    ENV_CHECK_SKILL_VERSION,
    PROJECTS_SKILL_VERSION,
    SESSION_SKILL_VERSION,
)
from adhd_hub.project_sync import (
    SyncMode,
    assert_only_managed_paths,
    sync_project,
    validate_synced_tree,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _seed_downstream(tmp_path: Path) -> Path:
    """Fake consumer repo with unrelated content to preserve."""
    project = tmp_path / "consumer"
    project.mkdir()
    (project / "README.md").write_text("# Consumer\n", encoding="utf-8")
    (project / "AGENTS.md").write_text(
        "# AGENTS.md\n\n## Local notes\n\nKeep me.\n",
        encoding="utf-8",
    )
    other = project / ".agents" / "skills" / "unrelated-skill"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text("---\nname: unrelated\n---\n\nok\n", encoding="utf-8")
    (project / "skills-lock.json").write_text(
        json.dumps(
            {
                "version": 1,
                "skills": {
                    "unrelated-skill": {
                        "source": "example/skills",
                        "sourceType": "github",
                        "skillPath": "skills/unrelated/SKILL.md",
                        "computedHash": "abc123",
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project / "src").mkdir()
    (project / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    return project


def test_sync_project_clean_install_and_idempotent(tmp_path: Path) -> None:
    project = _seed_downstream(tmp_path)
    first = sync_project(project, source=REPO_ROOT, mode=SyncMode.apply)
    assert first.ok
    assert first.needs_sync

    agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "Local notes" in agents
    assert "Keep me." in agents
    assert f"adhd-hub:guidance-version:{AGENT_GUIDANCE_VERSION}" in agents
    assert "<!-- adhd-hub:project-agent:start -->" in agents

    runtime = project / ".agents" / "skills" / "env-check" / "scripts" / "check_runtime.sh"
    assert runtime.is_file()
    assert runtime.stat().st_mode & stat.S_IXUSR

    session = (project / ".agents" / "skills" / "adhd-hub-session" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert f"hub_skill_version: {SESSION_SKILL_VERSION}" in session
    assert "create_if_missing=false" in session
    assert "private LAN or Docker network alone does not protect" in session
    assert "../../docs/" not in session
    assert "github.com/uniskela/adhd-hub/blob/main/docs/" in session

    projects = (project / ".agents" / "skills" / "adhd-hub-projects" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert f"hub_skill_version: {PROJECTS_SKILL_VERSION}" in projects
    assert "create_if_missing=false" in projects
    assert "Inbox authors" in projects

    env_skill = (project / ".agents" / "skills" / "env-check" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert f"hub_skill_version: {ENV_CHECK_SKILL_VERSION}" in env_skill
    assert ".agents/skills/env-check/scripts/check_runtime.sh" in env_skill
    assert "../../docs/" not in env_skill

    # Unrelated preserved
    assert (project / ".agents" / "skills" / "unrelated-skill" / "SKILL.md").is_file()
    assert (project / "src" / "app.py").read_text(encoding="utf-8") == "print('hi')\n"
    lock = json.loads((project / "skills-lock.json").read_text(encoding="utf-8"))
    assert "unrelated-skill" in lock["skills"]
    assert lock["skills"]["unrelated-skill"]["computedHash"] == "abc123"
    assert "adhd-hub-session" in lock["skills"]

    assert validate_synced_tree(project) == []

    second = sync_project(project, source=REPO_ROOT, mode=SyncMode.apply)
    assert second.ok
    assert not second.needs_sync

    check = sync_project(project, source=REPO_ROOT, mode=SyncMode.check)
    assert check.ok
    assert not check.needs_sync


def test_sync_project_upgrades_stale_skills(tmp_path: Path) -> None:
    project = _seed_downstream(tmp_path)
    stale = project / ".agents" / "skills" / "adhd-hub-session"
    stale.mkdir(parents=True)
    (stale / "SKILL.md").write_text(
        "---\nname: adhd-hub-session\nhub_skill_version: 1\n---\n\nold\n",
        encoding="utf-8",
    )
    result = sync_project(project, source=REPO_ROOT, mode=SyncMode.apply)
    assert result.ok
    text = (stale / "SKILL.md").read_text(encoding="utf-8")
    assert f"hub_skill_version: {SESSION_SKILL_VERSION}" in text
    assert "old\n" not in text or "hub_skill_version: 1" not in text


def test_sync_project_malformed_agents_fails_safe(tmp_path: Path) -> None:
    project = _seed_downstream(tmp_path)
    (project / "AGENTS.md").write_text(
        "# AGENTS.md\n\n<!-- adhd-hub:project-agent:start -->\nbroken\n",
        encoding="utf-8",
    )
    before = (project / "AGENTS.md").read_text(encoding="utf-8")
    result = sync_project(project, source=REPO_ROOT, mode=SyncMode.apply)
    assert not result.ok
    assert any("incomplete" in e for e in result.errors)
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == before
    assert not (project / ".agents" / "skills" / "adhd-hub-session").exists()


def test_sync_project_check_and_dry_run(tmp_path: Path) -> None:
    project = _seed_downstream(tmp_path)
    check = sync_project(project, source=REPO_ROOT, mode=SyncMode.check)
    assert check.needs_sync
    assert not (project / ".agents" / "skills" / "adhd-hub-session").exists()

    dry = sync_project(project, source=REPO_ROOT, mode=SyncMode.dry_run)
    assert dry.needs_sync
    assert not (project / ".agents" / "skills" / "adhd-hub-session").exists()


def test_assert_only_managed_paths() -> None:
    bad = assert_only_managed_paths(
        [
            "AGENTS.md",
            ".agents/skills/adhd-hub-session/SKILL.md",
            "src/app.py",
            "skills-lock.json",
        ]
    )
    assert bad == ["src/app.py"]


def test_canonical_skills_portable_and_hardened() -> None:
    session = (REPO_ROOT / "skills/adhd-hub-session/SKILL.md").read_text(encoding="utf-8")
    assert "hub_skill_version: 6" in session
    assert "create_if_missing=false" in session
    assert "private LAN or Docker network alone does not protect" in session
    assert "../../docs/" not in session

    reference = (REPO_ROOT / "skills/adhd-hub-session/reference.md").read_text(encoding="utf-8")
    assert "private LAN or Docker network alone does not protect" in reference
    assert "../../docs/" not in reference
    assert "create_if_missing=false" in reference

    projects = (REPO_ROOT / "skills/adhd-hub-projects/SKILL.md").read_text(encoding="utf-8")
    assert "hub_skill_version: 5" in projects
    assert "create_if_missing=false" in projects
    assert "Inbox authors" in projects
    assert "../../docs/" not in projects

    env_check = (REPO_ROOT / "skills/env-check/SKILL.md").read_text(encoding="utf-8")
    assert "hub_skill_version: 3" in env_check
    assert ".agents/skills/env-check/scripts/check_runtime.sh" in env_check
    assert "skills/env-check/scripts/check_runtime.sh" in env_check
    assert "../../docs/" not in env_check


def test_workflow_is_reusable_workflow_call() -> None:
    text = (REPO_ROOT / ".github/workflows/sync-project.yml").read_text(encoding="utf-8")
    assert "workflow_call:" in text
    assert "adhd-hub sync-project" in text
    assert "pull-requests: write" in text
    assert "force-with-lease" in text
    assert "never" in text.lower() or "Auto-merge is not enabled" in text
    assert "uniskela/adhd-hub" in text


def test_cli_sync_project_check(tmp_path: Path) -> None:
    from argparse import Namespace

    from adhd_hub.cli import cmd_sync_project

    project = _seed_downstream(tmp_path)
    code = cmd_sync_project(
        Namespace(
            path=str(project),
            source=str(REPO_ROOT),
            agents="cursor,codex",
            check=True,
            dry_run=False,
        )
    )
    assert code == 1
    code2 = cmd_sync_project(
        Namespace(
            path=str(project),
            source=str(REPO_ROOT),
            agents="cursor,codex",
            check=False,
            dry_run=False,
        )
    )
    assert code2 == 0
    code3 = cmd_sync_project(
        Namespace(
            path=str(project),
            source=str(REPO_ROOT),
            agents="cursor,codex",
            check=True,
            dry_run=False,
        )
    )
    assert code3 == 0


@pytest.mark.skipif(os.name == "nt", reason="executable bit semantics differ on Windows")
def test_executable_bit_preserved_on_resync(tmp_path: Path) -> None:
    project = _seed_downstream(tmp_path)
    sync_project(project, source=REPO_ROOT, mode=SyncMode.apply)
    runtime = project / ".agents" / "skills" / "env-check" / "scripts" / "check_runtime.sh"
    runtime.chmod(runtime.stat().st_mode | 0o111)
    sync_project(project, source=REPO_ROOT, mode=SyncMode.apply)
    assert runtime.stat().st_mode & stat.S_IXUSR
