"""Settings commands use the current agent selection without saving preferences."""

import subprocess
from pathlib import Path


def test_connect_settings_commands():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["node", "--experimental-vm-modules", "tests/js/connect_settings_smoke.mjs"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "connect_settings_smoke: ok" in result.stdout
