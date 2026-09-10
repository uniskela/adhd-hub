"""Guard against ES module state assignment bugs that black-screen /ui."""

from __future__ import annotations

import re
from pathlib import Path

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
