from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings


def test_api_health_and_auth(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="secret",
        host="127.0.0.1",
        port=8787,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        r = client.post(
            "/api/threads",
            json={"summary": "Finish DNS cutover", "project_slug": "dns"},
        )
        assert r.status_code == 401
        r = client.post(
            "/api/threads",
            headers={"Authorization": "Bearer secret"},
            json={
                "summary": "Finish DNS cutover",
                "project_slug": "dns",
                "source_tool": "cursor",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["project_slug"] == "dns"

        ov = client.get(
            "/api/overlap",
            headers={"Authorization": "Bearer secret"},
            params={"q": "dns cutover homelab"},
        )
        assert ov.status_code == 200
        assert ov.json()["hits"]


async def test_public_url_allows_browser_preflight_for_bearer_requests(tmp_path: Path) -> None:
    origin = "https://adhd.pike.homes"
    app = create_app(
        Settings(
            data_dir=tmp_path / "data",
            auth_token="secret",
            public_url=f"{origin}/",
        )
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.options(
            "/api/threads",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
