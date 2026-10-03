"""Tests for optional coding-companion recommend / install recipes."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from adhd_hub.companions import (
    graphify_register_commands,
    i_have_adhd_commands,
    install_companions,
    recommend_companions,
    resolve_companion_agents,
    rtk_init_commands,
)


def test_resolve_star_expands_multi_agent_not_cursor_only() -> None:
    all_star, agents = resolve_companion_agents(["*"])
    assert all_star is True
    assert agents == ["cursor", "codex", "claude", "gemini"]
    assert agents != ["cursor"]


def test_resolve_codex_claude_excludes_cursor() -> None:
    all_star, agents = resolve_companion_agents(["codex", "claude"])
    assert all_star is False
    assert agents == ["codex", "claude"]
    assert "cursor" not in agents


def test_resolve_empty_is_manual() -> None:
    all_star, agents = resolve_companion_agents([])
    assert all_star is False
    assert agents == []


def test_i_have_adhd_commands_multi_agent_maps_claude() -> None:
    cmds = i_have_adhd_commands(["codex", "claude"], all_star=False)
    assert len(cmds) == 1
    assert "ayghri/i-have-adhd" in cmds[0]
    assert "-a codex" in cmds[0]
    assert "-a claude-code" in cmds[0]
    assert "-a cursor" not in cmds[0]


def test_i_have_adhd_star_uses_agent_star() -> None:
    cmds = i_have_adhd_commands(["cursor", "codex", "claude", "gemini"], all_star=True)
    assert cmds == ["npx skills add ayghri/i-have-adhd -g -y --agent '*'"]


def test_graphify_register_codex_claude_not_cursor_only() -> None:
    cmds = graphify_register_commands(["codex", "claude"], all_star=False)
    assert "graphify install --platform codex" in cmds
    assert "graphify install" in cmds
    assert "graphify cursor install" not in cmds


def test_graphify_register_star_includes_all_platforms() -> None:
    agents = ["cursor", "codex", "claude", "gemini"]
    cmds = graphify_register_commands(agents, all_star=True)
    assert "graphify cursor install" in cmds
    assert "graphify install --platform codex" in cmds
    assert "graphify install" in cmds
    assert "graphify install --platform gemini" in cmds
    assert "graphify agents install" in cmds


def test_rtk_init_codex_claude_not_cursor_only() -> None:
    cmds = rtk_init_commands(["codex", "claude"], all_star=False)
    assert cmds == ["rtk init -g --codex", "rtk init -g"]
    assert not any("cursor" in c for c in cmds)


def test_rtk_init_cursor_explicit() -> None:
    cmds = rtk_init_commands(["cursor"], all_star=False)
    assert cmds == ["rtk init -g --agent cursor"]


def test_recommend_includes_opt_in_companions() -> None:
    from adhd_hub.companions import recommend_companions

    steps = recommend_companions(["cursor"])
    assert not any(s.name == "companion workflow pack" for s in steps)
    note = next(s for s in steps if s.name == "companions note")
    assert note.status == "ok"
    assert "coding-companions" in note.detail
    names = {s.name for s in steps}
    assert "companion superpowers" in names
    assert "companion context7" in names
    assert "companion agent-browser" in names
    assert "companion serena" in names


def test_recommend_empty_agents_is_manual_not_cursor() -> None:
    with (
        patch("adhd_hub.companions.detect_i_have_adhd", return_value=None),
        patch("adhd_hub.companions.detect_graphify", return_value=False),
        patch("adhd_hub.companions.detect_rtk", return_value=False),
        patch("adhd_hub.companions.detect_superpowers", return_value=False),
        patch("adhd_hub.companions.detect_context7_mcp", return_value=False),
        patch("adhd_hub.companions.detect_agent_browser", return_value=False),
        patch("adhd_hub.companions.detect_agent_browser_skill", return_value=False),
        patch("adhd_hub.companions.detect_serena", return_value=False),
        patch("adhd_hub.companions.detect_serena_mcp", return_value=False),
    ):
        steps = recommend_companions([])
    names = {s.name: s for s in steps}
    assert names["companion i-have-adhd"].status == "manual"
    assert names["companion graphify"].status == "manual"
    assert names["companion rtk"].status == "manual"
    assert names["companion superpowers"].status == "manual"
    assert names["companion context7"].status == "manual"
    assert names["companion agent-browser"].status == "manual"
    assert names["companion serena"].status == "manual"
    for step in steps:
        if step.name.startswith("companion "):
            assert "graphify cursor install" not in step.detail or "per agent" in step.detail


def test_recommend_codex_claude_recipes_exclude_cursor() -> None:
    with (
        patch("adhd_hub.companions.detect_i_have_adhd", return_value=False),
        patch("adhd_hub.companions.detect_graphify", return_value=False),
        patch("adhd_hub.companions.detect_rtk", return_value=False),
        patch("adhd_hub.companions.detect_superpowers", return_value=False),
        patch("adhd_hub.companions.detect_context7_mcp", return_value=False),
        patch("adhd_hub.companions.detect_agent_browser", return_value=False),
        patch("adhd_hub.companions.detect_agent_browser_skill", return_value=False),
        patch("adhd_hub.companions.detect_serena", return_value=False),
        patch("adhd_hub.companions.detect_serena_mcp", return_value=False),
    ):
        steps = recommend_companions(["codex", "claude"])
    details = " | ".join(s.detail for s in steps)
    assert "graphify install --platform codex" in details
    assert "rtk init -g --codex" in details
    assert "graphify cursor install" not in details
    assert "rtk init -g --agent cursor" not in details
    assert "-a cursor" not in details


def test_install_refuses_without_agents() -> None:
    steps = install_companions(
        [],
        with_i_have_adhd=True,
        dry_run=True,
    )
    assert len(steps) == 2
    assert steps[0].name == "companions install"
    assert steps[0].status == "warn"
    assert "No --agents" in steps[0].detail
    assert steps[1].name == "install i-have-adhd"
    assert steps[1].status == "warn"
    assert "pass --agents" in steps[1].detail


def test_install_dry_run_i_have_adhd_for_codex_claude() -> None:
    steps = install_companions(
        ["codex", "claude"],
        with_i_have_adhd=True,
        dry_run=True,
    )
    assert len(steps) == 1
    assert steps[0].status == "ok"
    assert "would run:" in steps[0].detail
    assert "-a codex" in steps[0].detail
    assert "-a claude-code" in steps[0].detail
    assert "-a cursor" not in steps[0].detail


def test_install_dry_run_graphify_multi_agent() -> None:
    with (
        patch("adhd_hub.companions.detect_graphify", return_value=True),
        patch("adhd_hub.companions.resolve_graphify_bin", return_value="graphify"),
    ):
        steps = install_companions(
            ["codex", "gemini"],
            with_graphify=True,
            dry_run=True,
        )
    details = " | ".join(s.detail for s in steps)
    assert "install --platform codex" in details
    assert "install --platform gemini" in details
    assert "cursor install" not in details


def test_unknown_agent_does_not_guess_hooks() -> None:
    cmds_g = graphify_register_commands(["windsurf"], all_star=False)
    cmds_r = rtk_init_commands(["windsurf"], all_star=False)
    assert cmds_g == []
    assert cmds_r == []
    with (
        patch("adhd_hub.companions.detect_i_have_adhd", return_value=False),
        patch("adhd_hub.companions.detect_graphify", return_value=False),
        patch("adhd_hub.companions.detect_rtk", return_value=False),
        patch("adhd_hub.companions.detect_superpowers", return_value=False),
        patch("adhd_hub.companions.detect_context7_mcp", return_value=False),
        patch("adhd_hub.companions.detect_agent_browser", return_value=False),
        patch("adhd_hub.companions.detect_agent_browser_skill", return_value=False),
        patch("adhd_hub.companions.detect_serena", return_value=False),
        patch("adhd_hub.companions.detect_serena_mcp", return_value=False),
    ):
        steps = recommend_companions(["windsurf"])
    details = " | ".join(s.detail for s in steps)
    assert "No auto recipe for agent(s): windsurf" in details
    assert "graphify install --platform windsurf" not in details
    assert "rtk init -g --agent windsurf" not in details


def test_append_skips_missing_when_installing(monkeypatch) -> None:
    from adhd_hub.companions import append_companion_steps

    recorded: list[tuple[str, str, str]] = []

    def add(name: str, status: str, detail: str) -> None:
        recorded.append((name, status, detail))

    with (
        patch("adhd_hub.companions.detect_i_have_adhd", return_value=False),
        patch("adhd_hub.companions.detect_graphify", return_value=False),
        patch("adhd_hub.companions.detect_rtk", return_value=False),
        patch("adhd_hub.companions.detect_superpowers", return_value=False),
        patch("adhd_hub.companions.detect_context7_mcp", return_value=False),
        patch("adhd_hub.companions.detect_agent_browser", return_value=False),
        patch("adhd_hub.companions.detect_agent_browser_skill", return_value=False),
        patch("adhd_hub.companions.detect_serena", return_value=False),
        patch("adhd_hub.companions.detect_serena_mcp", return_value=False),
    ):
        append_companion_steps(
            add,
            ["codex"],
            with_i_have_adhd=True,
            dry_run=True,
        )
    iha = [r for r in recorded if r[0] == "companion i-have-adhd"]
    assert iha and iha[0][1] == "skipped"
    assert any(r[0] == "install i-have-adhd" for r in recorded)


def test_resolve_graphify_bin_uses_local_bin(tmp_path: Path, monkeypatch) -> None:
    from adhd_hub.companions import resolve_graphify_bin

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with (
        patch("adhd_hub.companions._which", return_value=None),
        patch("adhd_hub.companions._uv_tool_bin_dir", return_value=None),
    ):
        assert resolve_graphify_bin() is None
        shim = tmp_path / ".local" / "bin" / ("graphify.exe" if sys.platform == "win32" else "graphify")
        shim.parent.mkdir(parents=True)
        shim.write_text("", encoding="utf-8")
        assert resolve_graphify_bin() == str(shim.resolve())


def test_optional_iha_failure_is_warn_not_error(monkeypatch) -> None:
    from adhd_hub import companions

    monkeypatch.setattr(
        companions,
        "_run",
        lambda *_a, **_k: ("error", "npx failed (exit 1)"),
    )
    steps = companions.install_companions(
        ["cursor"],
        with_i_have_adhd=True,
        dry_run=False,
    )
    assert steps
    assert all(s.status != "error" for s in steps)
    assert any(s.status == "warn" and "i-have-adhd" in s.name for s in steps)


def test_missing_rtk_is_warn_not_error() -> None:
    from adhd_hub.companions import CompanionStep

    with (
        patch("adhd_hub.companions.detect_rtk", return_value=False),
        patch(
            "adhd_hub.companions._try_install_rtk_binary",
            return_value=CompanionStep("install rtk binary", "warn", "rtk not on PATH"),
        ),
        patch("adhd_hub.companions.resolve_rtk_bin", return_value=None),
    ):
        steps = install_companions(["cursor", "codex"], with_rtk=True, dry_run=False)
    assert steps
    assert steps[0].name == "install rtk binary"
    assert steps[0].status == "warn"
    assert not any(s.status == "error" for s in steps)


def test_run_rtk_install_sh_downloads_before_exec(monkeypatch, tmp_path: Path) -> None:
    """Curl must finish successfully before sh runs the saved script."""
    from adhd_hub import companions

    calls: list[list[str]] = []
    script_body = "#!/bin/sh\necho ok\n"

    class Result:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def fake_run(cmd, *, check=False, timeout=None):  # noqa: ARG001
        calls.append(list(cmd))
        if cmd[0].endswith("curl") or Path(cmd[0]).name == "curl":
            out = Path(cmd[cmd.index("-o") + 1])
            out.write_text(script_body, encoding="utf-8")
            return Result(0)
        assert Path(cmd[1]).is_file()
        assert Path(cmd[1]).read_text(encoding="utf-8") == script_body
        return Result(0)

    class _Tmp:
        def __enter__(self):
            return str(tmp_path)

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        companions,
        "_which",
        lambda *names: (
            "/usr/bin/curl"
            if "curl" in names
            else ("/bin/sh" if "sh" in names else None)
        ),
    )
    monkeypatch.setattr(companions.subprocess, "run", fake_run)
    monkeypatch.setattr(companions.tempfile, "TemporaryDirectory", lambda *a, **k: _Tmp())

    status, detail = companions._run_rtk_install_sh(dry_run=False)
    assert status == "ok"
    assert "exit 0" in detail
    assert len(calls) == 2
    assert any("--max-time" in c for c in calls)
    assert calls[0][0] == "/usr/bin/curl"
    assert calls[1][0] == "/bin/sh"
    assert calls[1][1].endswith("install.sh")


def test_run_rtk_install_sh_skips_sh_when_curl_fails(monkeypatch, tmp_path: Path) -> None:
    from adhd_hub import companions

    calls: list[list[str]] = []

    class Result:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def fake_run(cmd, *, check=False, timeout=None):  # noqa: ARG001
        calls.append(list(cmd))
        return Result(22)

    class _Tmp:
        def __enter__(self):
            return str(tmp_path)

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        companions,
        "_which",
        lambda *names: (
            "/usr/bin/curl"
            if "curl" in names
            else ("/bin/sh" if "sh" in names else None)
        ),
    )
    monkeypatch.setattr(companions.subprocess, "run", fake_run)
    monkeypatch.setattr(companions.tempfile, "TemporaryDirectory", lambda *a, **k: _Tmp())

    status, detail = companions._run_rtk_install_sh(dry_run=False)
    assert status == "error"
    assert "curl exit 22" in detail
    assert len(calls) == 1
    assert calls[0][0] == "/usr/bin/curl"


def test_run_rtk_install_sh_timeout_is_error(monkeypatch, tmp_path: Path) -> None:
    from adhd_hub import companions

    class _Tmp:
        def __enter__(self):
            return str(tmp_path)

        def __exit__(self, *exc):
            return False

    def fake_run(*_a, **_k):
        raise companions.subprocess.TimeoutExpired(cmd="curl", timeout=150)

    monkeypatch.setattr(
        companions,
        "_which",
        lambda *names: (
            "/usr/bin/curl"
            if "curl" in names
            else ("/bin/sh" if "sh" in names else None)
        ),
    )
    monkeypatch.setattr(companions.subprocess, "run", fake_run)
    monkeypatch.setattr(companions.tempfile, "TemporaryDirectory", lambda *a, **k: _Tmp())

    status, detail = companions._run_rtk_install_sh(dry_run=False)
    assert status == "error"
    assert "timed out" in detail.lower() or "TimeoutExpired" in detail


def test_rtk_install_uses_install_sh_without_brew(monkeypatch) -> None:
    from adhd_hub import companions

    monkeypatch.setattr(
        companions,
        "_which",
        lambda *names: "/usr/bin/curl" if "curl" in names else None,
    )
    monkeypatch.setattr(
        companions,
        "_run_rtk_install_sh",
        lambda *, dry_run: (
            "ok",
            f"curl -fsSL {companions.RTK_INSTALL_SH_URL} | sh (exit 0)",
        ),
    )
    step = companions._try_install_rtk_binary(dry_run=False)
    assert step.status == "ok"
    assert "install.sh" in step.detail

    # Full connect path: after install.sh, binary is resolvable → init runs.
    seen = {"install": False}

    def detect() -> bool:
        return seen["install"]

    def try_install(*, dry_run: bool):
        seen["install"] = True
        return companions.CompanionStep(
            "install rtk binary",
            "ok",
            f"curl -fsSL {companions.RTK_INSTALL_SH_URL} | sh (exit 0)",
        )

    monkeypatch.setattr(companions, "detect_rtk", detect)
    monkeypatch.setattr(companions, "_try_install_rtk_binary", try_install)
    monkeypatch.setattr(companions, "resolve_rtk_bin", lambda: "/home/x/.local/bin/rtk")
    monkeypatch.setattr(
        companions,
        "_run",
        lambda cmd, *, dry_run: ("ok", " ".join(cmd) + " (exit 0)"),
    )
    steps = companions.install_companions(["cursor"], with_rtk=True, dry_run=False)
    assert any(s.name == "install rtk binary" and s.status == "ok" for s in steps)
    assert any(s.name == "install rtk init" and s.status == "ok" for s in steps)


def test_rtk_install_dry_run_prefers_install_sh_without_brew(monkeypatch) -> None:
    from adhd_hub import companions

    monkeypatch.setattr(companions, "detect_rtk", lambda: False)
    monkeypatch.setattr(
        companions,
        "_which",
        lambda *names: "/usr/bin/curl" if "curl" in names else (
            "/bin/sh" if "sh" in names else None
        ),
    )
    step = companions._try_install_rtk_binary(dry_run=True)
    assert step.status == "ok"
    assert "install.sh" in step.detail
    assert "would run:" in step.detail


def test_rtk_install_prefers_brew_when_present(monkeypatch) -> None:
    from adhd_hub import companions

    monkeypatch.setattr(
        companions,
        "_which",
        lambda *names: "/opt/homebrew/bin/brew" if "brew" in names else None,
    )
    monkeypatch.setattr(
        companions,
        "_run",
        lambda cmd, *, dry_run: ("ok", f"would run: {' '.join(cmd)}"),
    )
    step = companions._try_install_rtk_binary(dry_run=True)
    assert step.status == "ok"
    assert "brew install rtk" in step.detail


def test_with_rtk_without_agents_still_installs_binary(monkeypatch) -> None:
    """Regression: no --agents used to refuse before any RTK binary install."""
    from adhd_hub import companions

    installed = {"ok": False}

    def detect() -> bool:
        return installed["ok"]

    def try_install(*, dry_run: bool):
        installed["ok"] = True
        return companions.CompanionStep(
            "install rtk binary",
            "ok",
            f"curl -fsSL {companions.RTK_INSTALL_SH_URL} | sh (exit 0)",
        )

    monkeypatch.setattr(companions, "detect_rtk", detect)
    monkeypatch.setattr(companions, "resolve_rtk_bin", lambda: "/home/x/.local/bin/rtk")
    monkeypatch.setattr(companions, "_try_install_rtk_binary", try_install)
    steps = companions.install_companions([], with_rtk=True, dry_run=False)
    assert any(s.name == "companions install" and s.status == "warn" for s in steps)
    assert any(s.name == "install rtk binary" and s.status == "ok" for s in steps)
    assert any(
        s.name == "install rtk init" and "pass --agents" in s.detail for s in steps
    )
    assert not any(s.status == "error" for s in steps)


def test_run_prints_arrow_running(monkeypatch, capsys) -> None:
    from adhd_hub import companions

    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(companions, "_which", lambda *a, **k: "echo")
    monkeypatch.setattr(companions.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())
    status, _detail = companions._run(["echo", "hi"], dry_run=False)
    err = capsys.readouterr().err
    assert status == "ok"
    assert "→ Running  echo hi" in err
    assert "Running: echo hi" not in err


def test_graphify_register_uses_resolved_bin(tmp_path: Path) -> None:
    shim = tmp_path / "graphify.exe" if sys.platform == "win32" else tmp_path / "graphify"
    # Use a cross-platform name for the mock path string
    shim = tmp_path / "graphify"
    shim.write_text("", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, dry_run: bool):
        calls.append(cmd)
        return "ok", "would run"

    with (
        patch("adhd_hub.companions.detect_graphify", return_value=True),
        patch("adhd_hub.companions.resolve_graphify_bin", return_value=str(shim)),
        patch("adhd_hub.companions._run", side_effect=fake_run),
    ):
        steps = install_companions(["codex"], with_graphify=True, dry_run=True)
    assert any(s.name == "install graphify register" for s in steps)
    assert calls
    assert calls[-1][0] == str(shim)
    assert "codex" in calls[-1]

def test_install_dry_run_context7_and_superpowers() -> None:
    steps = install_companions(
        ["cursor"],
        with_context7=True,
        with_superpowers=True,
        dry_run=True,
    )
    names = [s.name for s in steps]
    assert any(n.startswith("install context7") for n in names)
    assert any(n.startswith("install superpowers") for n in names)
    assert all(s.status in {"ok", "warn", "skipped"} for s in steps)


def test_install_dry_run_agent_browser_and_serena() -> None:
    with (
        patch("adhd_hub.companions.detect_agent_browser", return_value=False),
        patch("adhd_hub.companions.detect_serena", return_value=False),
        patch("adhd_hub.companions.resolve_agent_browser_bin", return_value=None),
        patch("adhd_hub.companions.resolve_serena_bin", return_value=None),
    ):
        steps = install_companions(
            ["cursor", "codex"],
            with_agent_browser=True,
            with_serena=True,
            dry_run=True,
        )
    details = " | ".join(s.detail for s in steps)
    assert "agent-browser" in details
    assert "serena-agent" in details or "serena" in details
    assert all(s.status != "error" for s in steps)

def test_merge_stdio_preserves_existing_context7(tmp_path: Path) -> None:
    from adhd_hub.companions import merge_stdio_mcp_json

    path = tmp_path / "mcp.json"
    path.write_text(
        '{"mcpServers":{"context7":{"command":"npx","args":["-y","@upstash/context7-mcp"],"env":{"CONTEXT7_API_KEY":"x"}}}}\n',
        encoding="utf-8",
    )
    action = merge_stdio_mcp_json(
        path,
        "context7",
        {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
        dry_run=False,
    )
    assert action == "unchanged"
    raw = path.read_text(encoding="utf-8")
    assert "CONTEXT7_API_KEY" in raw


def test_merge_codex_stdio_escapes_windows_path(tmp_path: Path) -> None:
    from adhd_hub.companions import merge_codex_stdio_mcp

    path = tmp_path / "config.toml"
    action = merge_codex_stdio_mcp(
        path,
        "serena",
        r"C:\Users\me\serena.exe",
        ["start-mcp-server"],
        dry_run=False,
    )
    assert action == "created"
    text = path.read_text(encoding="utf-8")
    assert 'command = "C:\\\\Users\\\\me\\\\serena.exe"' in text


def test_context7_codex_only_skips_false_warn() -> None:
    steps = install_companions(["codex"], with_context7=True, dry_run=True)
    details = " | ".join(s.detail for s in steps)
    assert "no Cursor/Claude" not in details
    assert any(s.name == "install context7" and "codex" in s.detail for s in steps)
