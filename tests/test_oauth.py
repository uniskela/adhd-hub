from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings

MCP_ACCEPT = {"Accept": "application/json, text/event-stream"}


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        auth_token="secret",
        public_url="https://hub.example",
    )
    with TestClient(create_app(settings), base_url="http://testserver") as client:
        yield client


def test_oauth_protected_resource_metadata(client: TestClient) -> None:
    r = client.get("/.well-known/oauth-protected-resource")
    assert r.status_code == 200
    body = r.json()
    assert body["resource"] == "https://hub.example/mcp"
    assert body["authorization_servers"] == ["https://hub.example"]


def test_oauth_protected_resource_metadata_path_aware(client: TestClient) -> None:
    r = client.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200
    body = r.json()
    assert body["resource"] == "https://hub.example/mcp"
    assert body["authorization_servers"] == ["https://hub.example"]


def test_oauth_authorization_server_metadata(client: TestClient) -> None:
    r = client.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    body = r.json()
    assert body["issuer"] == "https://hub.example"
    assert body["authorization_endpoint"] == "https://hub.example/api/oauth/authorize"
    assert body["token_endpoint"] == "https://hub.example/api/oauth/token"
    assert body["registration_endpoint"] == "https://hub.example/api/oauth/register"
    assert body["code_challenge_methods_supported"] == ["S256"]
    assert body["response_types_supported"] == ["code"]
    assert body["grant_types_supported"] == ["authorization_code"]
    assert "refresh_token" not in body["grant_types_supported"]


def test_mcp_401_includes_resource_metadata(client: TestClient) -> None:
    r = client.post("/mcp", headers=MCP_ACCEPT)
    assert r.status_code == 401
    www = r.headers.get("www-authenticate", "")
    assert 'Bearer realm="mcp"' in www
    assert (
        'resource_metadata="https://hub.example/.well-known/oauth-protected-resource"'
        in www
    )


def test_messages_401_includes_resource_metadata(client: TestClient) -> None:
    r = client.post("/messages", headers=MCP_ACCEPT)
    assert r.status_code == 401
    www = r.headers.get("www-authenticate", "")
    assert "resource_metadata=" in www.lower()


def test_public_url_preferred_over_testclient_host(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        auth_token="secret",
        public_url="https://hub.example",
    )
    with TestClient(create_app(settings), base_url="http://evil.internal:8787") as client:
        body = client.get("/.well-known/oauth-protected-resource").json()
        assert body["resource"] == "https://hub.example/mcp"
        www = client.post("/mcp", headers=MCP_ACCEPT).headers["www-authenticate"]
        assert "https://hub.example/.well-known/oauth-protected-resource" in www
        assert "evil.internal" not in www


def test_loopback_request_host_fallback_without_public_url(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_token="secret", public_url=None)
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as client:
        body = client.get("/.well-known/oauth-authorization-server").json()
        assert body["issuer"] == "http://127.0.0.1:8787"
        assert body["authorization_endpoint"] == "http://127.0.0.1:8787/api/oauth/authorize"


def test_oauth_disabled_hides_discovery_and_plain_bearer(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        auth_token="secret",
        public_url="https://hub.example",
        oauth_enabled=False,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/.well-known/oauth-protected-resource").status_code == 404
        assert client.get("/.well-known/oauth-authorization-server").status_code == 404
        assert client.get("/.well-known/oauth-protected-resource/mcp").status_code == 404
        www = client.post("/mcp", headers=MCP_ACCEPT).headers.get("www-authenticate", "")
        assert www == "Bearer"
        assert "resource_metadata" not in www.lower()
