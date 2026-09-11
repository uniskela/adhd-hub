# Connect report UX + companions docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make connect/doctor CLI output ADHD-scannable (color + collapsed OK summary + `--verbose` full list), and document four additional coding companions without new auto-install flags.

**Architecture:** Add a tiny stdlib ANSI module (`cli_style.py`) shared by connect live lines and `print_report`. Restructure `print_report` into banner → Do next / Fix these → Needs attention → Done (counts). Expand `coding-companions.md` and add one soft manual companion checklist step. No new dependencies.

**Tech Stack:** Python 3 stdlib only (ANSI + `sys.stdout.isatty()`), existing pytest, Markdown docs.

## Global Constraints

- No `rich`, `colorama`, or other new packaging dependencies.
- Color off when not a TTY, or when `NO_COLOR` or `ADHD_HUB_NO_COLOR` is set (non-empty).
- Default report collapses OK/skipped; warn/error/missing/manual stay fully visible.
- `--verbose` / `-v` shows the full flat step list (colored marks when color on).
- Superpowers, Context7, agent-browser, Serena: docs + soft checklist only — no `--with-*`, no Settings toggles, no detection.
- Do not commit unless the operator explicitly asks (repository user rule overrides plan commit steps).
- After meaningful code edits: `graphify update .`

## File map

| File | Responsibility |
|------|----------------|
| `src/adhd_hub/cli_style.py` | Color enablement, `style()`, status mark helpers, `print_running()` |
| `src/adhd_hub/connect.py` | `print_report(report, *, verbose=False)`, step grouping, next/fix sections; use `print_running` in openclaw skills runner |
| `src/adhd_hub/companions.py` | Use `print_running`; soft checklist step for workflow pack |
| `src/adhd_hub/project_setup.py` | Use `print_running` for skills install |
| `src/adhd_hub/cli.py` | Pass `verbose=args.verbose` into `print_report` |
| `docs/coding-companions.md` | Table + sections for four new companions |
| `tests/test_cli_style.py` | Color on/off behavior |
| `tests/test_connect.py` | Report layout default vs verbose |
| `tests/test_companions.py` | Soft checklist step presence |

---

### Task 1: `cli_style` helpers (TDD)

**Files:**
- Create: `src/adhd_hub/cli_style.py`
- Create: `tests/test_cli_style.py`

**Interfaces:**
- Produces:
  - `def color_enabled(stream: TextIO | None = None) -> bool`
  - `def style(text: str, *, fg: str | None = None, bold: bool = False, dim: bool = False, stream: TextIO | None = None) -> str`
  - `def status_mark(status: str) -> str`  # returns `OK`, `--`, `!!`, or `XX`
  - `def paint_status(status: str, mark: str | None = None, *, stream: TextIO | None = None) -> str`
  - `def print_running(command: list[str], *, file: TextIO | None = None) -> None`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli_style.py
from __future__ import annotations

import io
import os

from adhd_hub import cli_style


def test_color_disabled_when_no_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("ADHD_HUB_NO_COLOR", raising=False)
    stream = io.StringIO()
    stream.isatty = lambda: True  # type: ignore[method-assign]
    assert cli_style.color_enabled(stream) is False
    assert "\x1b[" not in cli_style.style("hi", fg="green", stream=stream)


def test_color_disabled_when_not_tty(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("ADHD_HUB_NO_COLOR", raising=False)
    stream = io.StringIO()
    assert cli_style.color_enabled(stream) is False


def test_color_enabled_on_tty(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("ADHD_HUB_NO_COLOR", raising=False)
    stream = io.StringIO()
    stream.isatty = lambda: True  # type: ignore[method-assign]
    assert cli_style.color_enabled(stream) is True
    out = cli_style.style("ok", fg="green", stream=stream)
    assert out.startswith("\x1b[")
    assert out.endswith("\x1b[0m")
    assert "ok" in out


def test_status_mark_mapping() -> None:
    assert cli_style.status_mark("ok") == "OK"
    assert cli_style.status_mark("skipped") == "--"
    assert cli_style.status_mark("manual") == "--"
    assert cli_style.status_mark("warn") == "!!"
    assert cli_style.status_mark("missing") == "!!"
    assert cli_style.status_mark("error") == "XX"


def test_print_running_dim_prefix(capsys, monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("ADHD_HUB_NO_COLOR", raising=False)
    monkeypatch.setattr(cli_style.sys.stdout, "isatty", lambda: False)
    cli_style.print_running(["graphify", "cursor", "install"])
    assert "→ Running  graphify cursor install" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_style.py -v`  
Expected: FAIL (module missing / import error)

- [ ] **Step 3: Implement `cli_style.py`**

```python
# src/adhd_hub/cli_style.py
from __future__ import annotations

import os
import sys
from typing import TextIO

_FG = {
    "green": "32",
    "red": "31",
    "yellow": "33",
    "cyan": "36",
}

_STATUS_MARK = {
    "ok": "OK",
    "skipped": "--",
    "manual": "--",
    "warn": "!!",
    "missing": "!!",
    "error": "XX",
}

_STATUS_FG = {
    "ok": "green",
    "warn": "yellow",
    "missing": "yellow",
    "error": "red",
}


def color_enabled(stream: TextIO | None = None) -> bool:
    if os.environ.get("NO_COLOR", "").strip():
        return False
    if os.environ.get("ADHD_HUB_NO_COLOR", "").strip():
        return False
    target = stream if stream is not None else sys.stdout
    try:
        return bool(target.isatty())
    except Exception:
        return False


def style(
    text: str,
    *,
    fg: str | None = None,
    bold: bool = False,
    dim: bool = False,
    stream: TextIO | None = None,
) -> str:
    if not color_enabled(stream):
        return text
    parts: list[str] = []
    if bold:
        parts.append("1")
    if dim:
        parts.append("2")
    if fg and fg in _FG:
        parts.append(_FG[fg])
    if not parts:
        return text
    return f"\x1b[{';'.join(parts)}m{text}\x1b[0m"


def status_mark(status: str) -> str:
    return _STATUS_MARK.get(status, status)


def paint_status(
    status: str, mark: str | None = None, *, stream: TextIO | None = None
) -> str:
    label = mark if mark is not None else status_mark(status)
    fg = _STATUS_FG.get(status)
    if status in {"skipped", "manual"}:
        return style(label, dim=True, stream=stream)
    if fg:
        return style(label, fg=fg, bold=True, stream=stream)
    return label


def print_running(command: list[str], *, file: TextIO | None = None) -> None:
    target = file if file is not None else sys.stdout
    prefix = style("→ Running", dim=True, stream=target)
    print(f"{prefix}  {' '.join(command)}", file=target)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_style.py -v`  
Expected: PASS

- [ ] **Step 5: Commit only if operator asked** — otherwise skip.

---

### Task 2: Restructure `print_report` (default + verbose)

**Files:**
- Modify: `src/adhd_hub/connect.py` (`print_report` and helpers near end of file)
- Modify: `src/adhd_hub/cli.py` (`cmd_connect`, `cmd_doctor`, `cmd_login` call sites)
- Modify: `tests/test_connect.py`

**Interfaces:**
- Consumes: `cli_style.style`, `cli_style.paint_status`, `cli_style.status_mark`
- Produces: `def print_report(report: ConnectReport, *, verbose: bool = False) -> None`
- Produces: `def classify_step_group(name: str) -> str`  # Hub | Agents | Companions | Other

- [ ] **Step 1: Write / update failing tests**

Replace/extend `test_print_report_shows_complete_banner` and add:

```python
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
    print_report(report, verbose=False)
    out = capsys.readouterr().out
    assert "Connect finished with errors" in out
    assert "Fix these:" in out
    assert "Needs attention:" in out
    assert "[XX] install rtk binary:" in out
    assert "Done:" in out
```

Keep asserting Hub UI / Verify anytime still appear under success + `setup complete`.

- [ ] **Step 2: Run targeted tests — expect FAIL**

Run: `uv run pytest tests/test_connect.py::test_print_report_default_collapses_ok tests/test_connect.py::test_print_report_verbose_lists_all_steps tests/test_connect.py::test_print_report_fix_these_on_error tests/test_connect.py::test_print_report_shows_complete_banner -v`  
Expected: FAIL on new assertions / signature

- [ ] **Step 3: Implement grouping + `print_report`**

Add near `print_report` in `connect.py`:

```python
_ATTENTION = frozenset({"warn", "error", "missing", "manual"})
_HUB_NAMES = frozenset({"hub probe", "register", "setup complete"})
_AGENT_NAMES = frozenset({
    "cursor MCP",
    "cursor MCP (project)",
    "cursor MCP (global)",
    "cursor rule",
    "codex MCP",
    "AGENTS.md",
    "skills",
    "skills CLI",
    "openclaw skills",
})
_COMPANION_PREFIXES = ("companion ", "companions ", "install i-have-adhd", "install graphify", "install rtk")


def classify_step_group(name: str) -> str:
    if name in _HUB_NAMES or name.startswith("hub "):
        return "Hub"
    if name in _AGENT_NAMES or name.startswith("cursor ") or name.startswith("codex "):
        return "Agents"
    if any(name.startswith(p) for p in _COMPANION_PREFIXES):
        return "Companions"
    return "Other"
```

Rewrite `print_report` to:

1. Blank line + colored banner (`style(..., fg="green"|"red", bold=True)`).
2. `Hub: {url}`
3. If not `report.ok`: section **Fix these:** numbered list of attention steps (`name` — short detail).
4. Elif success: section **Do next:** existing next-step bullets (renamed header from `Next steps:` to `Do next:` per spec; keep same bullet content).
5. If attention steps exist: **Needs attention:** then for each `[{paint_status}] {name}: {detail}`.
6. If any ok/skipped: **Done:** lines like `  Hub · 3 ok` (count only ok+skipped in that group; if a group has zero ok/skipped, omit it).
7. If `verbose`: print blank line + `Summary of what ran:` + full flat list for **all** steps with painted marks (preserve `[OK] name: detail` shape for tests).
8. On failure after sections: keep the one-liner `Fix the XX/!! items above, then re-run the install/connect command.` only when not already covered — prefer putting that as the last Fix these note or keep as footer under Fix these.

Wire `cli.py`:

```python
print_report(report, verbose=args.verbose)
```

for `cmd_connect`, `cmd_doctor`, and `cmd_login` (login has access to `args.verbose` from the global parser).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_connect.py -v -k print_report`  
Expected: PASS

- [ ] **Step 5: Commit only if operator asked**

---

### Task 3: Quiet live `→ Running` lines

**Files:**
- Modify: `src/adhd_hub/connect.py` (`install_openclaw_skills` ~L382)
- Modify: `src/adhd_hub/companions.py` (`_run` ~L374)
- Modify: `src/adhd_hub/project_setup.py` (~L142)

**Interfaces:**
- Consumes: `cli_style.print_running`

- [ ] **Step 1: Write a small regression test (optional but preferred)**

```python
# in tests/test_companions.py
def test_run_prints_arrow_running(monkeypatch, capsys) -> None:
    from adhd_hub import companions

    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(companions.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())
    status, detail = companions._run(["echo", "hi"], dry_run=False)
    err = capsys.readouterr().err
    assert status == "ok"
    assert "→ Running  echo hi" in err
    assert "Running: echo hi" not in err
```

- [ ] **Step 2: Run test — expect FAIL** if still old format

- [ ] **Step 3: Replace all three print sites**

```python
from adhd_hub.cli_style import print_running

# companions._run — keep stderr:
print_running(command, file=sys.stderr)

# connect.install_openclaw_skills / project_setup — stdout default:
print_running(command)
```

- [ ] **Step 4: Run**

Run: `uv run pytest tests/test_companions.py tests/test_cli_style.py -v`  
Expected: PASS

---

### Task 4: Soft companion checklist + docs expansion

**Files:**
- Modify: `src/adhd_hub/companions.py` (`recommend_companions`)
- Modify: `docs/coding-companions.md`
- Modify: `tests/test_companions.py` (assert new step)

**Interfaces:**
- Produces step name: `companion workflow pack` with status `manual`

- [ ] **Step 1: Failing test**

```python
def test_recommend_includes_workflow_pack() -> None:
    from adhd_hub.companions import recommend_companions

    steps = recommend_companions(["cursor"])
    pack = next(s for s in steps if s.name == "companion workflow pack")
    assert pack.status == "manual"
    assert "Superpowers" in pack.detail
    assert "Context7" in pack.detail
    assert "agent-browser" in pack.detail
    assert "Serena" in pack.detail
    assert "coding-companions" in pack.detail
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement recommend step**

After the existing companions note (or at end of `recommend_companions` before return), append:

```python
steps.append(
    CompanionStep(
        "companion workflow pack",
        "manual",
        "Also consider Superpowers, Context7, agent-browser "
        "(+ Serena advanced) — see coding-companions.md",
    )
)
```

- [ ] **Step 4: Update `docs/coding-companions.md`**

1. Replace the top table with Role | Tool | Recommendation columns per spec (existing three + Hub + four new).
2. After RTK section, add four sections with this content shape (link README; do not invent long recipes):

**Superpowers** — MIT ([LICENSE](https://github.com/obra/superpowers/blob/main/LICENSE)). Agent workflow skills (brainstorm → plan → TDD → review). Privacy: local skills/plugin; see upstream for any optional telemetry (visual companion). Install: follow [obra/superpowers](https://github.com/obra/superpowers) README for Cursor/Codex/Claude. Hub does not install this.

**Context7** — MIT. Up-to-date library docs via MCP/CLI. Privacy: queries go to Context7’s service; may need an API key — see upstream. Install: [upstash/context7](https://github.com/upstash/context7). Hub does not install this.

**agent-browser** — Apache-2.0 (confirm on write from upstream LICENSE if badge differs). Browser automation for agents to verify UI. Privacy: drives a local browser; review upstream before enabling. Install: [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser). Hub does not install this.

**Serena** — MIT. Semantic code navigation / editing via MCP (advanced). Privacy: typically local LSP/MCP; confirm upstream if using remote options. Install: [oraios/serena](https://github.com/oraios/serena). Mark **Optional / advanced**. Hub does not install this.

3. Ethics section: restate recommendations only; no `--with-*` for these four.

- [ ] **Step 5: Run companion + connect tests**

Run: `uv run pytest tests/test_companions.py tests/test_connect.py -v`  
Expected: PASS

- [ ] **Step 6: `graphify update .`**

Run: `graphify update .` from repo root (or full path to `graphify.exe` under `%USERPROFILE%\.local\bin` if PATH not refreshed).

---

### Task 5: Full verification

- [ ] **Step 1: Full relevant suite**

Run: `uv run pytest tests/test_cli_style.py tests/test_connect.py tests/test_companions.py -v`  
Expected: all PASS

- [ ] **Step 2: Manual dry-run smoke (operator machine)**

```powershell
$env:NO_COLOR='1'
uv run adhd-hub doctor --hub http://127.0.0.1:8787 --project .
uv run adhd-hub -v doctor --hub http://127.0.0.1:8787 --project .
Remove-Item Env:NO_COLOR
uv run adhd-hub doctor --hub http://127.0.0.1:8787 --project .
```

Expected: default shows `Do next` / `Done` counts; `-v` shows `[OK] …` lines; with color TTY shows green/yellow/red marks.

- [ ] **Step 3: Rebuild wheel only if shipping via Hub install scripts**

```powershell
uv build --wheel -o dist
```

Restart Hub process so `/install.ps1` picks up the new wheel (same operational note as prior companion fixes).

---

## Spec coverage checklist

| Spec item | Task |
|-----------|------|
| Stdlib ANSI / NO_COLOR / ADHD_HUB_NO_COLOR | Task 1 |
| Live `→ Running` | Task 3 |
| Banner + Do next / Fix these + Needs attention + Done counts | Task 2 |
| `--verbose` full list | Task 2 + cli.py |
| No rich dependency | Global + Task 1 |
| Docs table + four sections | Task 4 |
| Soft checklist, no `--with-*` / Settings | Task 4 |
| Tests | Tasks 1–4 |
| graphify update | Task 4 Step 6 |
| Wheel rebuild note | Task 5 |

## Placeholder / consistency self-review

- Signatures fixed: `print_report(report, *, verbose: bool = False)`, `print_running(command, *, file=…)`.
- Header rename: `Next steps:` → `Do next:` (update any assertions that still expect `Next steps:`).
- No TBD left in tasks.
