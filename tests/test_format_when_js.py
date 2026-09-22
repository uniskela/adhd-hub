"""Node regression checks for Hub timestamp parsing / formatWhen."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "js" / "format_when_smoke.mjs"


def test_format_when_naive_midnight_is_utc_not_local() -> None:
    assert FIXTURE.is_file()
    proc = subprocess.run(
        ["node", str(FIXTURE)],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
