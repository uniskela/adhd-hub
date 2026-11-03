"""Wave 8 — Short vs Deep Now return density preference."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings

ROOT = Path(__file__).resolve().parents[1]
DENSITY_MJS = ROOT / "src/adhd_hub/ui/js/return-density.mjs"


def test_normalize_return_density_via_node() -> None:
    script = f"""
import {{ normalizeReturnDensity }} from {DENSITY_MJS.as_uri()!r};
const cases = [
  [null, "deep"],
  ["", "deep"],
  ["deep", "deep"],
  ["short", "short"],
  ["SHORT", "deep"],
  ["nope", "deep"],
];
for (const [input, expect] of cases) {{
  const got = normalizeReturnDensity(input);
  if (got !== expect) {{
    console.error(JSON.stringify({{ input, got, expect }}));
    process.exit(1);
  }}
}}
console.log("ok");
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_return_density_wired_in_ui(tmp_path: Path) -> None:
    with TestClient(create_app(Settings(data_dir=tmp_path, auth_token="secret"))) as client:
        assert client.get("/ui/js/return-density.mjs").status_code == 200
        html = client.get("/ui/").text
        assert 'data-return-density="short"' in html
        assert 'data-return-density="deep"' in html
        assert "Return view" in html
        boot = client.get("/ui/js/boot.js").text
        assert "updateReturnDensityUi" in boot
        assert "setReturnDensity" in boot
        now = client.get("/ui/js/now.js").text
        assert "shortView" in now
        assert "progress-details" in now
        css = client.get("/ui/app.css").text
        assert "body.return-short .now-overview" in css
        sw = client.get("/ui/sw.js").text
        assert "/ui/js/return-density.mjs" in sw
        assert "adhd-hub-shell-v54" in sw
