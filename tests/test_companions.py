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
    assert len(steps) == 1
    assert steps[0].status == "warn"
    assert "No --agents" in steps[0].detail


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
    with patch("adhd_hub.companions._which", return_value=None):
        with patch("adhd_hub.companions._uv_tool_bin_dir", return_value=None):
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
    with (
        patch("adhd_hub.companions.detect_rtk", return_value=False),
        patch("adhd_hub.companions._try_install_rtk_binary", return_value=None),
        patch("adhd_hub.companions.resolve_rtk_bin", return_value=None),
    ):
        steps = install_companions(["cursor", "codex"], with_rtk=True, dry_run=False)
    assert steps
    assert steps[0].name == "install rtk binary"
    assert steps[0].status == "warn"
    assert not any(s.status == "error" for s in steps)


def test_run_prints_arrow_running(monkeypatch, capsys) -> None:
    from adhd_hub import companions

    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(companions, "_which", lambda *a, **k: "echo")
    monkeypatch.setattr(companions.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())
    status, detail = companions._run(["echo", "hi"], dry_run=False)
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
    assert 'command = "C:\\Users\\me\\serena.exe"' in text


def test_context7_codex_only_skips_false_warn() -> None:
    steps = install_companions(["codex"], with_context7=True, dry_run=True)
    details = " | ".join(s.detail for s in steps)
    assert "no Cursor/Claude" not in details
    assert any(s.name == "install context7" and "codex" in s.detail for s in steps)

