"""Wave 8 — Web Share Target compose helper."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings

ROOT = Path(__file__).resolve().parents[1]
SHARE_MJS = ROOT / "src/adhd_hub/ui/js/share-capture.mjs"


def test_compose_share_capture_summary_via_node() -> None:
    script = f"""
import {{ composeShareCaptureSummary }} from {SHARE_MJS.as_uri()!r};

function check(qs, expect) {{
  const got = composeShareCaptureSummary(new URLSearchParams(qs));
  if (got !== expect) {{
    console.error(JSON.stringify({{ qs, got, expect }}));
    process.exit(1);
  }}
}}

check("title=Hi&text=Hi&url=https://x.test", "Hi\\nhttps://x.test");
check("title=A&text=B about https://x.test&url=https://x.test", "A\\nB about https://x.test");
check("title=Read this: https://x.test&url=https://x.test", "Read this: https://x.test");
check("text=only", "only");
check("url=https://only.test", "https://only.test");
check("", "");
const long = "x".repeat(600);
check("text=" + long, long.slice(0, 500));
console.log("ok");
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_share_capture_module_served(tmp_path: Path) -> None:
    with TestClient(create_app(Settings(data_dir=tmp_path, auth_token="secret"))) as client:
        res = client.get("/ui/js/share-capture.mjs")
        assert res.status_code == 200
        assert "composeShareCaptureSummary" in res.text
        boot = client.get("/ui/js/boot.js").text
        assert "openShareCaptureIfRequested" in boot
        auth = client.get("/ui/js/auth.js").text
        assert "openShareCaptureIfRequested" in auth
        sw = client.get("/ui/sw.js").text
        assert "/ui/js/share-capture.mjs" in sw
