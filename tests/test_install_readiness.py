from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from adhd_hub import companions, project_setup
from adhd_hub.connect import ConnectReport, print_report, render_install_sh
from adhd_hub.project_setup import install_skills


def executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def shell_install(tmp_path: Path, monkeypatch):
    uv = shutil.which("uv")
    if not uv:
        pytest.skip("real uv is required for shell profile integration")
    # GitHub runners can export PowerShell indicators. uv prioritizes these
    # over SHELL, so a Bash-profile test must not inherit the host environment.
    monkeypatch.setenv("PSModulePath", str(tmp_path / "powershell modules"))
    home = tmp_path / "home with ' quote"
    tools = home / ".local" / "bin"
    bin_dir = tmp_path / "bin"
    executable(bin_dir / "curl", "printf 'https://example/adhd-hub.whl\\n'\n")
    executable(tools / "adhd-hub", "printf 'CONNECTED\\n'\n")
    executable(
        tools / "uv",
        'case "$*" in\n'
        '  "tool install "*) exit 0 ;;\n'
        '  *) exec "$REAL_UV" "$@" ;;\n'
        'esac\n',
    )
    (home / ".bashrc").write_text("# Existing user settings\n", encoding="utf-8")
    env = {
        "HOME": str(home),
        "SHELL": "/bin/bash",
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "REAL_UV": uv,
        "UV_TOOL_BIN_DIR": str(tools),
        "UV_NO_CONFIG": "1",
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "ADHD_HUB_CONNECT_NO_SKILLS": "1",
        "ADHD_HUB_INSTALL_UV": "1",
    }
    return home, tools, env


def run_installer(env: dict[str, str], *args: str):
    return subprocess.run(
        ["sh", "-s", "--", ".", *args],
        input=render_install_sh("https://hub.example"),
        text=True,
        capture_output=True,
        env=env,
        start_new_session=True,
        timeout=15,
        check=False,
    )


def test_installer_repairs_future_shell_path_idempotently(shell_install):
    home, tools, env = shell_install
    first = run_installer(env)
    assert first.returncode == 0, first.stderr
    assert "CONNECTED" in first.stdout
    assert "current shell" in first.stdout.lower()
    profile = (home / ".bashrc").read_text(encoding="utf-8")
    assert profile.startswith("# Existing user settings\n")
    fresh = subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", '. "$HOME/.bashrc"; command -v adhd-hub'],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert fresh.returncode == 0, fresh.stderr
    assert fresh.stdout.strip() == str(tools / "adhd-hub")
    second = run_installer(env)
    assert second.returncode == 0, second.stderr
    assert (home / ".bashrc").read_text(encoding="utf-8") == profile


def test_installer_dry_run_does_not_change_shell_profile(shell_install):
    home, _, env = shell_install
    original = (home / ".bashrc").read_bytes()
    result = run_installer(env, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert (home / ".bashrc").read_bytes() == original


def test_installer_flags_dry_run_does_not_change_shell_profile(shell_install):
    home, _, env = shell_install
    env["ADHD_HUB_CONNECT_FLAGS"] = "--agents cursor --dry-run"
    original = (home / ".bashrc").read_bytes()
    result = run_installer(env)
    assert result.returncode == 0, result.stderr
    assert (home / ".bashrc").read_bytes() == original


@pytest.mark.parametrize("custom_on_path", [False, True])
def test_installer_repairs_uv_and_custom_tool_paths(shell_install, custom_on_path: bool):
    home, tools, env = shell_install
    custom = home / "custom tools"
    custom.mkdir()
    shutil.move(tools / "adhd-hub", custom / "adhd-hub")
    env["UV_TOOL_BIN_DIR"] = str(custom)
    if custom_on_path:
        env["PATH"] = f"{custom}:{env['PATH']}"
    result = run_installer(env)
    assert result.returncode == 0, result.stderr
    assert "current shell" in result.stdout.lower()
    fresh = subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", '. "$HOME/.bashrc"; command -v uv; command -v adhd-hub'],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert fresh.returncode == 0, fresh.stderr
    assert fresh.stdout.splitlines() == [str(tools / "uv"), str(custom / "adhd-hub")]


@pytest.mark.parametrize("partial", [False, True])
def test_skills_install_is_noninteractive_and_detects_partial_failure(
    tmp_path: Path, monkeypatch, partial: bool,
):
    executable(
        tmp_path / "npx",
        '[ "$1" = "--yes" ] || exit 19\n'
        + ("printf '\\033[31mFailed to install 2\\033[0m\\n'\n" if partial else "exit 0\n"),
    )
    monkeypatch.setenv("PATH", str(tmp_path))
    assert install_skills("./skills", agents=["cursor"]) == (3 if partial else 0)


def test_partial_companion_skill_install_is_a_warning(tmp_path: Path, monkeypatch):
    executable(tmp_path / "npx", "printf 'Failed to install 2\\n'\n")
    monkeypatch.setenv("PATH", str(tmp_path))
    steps = companions._install_skills_sh_source(
        "example/skills", "install skill", ["cursor"],
        all_star=True, has_agents=True, dry_run=False,
    )
    assert steps[0].status == "warn"
    assert "partial" in steps[0].detail.lower()


@pytest.mark.parametrize("output", [b"Download started\n\xff", "Download started\n", None])
def test_skills_timeout_preserves_output_and_warns_for_optional_install(
    monkeypatch, capsys, output,
):
    def stalled_install(command, **kwargs):
        assert kwargs["timeout"] == 300
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=output)

    monkeypatch.setattr(project_setup.subprocess, "run", stalled_install)
    monkeypatch.setattr(companions.shutil, "which", lambda name: "npx")
    steps = companions._install_skills_sh_source(
        "example/skills", "install skill", ["cursor"],
        all_star=True, has_agents=True, dry_run=False,
    )
    assert steps[0].status == "warn"
    assert "124" in steps[0].detail
    printed = capsys.readouterr().out
    assert "timed out" in printed.lower()
    if output:
        assert "Download started" in printed


def test_skills_install_stops_a_real_stalled_process(monkeypatch, capsys):
    monkeypatch.setattr(project_setup, "SKILLS_INSTALL_TIMEOUT", 1)
    result = project_setup.run_skills_command([
        sys.executable, "-c",
        "import time; print('Download started', flush=True); time.sleep(10)",
    ])
    assert result == 124
    printed = capsys.readouterr().out
    assert "Download started" in printed
    assert "timed out" in printed.lower()


@pytest.mark.parametrize("launch_code", [0, 1])
def test_browser_readiness_checks_launch_and_closes_its_session(
    tmp_path: Path, monkeypatch, launch_code: int,
):
    log = tmp_path / "browser.log"
    monkeypatch.setenv("BROWSER_LOG", str(log))
    browser = executable(
        tmp_path / "agent-browser",
        'printf "%s\\n" "$*" >>"$BROWSER_LOG"\n'
        'case "$*" in\n'
        f'  *"open about:blank"*) exit {launch_code} ;;\n'
        'esac\n',
    )
    monkeypatch.setattr(companions, "detect_agent_browser", lambda: True)
    monkeypatch.setattr(companions, "resolve_agent_browser_bin", lambda: str(browser))
    steps = companions.install_companions([], with_agent_browser=True)
    readiness = next(s for s in steps if s.name == "install agent-browser launch")
    assert readiness.status == ("ok" if launch_code == 0 else "warn")
    calls = log.read_text(encoding="utf-8").splitlines()
    launch = next(call for call in calls if "open about:blank" in call)
    assert launch.startswith("--session adhd-hub-install-")
    assert launch.removesuffix("open about:blank") + "close" in calls


def test_browser_probe_ignores_existing_browser_connection_settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENT_BROWSER_CDP", "ws://127.0.0.1:9222")
    monkeypatch.setenv("AGENT_BROWSER_AUTO_CONNECT", "1")
    monkeypatch.setenv("AGENT_BROWSER_CONFIG", str(tmp_path / "shared-browser.json"))
    browser = executable(
        tmp_path / "agent-browser",
        '[ -z "${AGENT_BROWSER_CDP+x}" ] || exit 17\n'
        '[ -z "${AGENT_BROWSER_AUTO_CONNECT+x}" ] || exit 17\n'
        '[ -z "${AGENT_BROWSER_CONFIG+x}" ] || exit 17\n'
        '[ "$3" = "--config" ] || exit 18\n'
        '[ "$(cat "$4")" = "{}" ] || exit 18\n',
    )
    step = companions._verify_agent_browser(str(browser), dry_run=False)
    assert step.status == "ok", step.detail


def test_browser_probe_temp_configuration_failure_is_a_warning(monkeypatch):
    def unavailable_temp_directory(*args, **kwargs):
        raise OSError("temporary storage unavailable")

    monkeypatch.setattr(companions.tempfile, "TemporaryDirectory", unavailable_temp_directory)
    step = companions._verify_agent_browser("agent-browser", dry_run=False)
    assert step.status == "warn"


def test_browser_probe_timeout_still_closes_its_session(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[-2:] == ["open", "about:blank"]:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(companions.subprocess, "run", run)
    step = companions._verify_agent_browser("agent-browser", dry_run=False)
    assert step.status == "warn"
    assert len(calls) == 2
    assert calls[1] == [*calls[0][:-2], "close"]


@pytest.mark.parametrize("close_failure", ["exit", "timeout", "oserror"])
@pytest.mark.parametrize("launch_code", [0, 1])
def test_browser_probe_reports_cleanup_failure(monkeypatch, close_failure, launch_code):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[-1] == "close":
            if close_failure == "timeout":
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            if close_failure == "oserror":
                raise OSError("close failed")
            return subprocess.CompletedProcess(command, returncode=1)
        return subprocess.CompletedProcess(command, returncode=launch_code)

    monkeypatch.setattr(companions.subprocess, "run", run)
    step = companions._verify_agent_browser("agent-browser", dry_run=False)
    assert step.status == "warn"
    assert "cleanup" in step.detail.lower()
    assert f"agent-browser --session {calls[0][2]} close" in step.detail
    if launch_code:
        assert "launch failed" in step.detail


def test_report_does_not_count_skipped_checks_as_success(capsys):
    report = ConnectReport(hub_url="https://hub.example")
    report.add("hub probe", "ok", "reachable")
    report.add("skills", "skipped", "not requested")
    print_report(report)
    output = capsys.readouterr().out
    assert "Hub · 1 ok" in output
    assert "Agents · 1 ok" not in output
    assert "1 skipped" in output
