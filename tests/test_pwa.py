from pathlib import Path

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings


def test_pwa_manifest_and_service_worker(tmp_path: Path):
    with TestClient(create_app(Settings(data_dir=tmp_path, auth_token="secret"))) as client:
        manifest = client.get("/ui/manifest.webmanifest")
        assert manifest.status_code == 200
        assert manifest.headers["content-type"].startswith("application/manifest+json")
        body = manifest.json()
        assert body["name"] == "ADHD Progress Hub"
        assert body["start_url"] == "/ui/"
        assert any(icon["src"].endswith("icon-192.png") for icon in body["icons"])

        sw = client.get("/ui/sw.js")
        assert sw.status_code == 200
        assert "Service-Worker-Allowed" in sw.headers
        assert "adhd-hub-shell-v3" in sw.text
        assert "/ui/js/boot.js" in sw.text

        icon = client.get("/ui/brand/icon-192.png")
        assert icon.status_code == 200
        assert icon.headers["content-type"].startswith("image/png")

        home = client.get("/ui/")
        assert home.status_code == 200
        assert b'type="module" src="/ui/js/boot.js"' in home.content
        assert b'id="chart-summary"' in home.content
        assert b'aria-live="polite"' in home.content

        boot = client.get("/ui/js/boot.js")
        assert boot.status_code == 200
        assert "export async function loadAll" in boot.text or "loadAll" in boot.text

        for name in (
            "state.js",
            "dom.js",
            "api.js",
            "auth.js",
            "theme.js",
            "screens.js",
            "now.js",
            "work.js",
            "progress.js",
            "settings.js",
            "load.js",
            "boot.js",
        ):
            assert client.get(f"/ui/js/{name}").status_code == 200, name

        assert client.get("/ui/js/not-a-module.js").status_code == 404
        assert client.get("/ui/js/capture.js").status_code == 404

        legacy = client.get("/ui/app.js", follow_redirects=False)
        assert legacy.status_code in (307, 302)
        assert legacy.headers["location"].endswith("/ui/js/boot.js")
