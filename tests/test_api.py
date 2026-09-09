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
                "Access-Control-Request-Headers": "Authorization, X-Hub-Request",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    assert "x-hub-request" in response.headers["access-control-allow-headers"].lower()


def test_thread_resume_and_pause_are_exposed(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", auth_token="secret")
    app = create_app(settings)
    headers = {"Authorization": "Bearer secret"}
    with TestClient(app) as client:
        created = client.post(
            "/api/threads", headers=headers, json={"summary": "Write docs", "project_slug": "hub"}
        ).json()
        thread_id = created["id"]
        client.post(
            "/api/progress",
            headers=headers,
            json={
                "project_slug": "hub",
                "content": "## Return here\n\n- **Small step**\n\n<script>alert(1)</script>",
            },
        ).raise_for_status()
        paused = client.post(
            f"/api/threads/{thread_id}/pause",
            headers=headers,
            json={"next_step": "  Draft the intro  "},
        )
        assert paused.status_code == 200
        assert paused.json()["resume_step"] == "Draft the intro"
        detail = client.get(f"/api/threads/{thread_id}", headers=headers)
        assert detail.status_code == 200
        assert "resume_step_html" in detail.json()
        assert "Draft the intro" in detail.json()["resume_step_html"]
        assert "<h2>Return here</h2>" in detail.json()["progress_html"]
        assert "<strong>Small step</strong>" in detail.json()["progress_html"]
        assert "<script>" not in detail.json()["progress_html"]
        assert client.get(f"/api/threads/{thread_id}").status_code == 401
        assert (
            client.post(
                f"/api/threads/{thread_id}/pause", headers=headers, json={"next_step": "  "}
            ).status_code
            == 422
        )
        client.post(
            "/api/threads/mark-done", headers=headers, json={"id": thread_id}
        ).raise_for_status()
        assert (
            client.post(
                f"/api/threads/{thread_id}/pause", headers=headers, json={"next_step": "Too late"}
            ).status_code
            == 409
        )


def test_brand_assets_are_available_without_login(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, auth_token="secret"))
    with TestClient(app) as client:
        for name in ("icon.svg", "logo.svg", "logo-dark.svg"):
            response = client.get(f"/ui/brand/{name}")
            assert response.status_code == 200
            assert "image/svg+xml" in response.headers["content-type"]
            assert "<svg" in response.text
        assert client.get("/ui/brand/unknown.svg").status_code == 404
