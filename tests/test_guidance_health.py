from __future__ import annotations

from pathlib import Path

from adhd_hub.connect import expected_cursor_rule_text, run_doctor
from adhd_hub.guidance_health import (
    AGENT_GUIDANCE_VERSION,
    BEGIN_MARKER,
    END_MARKER,
    HUB_OWNED_SKILLS,
    GuidanceStatus,
    inspect_agents_md,
    inspect_hub_skill,
    inspect_project_continuity,
    version_marker,
)
from adhd_hub.project_setup import agent_block, install_agent_guidance


def test_current_managed_block_is_healthy(tmp_path: Path) -> None:
    install_agent_guidance(tmp_path)
    health = inspect_agents_md(tmp_path, expected_body=agent_block())
    assert health.status == GuidanceStatus.current
    assert health.installed_version == AGENT_GUIDANCE_VERSION


def test_old_guidance_version_is_stale(tmp_path: Path) -> None:
    old = (
        f"{BEGIN_MARKER}\n"
        f"{version_marker(1)}\n"
        "## ADHD Hub continuity\n\n- old instructions\n"
        f"{END_MARKER}\n"
    )
    (tmp_path / "AGENTS.md").write_text("# Keep me\n\n" + old, encoding="utf-8")
    health = inspect_agents_md(tmp_path, expected_body=agent_block())
    assert health.status == GuidanceStatus.outdated
    assert health.installed_version == 1
    assert health.expected_version == AGENT_GUIDANCE_VERSION


def test_unversioned_block_is_stale(tmp_path: Path) -> None:
    old = f"{BEGIN_MARKER}\n## ADHD Hub continuity\n\n- legacy\n{END_MARKER}\n"
    (tmp_path / "AGENTS.md").write_text(old, encoding="utf-8")
    health = inspect_agents_md(tmp_path, expected_body=agent_block())
    assert health.status == GuidanceStatus.outdated
    assert health.installed_version is None


def test_missing_block(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Team rules only\n", encoding="utf-8")
    health = inspect_agents_md(tmp_path, expected_body=agent_block())
    assert health.status == GuidanceStatus.missing


def test_malformed_markers_no_destructive_rewrite(tmp_path: Path) -> None:
    broken = BEGIN_MARKER + "\nno end\n"
    path = tmp_path / "AGENTS.md"
    path.write_text(broken, encoding="utf-8")
    health = inspect_agents_md(tmp_path, expected_body=agent_block())
    assert health.status == GuidanceStatus.malformed
    try:
        install_agent_guidance(tmp_path)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "incomplete" in str(exc).lower()
    assert path.read_text(encoding="utf-8") == broken


def test_user_content_survives_refresh(tmp_path: Path) -> None:
    custom = "# Team rules\n\n- Keep this forever.\n\n"
    (tmp_path / "AGENTS.md").write_text(custom, encoding="utf-8")
    install_agent_guidance(tmp_path)
    install_agent_guidance(tmp_path)  # idempotent
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith("# Team rules\n\n- Keep this forever.")
    assert text.count(BEGIN_MARKER) == 1
    assert version_marker(AGENT_GUIDANCE_VERSION) in text


def test_locally_modified_same_version(tmp_path: Path) -> None:
    install_agent_guidance(tmp_path)
    path = tmp_path / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("Skip Hub for trivial", "SKIP HUB TWEAKED")
    path.write_text(text, encoding="utf-8")
    health = inspect_agents_md(tmp_path, expected_body=agent_block())
    assert health.status == GuidanceStatus.locally_modified


def test_hub_skill_current_and_stale(tmp_path: Path, monkeypatch) -> None:
    skills_root = tmp_path / ".agents" / "skills" / "adhd-hub-session"
    skills_root.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    # Force home-based search by using empty project without local skills
    (skills_root / "SKILL.md").write_text(
        "---\nname: adhd-hub-session\nhub_skill_version: 2\n---\n\n# ok\n",
        encoding="utf-8",
    )
    healthy = inspect_hub_skill(
        "adhd-hub-session",
        expected_version=HUB_OWNED_SKILLS["adhd-hub-session"],
        project_dir=tmp_path / "proj",
    )
    assert healthy.status == GuidanceStatus.current

    (skills_root / "SKILL.md").write_text(
        "---\nname: adhd-hub-session\nhub_skill_version: 1\n---\n\n# old\n",
        encoding="utf-8",
    )
    stale = inspect_hub_skill(
        "adhd-hub-session",
        expected_version=HUB_OWNED_SKILLS["adhd-hub-session"],
        project_dir=tmp_path / "proj",
    )
    assert stale.status == GuidanceStatus.outdated
    assert stale.installed_version == 1


def test_unrelated_skill_not_in_hub_owned(tmp_path: Path) -> None:
    assert "graphify" not in HUB_OWNED_SKILLS
    assert "superpowers" not in HUB_OWNED_SKILLS
    foreign = tmp_path / "skills" / "graphify"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("# foreign\n", encoding="utf-8")
    # Hub inventory only inspects owned names
    items = inspect_project_continuity(
        tmp_path,
        expected_agents_block=agent_block(),
        expected_cursor_rule=expected_cursor_rule_text(),
        check_skills=True,
    )
    assert all(not i.name.startswith("graphify") for i in items)
    assert (foreign / "SKILL.md").read_text(encoding="utf-8") == "# foreign\n"


def test_doctor_reports_drift(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "AGENTS.md").write_text(
        f"{BEGIN_MARKER}\n{version_marker(1)}\n## old\n{END_MARKER}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    with __import__("unittest.mock").mock.patch(
        "adhd_hub.connect.probe_hub", return_value=(True, "health ok")
    ):
        report = run_doctor(hub_url="http://127.0.0.1:9", project=project, token=None)
    names = {s.name: s for s in report.steps}
    assert names["AGENTS.md guidance"].status == "warn"
    assert "v1" in names["AGENTS.md guidance"].detail
    assert report.continuity_text
    assert "Do next" in report.continuity_text
    assert "adhd-hub setup" in report.continuity_text


def test_repair_updates_without_duplicating(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        f"# Intro\n\n{BEGIN_MARKER}\n{version_marker(1)}\n## old\n{END_MARKER}\n\n# Footer\n",
        encoding="utf-8",
    )
    install_agent_guidance(tmp_path)
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert text.count(BEGIN_MARKER) == 1
    assert version_marker(AGENT_GUIDANCE_VERSION) in text
    assert "# Intro" in text and "# Footer" in text
    health = inspect_agents_md(tmp_path, expected_body=agent_block())
    assert health.status == GuidanceStatus.current


def test_package_release_independent_of_guidance_version() -> None:
    from adhd_hub import __version__

    # Guidance schema version is independent; bumping package alone does not
    # require bumping AGENT_GUIDANCE_VERSION.
    assert isinstance(__version__, str)
    assert AGENT_GUIDANCE_VERSION >= 2


def test_session_digest_guidance_honesty(tmp_path: Path) -> None:
    from adhd_hub.config import Settings
    from adhd_hub.service import HubService

    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    digest = service.session_digest(workspace_path=str(tmp_path))
    assert digest.guidance is not None
    assert digest.guidance["expected_version"] == AGENT_GUIDANCE_VERSION
    assert digest.guidance["status"] == "local_verification_required"
    assert digest.guidance["last_verified_version"] is None

    service.resolve_project(
        workspace_path=str(tmp_path), create_if_missing=True, title="Demo"
    )
    service.record_guidance_verification(
        workspace_path=str(tmp_path),
        agent_guidance_version=AGENT_GUIDANCE_VERSION,
        source="test",
    )
    digest2 = service.session_digest(workspace_path=str(tmp_path))
    assert digest2.guidance["last_verified_version"] == AGENT_GUIDANCE_VERSION
    assert digest2.guidance["status"] == "last_verified_current"
