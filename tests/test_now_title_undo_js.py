"""Node smoke: Now title coercion + Undo Done toast wiring."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "js" / "now_title_undo_smoke.mjs"


def test_now_title_and_undo_toast_wiring() -> None:
    assert FIXTURE.is_file()
    proc = subprocess.run(
        ["node", str(FIXTURE)],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
