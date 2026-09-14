from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.connect import (
    evaluate_oauth_prm_payload,
    find_candidate_projects,
    merge_codex_mcp,
    merge_cursor_mcp,
    normalize_hub_url,
    render_install_ps1,
    render_install_sh,
    run_connect,
    run_doctor,
)


def test_normalize_hub_url_strips_slash() -> None:
    assert normalize_hub_url("http://hub.example:8787/") == "http://hub.example:8787"


def test_resolve_hub_url_uses_saved_default(tmp_path: Path, monkeypatch) -> None:
    from adhd_hub.connect import resolve_hub_url
    from adhd_hub.connect_login import set_default_hub

    monkeypatch.delenv("ADHD_HUB_PUBLIC_URL", raising=False)
    monkeypatch.delenv("ADHD_HUB_HUB_URL", raising=False)
    monkeypatch.delenv("ADHD_HUB_URL", raising=False)
    monkeypatch.setenv("ADHD_HUB_CREDENTIALS", str(tmp_path / "creds.json"))
    set_default_hub("https://adhd-hub.example.com/")
    assert resolve_hub_url(None) == "https://adhd-hub.example.com"
    assert resolve_hub_url("http://127.0.0.1:8787") == "http://127.0.0.1:8787"


def test_run_use_hub_retargets_mcp_and_saves_default(tmp_path: Path, monkeypatch) -> None:
    from adhd_hub.connect import run_use_hub
    from adhd_hub.connect_login import load_saved_default_hub

    project = tmp_path / "proj"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ADHD_HUB_CREDENTIALS", str(tmp_path / "creds.json"))
    (project / ".cursor").mkdir()
    (project / ".cursor" / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "adhd-hub": {
                        "url": "http://127.0.0.1:8787/mcp",
                        "headers": {"Authorization": "Bearer ${env:ADHD_HUB_AUTH_TOKEN}"},
                    }
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    with patch("adhd_hub.connect.probe_hub", return_value=(True, "health ok")):
        report = run_use_hub(
            hub_url="https://adhd-hub.example.com/",
            project=project,
            agents=["cursor"],
            scope="project",
        )

    assert report.ok
    assert load_saved_default_hub() == "https://adhd-hub.example.com"
    mcp = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["adhd-hub"]["url"] == "https://adhd-hub.example.com/mcp"
    assert any(s.name == "default hub" and s.status == "ok" for s in report.steps)


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


def test_run_connect_dry_run_writes_nothing(tmp_path: Path, monkeypatch) -> None:
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
            install_skills_flag=True,
            skills_source="uniskela/adhd-hub",
            cursor_rule=True,
            openclaw_skills=True,
            register=True,
            find_roots=None,
            token="test-token",
            dry_run=True,
        )

    assert report.ok
    assert any(s.name == "mode" and "dry-run" in s.detail for s in report.steps)
    assert not (project / "AGENTS.md").exists()
    assert not (project / ".cursor").exists()
    assert any(
        s.name == "skills" and (s.detail.startswith("would run:") or "npx not found" in s.detail)
        for s in report.steps
    )
    assert any(s.name == "register" and s.detail.startswith("would resolve") for s in report.steps)


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
    assert "AGENTS.md guidance" in names


def test_evaluate_oauth_prm_payload_healthy() -> None:
    status, detail = evaluate_oauth_prm_payload(
        http_status=200,
        payload={
            "resource": "https://hub.example/mcp",
            "authorization_servers": ["https://hub.example"],
        },
    )
    assert status == "ok"
    assert "https://hub.example/mcp" in detail


def test_evaluate_oauth_prm_payload_warns_on_errors() -> None:
    assert evaluate_oauth_prm_payload(error="timeout")[0] == "warn"
    assert evaluate_oauth_prm_payload(http_status=404)[0] == "warn"
    assert evaluate_oauth_prm_payload(http_status=200, payload={"resource": "x"})[0] == "warn"
    assert (
        evaluate_oauth_prm_payload(
            http_status=200,
            payload={"resource": "x", "authorization_servers": []},
        )[0]
        == "warn"
    )


def test_doctor_oauth_probe_when_public_url_set(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("ADHD_HUB_PUBLIC_URL", "https://hub.example")
    monkeypatch.delenv("ADHD_HUB_OAUTH_ENABLED", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    with (
        patch("adhd_hub.connect.probe_hub", return_value=(True, "health ok")),
        patch(
            "adhd_hub.connect.probe_oauth_discovery",
            return_value=("ok", "PRM ok (https://hub.example/mcp)"),
        ) as probe,
        patch("adhd_hub.connect._doctor_remote_checks"),
    ):
        report = run_doctor(hub_url="https://hub.example", project=project, token=None)
    probe.assert_called_once_with("https://hub.example")
    step = next(s for s in report.steps if s.name == "hub oauth discovery")
    assert step.status == "ok"


def test_doctor_oauth_probes_hub_without_public_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.delenv("ADHD_HUB_PUBLIC_URL", raising=False)
    monkeypatch.delenv("ADHD_HUB_OAUTH_ENABLED", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    with (
        patch("adhd_hub.connect.probe_hub", return_value=(True, "health ok")),
        patch(
            "adhd_hub.connect.probe_oauth_discovery",
            return_value=("ok", "PRM ok (https://hub.example/mcp)"),
        ) as probe,
        patch("adhd_hub.connect._doctor_remote_checks"),
    ):
        report = run_doctor(hub_url="https://hub.example", project=project, token=None)
    probe.assert_called_once_with("https://hub.example")
    assert any(s.name == "hub oauth discovery" and s.status == "ok" for s in report.steps)


def test_doctor_oauth_warns_when_public_url_differs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("ADHD_HUB_PUBLIC_URL", "https://public.example")
    project = tmp_path / "proj"
    project.mkdir()
    with (
        patch("adhd_hub.connect.probe_hub", return_value=(True, "health ok")),
        patch(
            "adhd_hub.connect.probe_oauth_discovery",
            return_value=("ok", "PRM ok (https://hub.example/mcp)"),
        ) as probe,
        patch("adhd_hub.connect._doctor_remote_checks"),
    ):
        report = run_doctor(hub_url="https://hub.example", project=project, token=None)
    probe.assert_called_once_with("https://hub.example")
    step = next(s for s in report.steps if s.name == "hub oauth discovery")
    assert step.status == "warn"
    assert "differs" in step.detail


def test_doctor_oauth_probes_even_when_local_oauth_env_false(
    tmp_path: Path, monkeypatch
) -> None:
    """Local ADHD_HUB_OAUTH_ENABLED must not skip Hub discovery (server setting)."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("ADHD_HUB_PUBLIC_URL", "https://hub.example")
    monkeypatch.setenv("ADHD_HUB_OAUTH_ENABLED", "false")
    project = tmp_path / "proj"
    project.mkdir()
    with (
        patch("adhd_hub.connect.probe_hub", return_value=(True, "health ok")),
        patch(
            "adhd_hub.connect.probe_oauth_discovery",
            return_value=("ok", "PRM ok"),
        ) as probe,
        patch("adhd_hub.connect._doctor_remote_checks"),
    ):
        report = run_doctor(hub_url="https://hub.example", project=project, token=None)
    probe.assert_called_once()
    step = next(s for s in report.steps if s.name == "hub oauth discovery")
    assert step.status == "ok"
    assert "PRM ok" in step.detail


def test_doctor_oauth_skipped_on_loopback_without_public_url(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.delenv("ADHD_HUB_PUBLIC_URL", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    with (
        patch("adhd_hub.connect.probe_hub", return_value=(False, "unreachable")),
        patch("adhd_hub.connect.probe_oauth_discovery") as probe,
    ):
        report = run_doctor(hub_url="http://127.0.0.1:9", project=project, token=None)
    probe.assert_not_called()
    step = next(s for s in report.steps if s.name == "hub oauth discovery")
    assert step.status == "ok"
    assert "skipped" in step.detail.lower()


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
    assert root.json()["install_ps1"] == "/install.ps1"

    resp = client.get("/install.sh")
    assert resp.status_code == 200
    body = resp.text
    assert "super-secret-token-value" not in body
    assert "http://hub.test:8787" in body
    assert "adhd-hub connect" in body
    assert "macOS" in body or "Windows PowerShell" in body
    assert "WITH_I_HAVE_ADHD=0" in body

    ps1 = client.get("/install.ps1")
    assert ps1.status_code == 200
    assert "super-secret-token-value" not in ps1.text
    assert "http://hub.test:8787" in ps1.text
    assert "param(" in ps1.text
    assert "uvx" in ps1.text


def test_install_scripts_bake_saved_companions(tmp_path: Path) -> None:
    from adhd_hub.prefs import HubPrefs

    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="tok",
        host="127.0.0.1",
        public_url="http://hub.test:8787",
    )
    app = create_app(settings)
    # Persist companion prefs the same way the UI/API would.
    from adhd_hub.service import HubService

    svc = HubService(settings)
    svc.save_prefs(
        HubPrefs(
            timezone="UTC",
            connect_agents=["codex"],
            connect_companions=["i-have-adhd", "graphify"],
        )
    )
    client = TestClient(app)
    # Recreate so prefs are loaded from disk for the request handlers' service.
    client = TestClient(create_app(settings))
    sh = client.get("/install.sh").text
    assert "WITH_I_HAVE_ADHD=1" in sh
    assert "WITH_GRAPHIFY=1" in sh
    assert "WITH_RTK=0" in sh
    assert 'AGENTS="${ADHD_HUB_CONNECT_AGENTS:-codex}"' in sh
    ps1 = client.get("/install.ps1").text
    assert "if (-not $WithIHaveAdhd -and $true)" in ps1
    assert "if (-not $WithGraphify -and $true)" in ps1
    assert "if (-not $WithRtk -and $false)" in ps1


def test_render_install_sh_mentions_uvx() -> None:
    script = render_install_sh("http://example:8787")
    assert "uvx" in script
    assert "ADHD_HUB_AUTH_TOKEN" in script


def test_render_install_sh_isolates_streamed_script_from_child_stdin(
    tmp_path: Path,
) -> None:
    """A child reading stdin must not consume the unread `curl | sh` source."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    child = bin_dir / "adhd-hub"
    child.write_text(
        "#!/bin/sh\ncat\nprintf 'CHILD_FINISHED\\n'\n",
        encoding="utf-8",
    )
    child.chmod(child.stat().st_mode | stat.S_IXUSR)
    curl = bin_dir / "curl"
    curl.write_text("#!/bin/sh\nprintf 'https://example/adhd-hub.whl\\n'\n", encoding="utf-8")
    curl.chmod(curl.stat().st_mode | stat.S_IXUSR)

    script = render_install_sh("http://example:8787")
    # Exceed typical shell read buffering so the regression is deterministic.
    script += "\n# UNREAD_INSTALLER_SOURCE\n" * 2000
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "ADHD_HUB_CONNECT_NO_SKILLS": "1",
    }
    result = subprocess.run(
        ["sh", "-s", "--", "."],
        input=script,
        text=True,
        capture_output=True,
        env=env,
        check=False,
        start_new_session=True,
    )

    assert result.returncode == 0
    assert "CHILD_FINISHED" in result.stdout
    assert "UNREAD_INSTALLER_SOURCE" not in result.stdout


def test_render_install_sh_preserves_child_exit_and_quoted_project(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    child = bin_dir / "adhd-hub"
    child.write_text(
        "#!/bin/sh\nprintf 'ARG=<%s>\\n' \"$2\"\ncat\nexit 23\n",
        encoding="utf-8",
    )
    child.chmod(child.stat().st_mode | stat.S_IXUSR)
    curl = bin_dir / "curl"
    curl.write_text("#!/bin/sh\nprintf 'https://example/adhd-hub.whl\\n'\n", encoding="utf-8")
    curl.chmod(curl.stat().st_mode | stat.S_IXUSR)
    script = render_install_sh("http://example:8787")
    script += "\n# UNREAD_AFTER_FAILURE\n" * 2000
    result = subprocess.run(
        ["sh", "-s", "--", "project with spaces"],
        input=script,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:/usr/bin:/bin",
        },
        check=False,
        start_new_session=True,
    )

    assert result.returncode == 23
    assert "ARG=<project with spaces>" in result.stdout
    assert "UNREAD_AFTER_FAILURE" not in result.stdout


def test_render_install_sh_isolates_uvx_and_wheel_lookup_stdin(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "stub.log"
    curl = bin_dir / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        "value=EOF\n"
        "IFS= read -r value || true\n"
        "printf 'curl-stdin=<%s>\\n' \"$value\" >>\"$STUB_LOG\"\n"
        "printf 'https://example/adhd-hub.whl\\n'\n",
        encoding="utf-8",
    )
    uvx = bin_dir / "uvx"
    uvx.write_text(
        "#!/bin/sh\n"
        "value=EOF\n"
        "IFS= read -r value || true\n"
        "printf 'uvx-stdin=<%s>\\n' \"$value\" >>\"$STUB_LOG\"\n"
        "printf 'UVX_FINISHED\\n'\n",
        encoding="utf-8",
    )
    for stub in (curl, uvx):
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    script = render_install_sh("http://example:8787")
    script += "\n# UVX_UNREAD_INSTALLER_SOURCE\n" * 2000
    result = subprocess.run(
        ["sh", "-s", "--", "."],
        input=script,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "STUB_LOG": str(log),
            "ADHD_HUB_CLI_INSTALL_PROMPTED": "1",
        },
        check=False,
        start_new_session=True,
    )

    assert result.returncode == 0
    assert "UVX_FINISHED" in result.stdout
    assert log.read_text(encoding="utf-8").splitlines() == [
        "curl-stdin=<>",
        "uvx-stdin=<>",
    ]
    assert "UVX_UNREAD_INSTALLER_SOURCE" not in result.stdout


def test_render_install_sh_isolates_uv_bootstrap_and_install_stdin(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    log = tmp_path / "stub.log"
    bootstrap_capture = tmp_path / "bootstrap-stdin.log"
    curl = bin_dir / "curl"
    curl.write_text(
        """#!/bin/sh
value=EOF
IFS= read -r value || true
case "$*" in
  *cli-wheel.url*)
    printf 'wheel-curl-stdin=<%s>\n' "$value" >>"$STUB_LOG"
    printf 'https://example/adhd-hub.whl\n'
    ;;
  *)
    printf 'bootstrap-curl-stdin=<%s>\n' "$value" >>"$STUB_LOG"
    cat <<'BOOTSTRAP'
mkdir -p "$HOME/.local/bin"
cat >"$HOME/.local/bin/uv" <<'UV'
#!/bin/sh
value=EOF
IFS= read -r value || true
printf 'uv-install-stdin=<%s>\n' "$value" >>"$STUB_LOG"
cat >"$HOME/.local/bin/adhd-hub" <<'CLI'
#!/bin/sh
value=EOF
IFS= read -r value || true
printf 'installed-cli-stdin=<%s>\n' "$value" >>"$STUB_LOG"
printf 'BOOTSTRAP_CLI_FINISHED\n'
CLI
chmod +x "$HOME/.local/bin/adhd-hub"
UV
chmod +x "$HOME/.local/bin/uv"
cat >"$BOOTSTRAP_CAPTURE"
exit 0
BOOTSTRAP
    i=0
    while [ "$i" -lt 5000 ]; do
      printf '# bootstrap pipeline padding %s\n' "$i"
      i=$((i + 1))
    done
    printf 'BOOTSTRAP_PIPE_PAYLOAD\n'
    ;;
esac
""",
        encoding="utf-8",
    )
    curl.chmod(curl.stat().st_mode | stat.S_IXUSR)

    script = render_install_sh("http://example:8787")
    script += "\n# BOOTSTRAP_UNREAD_INSTALLER_SOURCE\n" * 2000
    result = subprocess.run(
        ["sh", "-s", "--", "."],
        input=script,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "HOME": str(home),
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "STUB_LOG": str(log),
            "BOOTSTRAP_CAPTURE": str(bootstrap_capture),
            "ADHD_HUB_INSTALL_UV": "1",
        },
        check=False,
        start_new_session=True,
    )

    assert result.returncode == 0
    assert "BOOTSTRAP_CLI_FINISHED" in result.stdout
    assert log.read_text(encoding="utf-8").splitlines() == [
        "wheel-curl-stdin=<>",
        "bootstrap-curl-stdin=<>",
        "uv-install-stdin=<>",
        "installed-cli-stdin=<>",
    ]
    assert "BOOTSTRAP_PIPE_PAYLOAD" in bootstrap_capture.read_text(encoding="utf-8")
    assert "BOOTSTRAP_UNREAD_INSTALLER_SOURCE" not in result.stdout


def test_render_install_sh_uses_controlling_terminal_for_prompt_and_children(
    tmp_path: Path,
) -> None:
    import fcntl
    import pty
    import termios

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(
        "#!/bin/sh\nprintf 'https://example/adhd-hub.whl\\n'\n",
        encoding="utf-8",
    )
    uv = bin_dir / "uv"
    uv.write_text(
        """#!/bin/sh
IFS= read -r value
printf 'UV_TTY=<%s>\n' "$value"
mkdir -p "$HOME/.local/bin"
cat >"$HOME/.local/bin/adhd-hub" <<'CLI'
#!/bin/sh
IFS= read -r value
printf 'CLI_TTY=<%s>\n' "$value"
printf 'PROJECT=<%s>\n' "$2"
CLI
chmod +x "$HOME/.local/bin/adhd-hub"
""",
        encoding="utf-8",
    )
    for stub in (curl, uv):
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    master_fd, slave_fd = pty.openpty()

    def claim_controlling_terminal() -> None:
        os.setsid()
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

    script = render_install_sh("http://example:8787")
    script += "\n# PTY_UNREAD_INSTALLER_SOURCE\n" * 2000
    os.write(master_fd, b"y\nuv-terminal-input\ncli-terminal-input\n")
    process = subprocess.Popen(
        ["sh", "-s", "--", "project with spaces"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "PATH": f"{bin_dir}:/usr/bin:/bin",
        },
        pass_fds=(slave_fd,),
        preexec_fn=claim_controlling_terminal,  # noqa: PLW1509 - child-only PTY setup
    )
    os.close(slave_fd)
    stdout, stderr = process.communicate(script, timeout=20)
    os.set_blocking(master_fd, False)
    terminal_output = b""
    while True:
        try:
            chunk = os.read(master_fd, 4096)
        except (BlockingIOError, OSError):
            break
        if not chunk:
            break
        terminal_output += chunk
    os.close(master_fd)

    assert process.returncode == 0, stderr
    assert "Install it now with uv tool install?" in terminal_output.decode(errors="replace")
    assert "UV_TTY=<uv-terminal-input>" in stdout
    assert "CLI_TTY=<cli-terminal-input>" in stdout
    assert "PROJECT=<project with spaces>" in stdout
    assert "PTY_UNREAD_INSTALLER_SOURCE" not in stdout


def test_render_install_sh_supports_flags() -> None:
    script = render_install_sh("http://example:8787")
    assert "--register" in script
    assert "--dry-run" in script
    assert "ADHD_HUB_CONNECT_FLAGS" in script
    assert "ADHD_HUB_CONNECT_AGENTS" in script
    assert "--with-i-have-adhd)" in script
    assert "--with-graphify)" in script
    assert "--with-rtk)" in script
    assert "--with-superpowers)" in script
    assert "--with-context7)" in script
    assert "--with-agent-browser)" in script
    assert "--with-serena)" in script
    assert "ADHD_HUB_CONNECT_WITH_GRAPHIFY" in script


def test_render_install_ps1_supports_flags() -> None:
    script = render_install_ps1("http://example:8787")
    assert "[switch]$Register" in script
    assert "[switch]$DryRun" in script
    assert "[switch]$WithIHaveAdhd" in script
    assert "[switch]$WithGraphify" in script
    assert "[switch]$WithRtk" in script
    assert "--with-i-have-adhd" in script
    assert "ADHD_HUB_CONNECT_WITH_RTK" in script
    assert "ADHD_HUB_CONNECT_OPENCLAW_SKILLS" in script
    assert "iwr $HubUrl/install.ps1 -OutFile" in script
    # Empty ValidateSet default breaks `irm | iex` on Windows.
    assert '[ValidateSet("project", "user")][string]$Scope = "project"' in script
    assert '[ValidateSet("project", "user")][string]$Scope = ""' not in script
    assert "git+https://github.com/uniskela/adhd-hub.git" in script
    assert "uvx --from adhd-hub " not in script
    assert "install/cli-wheel.url" in script
    assert "uvx --refresh --from $pkgFrom" in script
    # irm|iex must not call bare `exit` (closes the interactive host).
    assert "Complete-AdhdInstall" in script
    assert "if ($PSCommandPath) { exit $Code }" in script
    assert "exit $LASTEXITCODE" not in script
    assert 'else { $Agents = "cursor" }' not in script
    assert "Doctor (uvx" in script
    assert "adhd-hub is not on PATH yet" in script


def test_render_install_sh_mentions_uvx_doctor_when_cli_missing() -> None:
    script = render_install_sh("http://example:8787")
    assert "_adhd_after_connect" in script
    assert "Doctor (uvx" in script
    assert "exec uvx" not in script


def test_render_install_bakes_default_agents() -> None:
    sh = render_install_sh("http://example:8787", default_agents="codex")
    assert 'AGENTS="${ADHD_HUB_CONNECT_AGENTS:-codex}"' in sh
    assert 'AGENTS="${ADHD_HUB_CONNECT_AGENTS:-cursor}"' not in sh
    ps1 = render_install_ps1("http://example:8787", default_agents="cursor,claude")
    assert '$DefaultAgents = "cursor,claude"' in ps1


def test_render_install_bakes_companion_defaults() -> None:
    sh = render_install_sh(
        "http://example:8787",
        with_i_have_adhd=True,
        with_graphify=True,
        with_rtk=False,
        with_context7=True,
        with_serena=True,
    )
    assert "WITH_I_HAVE_ADHD=1" in sh
    assert "WITH_GRAPHIFY=1" in sh
    assert "WITH_RTK=0" in sh
    assert "WITH_CONTEXT7=1" in sh
    assert "WITH_SERENA=1" in sh
    assert "WITH_SUPERPOWERS=0" in sh
    assert "--with-context7" in sh
    ps1 = render_install_ps1(
        "http://example:8787",
        with_rtk=True,
        with_graphify=False,
        with_agent_browser=True,
        with_superpowers=True,
    )
    assert "if (-not $WithRtk -and $true)" in ps1
    assert "if (-not $WithGraphify -and $false)" in ps1
    assert "if (-not $WithAgentBrowser -and $true)" in ps1
    assert "if (-not $WithSuperpowers -and $true)" in ps1
    assert "--with-agent-browser" in ps1


def test_print_report_shows_complete_banner(capsys, monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    from adhd_hub.connect import ConnectReport, print_report

    report = ConnectReport(hub_url="http://127.0.0.1:8787")
    report.add("hub probe", "ok", "reachable")
    report.add(
        "setup complete",
        "ok",
        "Open http://127.0.0.1:8787/ui · run: uvx --refresh --from "
        '"http://127.0.0.1:8787/install/wheels/x.whl" adhd-hub doctor --hub '
        "http://127.0.0.1:8787 --project C:\\Users\\alexp",
    )
    print_report(report)
    out = capsys.readouterr().out
    assert "Complete! ADHD Hub is connected." in out
    assert "Do next:" in out
    assert "http://127.0.0.1:8787/ui" in out
    assert "Verify anytime:" in out
    assert "uvx --refresh --from" in out


def test_print_report_default_collapses_ok(capsys, monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    from adhd_hub.connect import ConnectReport, print_report

    report = ConnectReport(hub_url="http://127.0.0.1:8787")
    report.add("hub probe", "ok", "health ok")
    report.add("cursor MCP (project)", "ok", "unchanged")
    report.add("companion graphify", "ok", "on PATH")
    report.add(
        "setup complete",
        "ok",
        "Open http://127.0.0.1:8787/ui · run: uvx doctor-demo",
    )
    print_report(report, verbose=False)
    out = capsys.readouterr().out
    assert "Complete! ADHD Hub is connected." in out
    assert "Do next:" in out
    assert "pick what fits" in out
    assert "coding-companions.md" in out
    assert "Done:" in out
    assert "Hub ·" in out and "ok" in out
    assert "Agents ·" in out
    assert "Companions ·" in out
    assert "[OK] hub probe:" not in out
    assert "Needs attention:" not in out


def test_print_report_verbose_lists_all_steps(capsys, monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    from adhd_hub.connect import ConnectReport, print_report

    report = ConnectReport(hub_url="http://127.0.0.1:8787")
    report.add("hub probe", "ok", "health ok")
    print_report(report, verbose=True)
    out = capsys.readouterr().out
    assert "[OK] hub probe: health ok" in out


def test_print_report_fix_these_on_error(capsys, monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    from adhd_hub.connect import ConnectReport, print_report

    report = ConnectReport(hub_url="http://127.0.0.1:8787")
    report.add("hub probe", "ok", "health ok")
    report.add("install rtk binary", "error", "rtk not on PATH")
    report.add("companions agents", "manual", "soft tip only")
    print_report(report, verbose=False)
    out = capsys.readouterr().out
    assert "Connect finished with errors" in out
    assert "Fix these:" in out
    assert "1. install rtk binary — rtk not on PATH" in out
    assert "companions agents" not in out.split("Fix these:")[1].split("Needs attention:")[0]
    assert "Needs attention:" in out
    assert "[XX] install rtk binary:" in out
    assert "[--] companions agents:" in out
    assert "Done:" in out


def test_classify_step_group_hub_claude_openclaw() -> None:
    from adhd_hub.connect import classify_step_group

    assert classify_step_group("hub") == "Hub"
    assert classify_step_group("claude MCP") == "Agents"
    assert classify_step_group("openclaw pair") == "Agents"


def test_format_hub_cli_command_uses_uvx_when_missing(monkeypatch) -> None:
    from adhd_hub import connect as connect_mod

    monkeypatch.setattr(
        connect_mod.shutil,
        "which",
        lambda name: "uvx" if name in {"uvx", "uvx.exe"} else None,
    )
    monkeypatch.setattr(
        connect_mod,
        "resolve_uv_package_from",
        lambda hub: "http://127.0.0.1:8787/install/wheels/demo.whl",
    )
    cmd = connect_mod.format_hub_cli_command(
        "http://127.0.0.1:8787",
        "doctor",
        "--hub",
        "http://127.0.0.1:8787",
        "--project",
        r"C:\Users\alexp",
    )
    assert cmd.startswith('uvx --refresh --from "http://127.0.0.1:8787/install/wheels/demo.whl"')
    assert "adhd-hub doctor" in cmd
    assert "adhd-hub doctor --hub http://127.0.0.1:8787" in cmd


def test_format_hub_cli_command_uses_uvx_for_ephemeral_cache_binary(monkeypatch) -> None:
    from adhd_hub import connect as connect_mod

    ephemeral = r"C:\Users\alexp\AppData\Local\uv\cache\archive-v0\abc\Scripts\adhd-hub.exe"

    def which(name: str):
        if name in {"adhd-hub", "adhd-hub.exe"}:
            return ephemeral
        if name in {"uvx", "uvx.exe"}:
            return r"C:\uvx.exe"
        return None

    monkeypatch.setattr(connect_mod.shutil, "which", which)
    monkeypatch.setattr(
        connect_mod,
        "resolve_uv_package_from",
        lambda hub: "http://127.0.0.1:8787/install/wheels/demo.whl",
    )
    assert connect_mod.cli_on_path() is False
    cmd = connect_mod.format_hub_cli_command("http://127.0.0.1:8787", "doctor")
    assert cmd.startswith("uvx --refresh --from")


def test_format_hub_cli_command_prefers_path_binary(monkeypatch) -> None:
    from adhd_hub import connect as connect_mod

    monkeypatch.setattr(
        connect_mod.shutil,
        "which",
        lambda name: r"C:\Tools\adhd-hub.exe" if name in {"adhd-hub", "adhd-hub.exe"} else None,
    )
    cmd = connect_mod.format_hub_cli_command("http://127.0.0.1:8787", "doctor", "--hub", "http://x")
    assert cmd.startswith("adhd-hub doctor")
    assert "uvx" not in cmd


def test_render_install_sh_offers_uv_bootstrap() -> None:
    script = render_install_sh("http://example:8787")
    assert "ADHD_HUB_INSTALL_UV" in script
    assert "astral.sh/uv/install.sh" in script
    assert "Install uv now using the official Astral installer" in script
    assert "/dev/tty" in script


def test_render_install_ps1_offers_uv_bootstrap() -> None:
    script = render_install_ps1("http://example:8787")
    assert "ADHD_HUB_INSTALL_UV" in script
    assert "astral.sh/uv/install.ps1" in script
    assert "Install uv now using the official Astral installer" in script


def test_render_install_sh_uses_hub_wheel_with_git_fallback() -> None:
    script = render_install_sh("http://example:8787")
    assert "install/cli-wheel.url" in script
    assert "git+https://github.com/uniskela/adhd-hub.git" in script
    assert "uvx --refresh --from" in script
    assert "uvx --from adhd-hub " not in script
    assert "uv tool install" in script
    assert 'uv tool install --force "$PKG_FROM"' in script
    assert "Executable already exists" not in script  # we use --force instead
    assert "Updating existing adhd-hub CLI from this Hub" in script
    assert "ADHD_HUB_FROM_INSTALL_SCRIPT" in script
    # Durable CLI (after refresh) is preferred over ephemeral uvx.
    refresh_at = script.index("_adhd_refresh_existing_cli\n")
    hub_at = script.index('if command -v adhd-hub >/dev/null 2>&1; then\n  _adhd_run_child adhd-hub "$@"')
    uvx_at = script.index('if command -v uvx >/dev/null 2>&1; then\n  _adhd_run_child uvx --refresh --from "$PKG_FROM" adhd-hub "$@"')
    assert refresh_at < hub_at < uvx_at


def test_render_install_ps1_uses_force_for_cli_install() -> None:
    script = render_install_ps1("http://example:8787")
    assert "uv tool install --force" in script
    assert "ADHD_HUB_INSTALL_CLI" in script
    assert "ADHD_HUB_CLI_INSTALL_PROMPTED" in script
    assert "Updating existing adhd-hub CLI from this Hub" in script
    assert "ADHD_HUB_FROM_INSTALL_SCRIPT" in script
    assert "Update-AdhdExistingCli" in script
    refresh_at = script.index("Update-AdhdExistingCli\n")
    hub_at = script.index("if (Get-Command adhd-hub -ErrorAction SilentlyContinue) {\n  & adhd-hub @connectArgs")
    uvx_at = script.index("if (Get-Command uvx -ErrorAction SilentlyContinue) {\n  & uvx --refresh --from $pkgFrom adhd-hub @connectArgs")
    assert refresh_at < hub_at < uvx_at


def test_permanent_cli_install_hint_uses_force(monkeypatch) -> None:
    from adhd_hub import connect as connect_mod

    monkeypatch.setattr(
        connect_mod.shutil,
        "which",
        lambda name: "/usr/bin/uv" if name in {"uv", "uv.exe"} else None,
    )
    monkeypatch.setattr(connect_mod, "resolve_uv_package_from", lambda _url: "http://hub/wheel.whl")
    hint = connect_mod.permanent_cli_install_hint("http://hub:8787")
    assert hint == 'uv tool install --force "http://hub/wheel.whl"'


def test_install_wheel_endpoint(tmp_path: Path, monkeypatch) -> None:
    wheel_dir = tmp_path / "dist"
    wheel_dir.mkdir()
    wheel = wheel_dir / "adhd_hub-0.3.11-py3-none-any.whl"
    wheel.write_bytes(b"PK\x03\x04fake-wheel")
    monkeypatch.setenv("ADHD_HUB_WHEEL_DIR", str(wheel_dir))
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="super-secret-token-value",
        host="127.0.0.1",
        public_url="http://hub.test:8787",
    )
    client = TestClient(create_app(settings))
    meta = client.get("/install/cli-wheel.url")
    assert meta.status_code == 200
    assert meta.text.strip() == (
        "http://hub.test:8787/install/wheels/adhd_hub-0.3.11-py3-none-any.whl"
    )
    alias = client.get("/install/adhd-hub.whl", follow_redirects=False)
    assert alias.status_code == 302
    assert alias.headers["location"].endswith(
        "/install/wheels/adhd_hub-0.3.11-py3-none-any.whl"
    )
    resp = client.get("/install/wheels/adhd_hub-0.3.11-py3-none-any.whl")
    assert resp.status_code == 200
    assert resp.content.startswith(b"PK")
    head = client.head("/install/wheels/adhd_hub-0.3.11-py3-none-any.whl")
    assert head.status_code == 200
    assert client.get("/").json()["install_wheel_url"] == "/install/cli-wheel.url"


def test_install_wheel_endpoint_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADHD_HUB_WHEEL_DIR", str(tmp_path / "empty-dist"))
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="token",
        host="127.0.0.1",
    )
    client = TestClient(create_app(settings))
    resp = client.get("/install/adhd-hub.whl")
    assert resp.status_code == 404


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
