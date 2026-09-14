"""Guard against ES module state assignment bugs that black-screen /ui."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

UI_JS = Path(__file__).resolve().parents[1] / "src" / "adhd_hub" / "ui" / "js"

MUTABLE = [
    "authStatus",
    "loginMode",
    "celebrationTimeout",
    "threadsCache",
    "threadsRequest",
    "projectRequest",
    "currentView",
    "projectFilter",
    "overviewCache",
    "detailCache",
    "activeScreen",
    "chosenId",
    "chosenThread",
    "focusState",
    "focusRequest",
    "pauseTarget",
    "nowMessage",
    "shareFile",
    "shareVersion",
    "focusModeOn",
    "focusEndsAt",
    "focusTimerId",
    "archivedProjectsCache",
    "currentTz",
    "repoUrl",
    "repoDisplayUrl",
]


def test_state_is_mutable_object():
    state = (UI_JS / "state.js").read_text()
    assert "export const state = {" in state
    assert "export let focusEndsAt" not in state
    assert "focusEndsAt:" in state


def test_clear_focus_session_assigns_via_state():
    now = (UI_JS / "now.js").read_text()
    assert "export function clearFocusSession" in now
    assert "state.focusEndsAt = 0" in now
    # Bare assignment would throw "Assignment to constant variable" at runtime.
    assert re.search(r"(?<![\w.])focusEndsAt\s*=", now) is None


def test_modules_do_not_reassign_imported_bindings():
    """Imported bindings are live but read-only; assign via state.* only."""
    bare_assign = re.compile(
        r"(?<![\w.$])(" + "|".join(MUTABLE) + r")\s*=(?!=)"
    )
    bare_inc = re.compile(
        r"(?<![\w.$])(?:\+\+(" + "|".join(MUTABLE) + r")|(" + "|".join(MUTABLE) + r")\+\+)"
    )
    failures: list[str] = []
    for path in sorted(UI_JS.glob("*.js")):
        if path.name == "state.js":
            continue
        text = path.read_text()
        for m in bare_assign.finditer(text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line = text[line_start : text.find("\n", m.start())].strip()
            if line.startswith("import ") or "import {" in line:
                continue
            if text[max(0, m.start() - 6) : m.start()] == "state.":
                continue
            failures.append(f"{path.name}: {line}")
        for m in bare_inc.finditer(text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line = text[line_start : text.find("\n", m.start())].strip()
            if text[max(0, m.start() - 6) : m.start()] == "state.":
                continue
            # ++state.x is fine; state.x++ is fine — bare ++x is not.
            if "state." in line[max(0, line.find(m.group(0)) - 6) :]:
                continue
            failures.append(f"{path.name} ++: {line}")
    assert not failures, "Bare mutable reassignments:\n" + "\n".join(failures)


def _load_splitter():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "split_ui_modules.py"
    spec = importlib.util.spec_from_file_location("split_ui_modules", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_qualify_mutable_refs_ignores_comment_periods():
    splitter = _load_splitter()
    src = """
      // Clear end marker so the next Start can begin a fresh session.
      focusEndsAt = 0;
      foo.focusEndsAt = 1;
"""
    out = splitter.qualify_mutable_refs(src)
    assert "state.focusEndsAt = 0" in out
    assert re.search(r"(?<![\w.])focusEndsAt\s*=", out) is None
    assert "foo.focusEndsAt = 1" in out


def test_legacy_renderer_preserves_focus_timer_mutability():
    splitter = _load_splitter()
    files = splitter.render_all()
    splitter.assert_no_mutable_regressions(files)
    assert re.search(r"(?<![\w.])focusEndsAt\s*=", files["now.js"]) is None


@pytest.mark.parametrize("args", [[], ["--check"]])
def test_splitter_does_not_modify_maintained_ui(tmp_path: Path, monkeypatch, args):
    splitter = _load_splitter()
    ui = tmp_path / "ui"
    shutil.copytree(UI_JS.parent, ui)
    monkeypatch.setattr(splitter, "OUT", ui / "js")
    # Neither CLI mode may read the obsolete migration input.
    monkeypatch.setattr(splitter, "APP_PATH", tmp_path / "missing-app.js")
    before = {p.relative_to(ui): p.read_bytes() for p in ui.rglob("*") if p.is_file()}
    assert Path("js/forge-jobs.js") in before
    if args:
        splitter.main(args)
    else:
        with pytest.raises(SystemExit) as exc:
            splitter.main(args)
        assert exc.value.code == 2
    after = {p.relative_to(ui): p.read_bytes() for p in ui.rglob("*") if p.is_file()}
    assert after == before


def test_splitter_check_rejects_mutability_regression_without_writing(tmp_path: Path, monkeypatch):
    splitter = _load_splitter()
    monkeypatch.setattr(splitter, "OUT", tmp_path)
    now = tmp_path / "now.js"
    broken = (UI_JS / "now.js").read_text().replace("state.focusEndsAt = 0", "focusEndsAt = 0")
    now.write_text(broken)
    with pytest.raises(SystemExit, match="bare focusEndsAt assignment"):
        splitter.main(["--check"])
    assert now.read_text() == broken


def test_splitter_check_rejects_missing_now_module(tmp_path: Path, monkeypatch):
    splitter = _load_splitter()
    monkeypatch.setattr(splitter, "OUT", tmp_path)
    with pytest.raises(SystemExit, match="Missing now.js"):
        splitter.main(["--check"])
    assert list(tmp_path.iterdir()) == []
