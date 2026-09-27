"""Node smoke: celebration + Done/Undo toast stack (no fixed-banner overlap)."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "js" / "toast_stack_smoke.mjs"


def test_toast_stack_celebration_and_keys() -> None:
    assert FIXTURE.is_file()
    proc = subprocess.run(
        ["node", str(FIXTURE)],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "toast_stack_smoke: ok" in proc.stdout
