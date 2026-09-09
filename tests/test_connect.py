from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.connect import (
    find_candidate_projects,
    merge_codex_mcp,
    merge_cursor_mcp,
    normalize_hub_url,
    render_install_sh,
    run_connect,
    run_doctor,
)


def test_normalize_hub_url_strips_slash() -> None:
    assert normalize_hub_url("http://hub.example:8787/") == "http://hub.example:8787"


def test_merge_cursor_mcp_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    assert merge_cursor_mcp(path, "http://127.0.0.1:8787") == "created"
    assert merge_cursor_mcp(path, "http://127.0.0.1:8787") == "unchanged"
    data = path.read_text(encoding="utf-8")
    assert "adhd-hub" in data
    assert "${env:ADHD_HUB_AUTH_TOKEN}" in data
    assert "Bearer actual-secret" not in data


def test_merge_codex_mcp_updates_block(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[mcp_servers.other]\nurl = \"http://x\"\n", encoding="utf-8")
    assert merge_codex_mcp(path, "http://hub:8787") == "updated"
    text = path.read_text(encoding="utf-8")
    assert "[mcp_servers.adhd-hub]" in text
    assert 'url = "http://hub:8787/mcp"' in text
    assert "other" in text
    assert merge_codex_mcp(path, "http://hub:8787") == "unchanged"


def test_find_candidate_projects(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    other = tmp_path / "notes"
    other.mkdir()
    (other / "AGENTS.md").write_text("# hi\n", encoding="utf-8")
    found = find_candidate_projects([tmp_path])
    assert repo.resolve() in found
    assert other.resolve() in found


def test_run_connect_writes_agents_and_mcp(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()

    with patch("adhd_hub.connect.probe_hub", return_value=(True, "health ok (0.0)")):
        report = run_connect(
            project=project,
            hub_url="http://127.0.0.1:8787",
            agents=["cursor"],
            scope="project",
            install_skills_flag=False,
            skills_source="uniskela/adhd-hub",
            cursor_rule=True,
            openclaw_skills=False,
            register=False,
            find_roots=None,
            token=None,
        )

    assert report.ok
    assert (project / "AGENTS.md").is_file()
    assert (project / ".cursor" / "mcp.json").is_file()
    assert (project / ".cursor" / "rules" / "adhd-hub.mdc").is_file()
    mcp = (project / ".cursor" / "mcp.json").read_text(encoding="utf-8")
    assert "change-me" not in mcp


def test_run_doctor_reports_missing_pieces(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    project = tmp_path / "proj"
    project.mkdir()
    with patch("adhd_hub.connect.probe_hub", return_value=(False, "unreachable")):
        report = run_doctor(hub_url="http://127.0.0.1:9", project=project, token=None)
    assert not report.ok
    names = {s.name for s in report.steps}
    assert "hub" in names
    assert "AGENTS.md" in names


def test_install_sh_endpoint_has_no_token(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="super-secret-token-value",
        host="127.0.0.1",
        public_url="http://hub.test:8787",
    )
    client = TestClient(create_app(settings))
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["install"] == "/install.sh"

    resp = client.get("/install.sh")
    assert resp.status_code == 200
    body = resp.text
    assert "super-secret-token-value" not in body
    assert "http://hub.test:8787" in body
    assert "adhd-hub connect" in body


def test_render_install_sh_mentions_uvx() -> None:
    script = render_install_sh("http://example:8787")
    assert "uvx" in script
    assert "ADHD_HUB_AUTH_TOKEN" in script


def test_merge_codex_mcp_preserves_other_servers_with_brackets(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "[mcp_servers.adhd-hub]\n"
        'url = "http://old:8787/mcp"\n'
        'note = "array-like [x]"\n'
        "\n"
        "[mcp_servers.other]\n"
        'url = "http://x"\n',
        encoding="utf-8",
    )
    assert merge_codex_mcp(path, "http://hub:8787") == "updated"
    text = path.read_text(encoding="utf-8")
    assert 'url = "http://hub:8787/mcp"' in text
    assert "[mcp_servers.other]" in text
    assert 'url = "http://x"' in text


def test_connect_reports_bad_mcp_json(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    mcp = project / ".cursor" / "mcp.json"
    mcp.parent.mkdir(parents=True)
    mcp.write_text('{"mcpServers": []}', encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    with patch("adhd_hub.connect.probe_hub", return_value=(True, "ok")):
        report = run_connect(
            project=project,
            hub_url="http://127.0.0.1:8787",
            agents=["cursor"],
            scope="project",
            install_skills_flag=False,
            skills_source="uniskela/adhd-hub",
            cursor_rule=False,
            openclaw_skills=False,
            register=False,
            find_roots=None,
            token=None,
        )
    assert any(s.name == "cursor MCP" and s.status == "error" for s in report.steps)


def test_doctor_survives_bad_project_mcp(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    project = tmp_path / "proj"
    project.mkdir()
    mcp = project / ".cursor" / "mcp.json"
    mcp.parent.mkdir(parents=True)
    mcp.write_text("{not-json", encoding="utf-8")
    with patch("adhd_hub.connect.probe_hub", return_value=(True, "ok")):
        report = run_doctor(hub_url="http://127.0.0.1:8787", project=project, token="t")
    assert any(s.name == "cursor project MCP" and s.status == "error" for s in report.steps)
