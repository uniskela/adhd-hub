"""Settings commands use the current agent selection without saving preferences."""

import shutil
import subprocess
from pathlib import Path


def test_connect_settings_commands(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    modules = tmp_path / "js"
    shutil.copytree(root / "src/adhd_hub/ui/js", modules)
    shutil.copy2(root / "tests/js/connect_settings_smoke.mjs", modules)
    (modules / "package.json").write_text('{"type":"module"}', encoding="utf-8")
    result = subprocess.run(
        ["node", "connect_settings_smoke.mjs"],
        cwd=modules,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "connect_settings_smoke: ok" in result.stdout
