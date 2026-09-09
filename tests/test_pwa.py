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
        assert "adhd-hub-shell-v2" in sw.text

        icon = client.get("/ui/brand/icon-192.png")
        assert icon.status_code == 200
        assert icon.headers["content-type"].startswith("image/png")
