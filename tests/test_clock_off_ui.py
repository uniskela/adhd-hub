"""Now and Settings Clock-Off copy stays quiet and timezone-aware."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "js" / "clock_off_ui_smoke.mjs"


def test_clock_off_ui_smoke() -> None:
    assert FIXTURE.is_file()
    proc = subprocess.run(
        ["node", str(FIXTURE)],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "clock_off_ui_smoke: ok" in proc.stdout
