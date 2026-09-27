"""Node smoke: Quiet check-in / triage action row layout."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "js" / "triage_layout_smoke.mjs"


def test_triage_layout_title_and_actions() -> None:
    assert FIXTURE.is_file()
    proc = subprocess.run(
        ["node", str(FIXTURE)],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "triage_layout_smoke: ok" in proc.stdout
