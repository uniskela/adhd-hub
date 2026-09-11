from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.connect_auth import generate_pkce, verify_pkce
from adhd_hub.oauth import OAuthStore

MCP_ACCEPT = {"Accept": "application/json, text/event-stream"}
MCP_RESOURCE = "https://hub.example/mcp"


def _register_and_code(
    store: OAuthStore,
    *,
    resource: str = MCP_RESOURCE,
    redirect_uri: str = "http://127.0.0.1:9999/callback",
) -> tuple[dict, str, str, str]:
    client = store.register_client(
        client_name="cursor",
        redirect_uris=[redirect_uri],
    )
    verifier, challenge = generate_pkce()
    code = store.create_auth_code(
        client_id=client["client_id"],
        redirect_uri=redirect_uri,
        resource=resource,
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    return client, code, verifier, redirect_uri


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


def test_pkce_verify_success_and_fail() -> None:
    verifier, challenge = generate_pkce()
    assert verify_pkce(verifier, challenge)
    assert not verify_pkce(verifier + "x", challenge)
    assert not verify_pkce("short", challenge)


def test_auth_code_consume_once_and_bindings(tmp_path: Path) -> None:
    store = OAuthStore(tmp_path / "connect.sqlite3")
    client, code, verifier, redirect_uri = _register_and_code(store)

    row = store.consume_auth_code(
        code=code,
        client_id=client["client_id"],
        redirect_uri=redirect_uri,
        resource=MCP_RESOURCE,
        code_verifier=verifier,
    )
    assert row is not None
    assert row["client_id"] == client["client_id"]
    assert row["resource"] == MCP_RESOURCE

    assert (
        store.consume_auth_code(
            code=code,
            client_id=client["client_id"],
            redirect_uri=redirect_uri,
            resource=MCP_RESOURCE,
            code_verifier=verifier,
        )
        is None
    )


def test_auth_code_rejects_wrong_bindings(tmp_path: Path) -> None:
    store = OAuthStore(tmp_path / "connect.sqlite3")
    client, code, verifier, redirect_uri = _register_and_code(store)
    other, _ = generate_pkce()

    assert (
        store.consume_auth_code(
            code=code,
            client_id="not-the-client",
            redirect_uri=redirect_uri,
            resource=MCP_RESOURCE,
            code_verifier=verifier,
        )
        is None
    )
    assert (
        store.consume_auth_code(
            code=code,
            client_id=client["client_id"],
            redirect_uri="http://127.0.0.1:1/other",
            resource=MCP_RESOURCE,
            code_verifier=verifier,
        )
        is None
    )
    assert (
        store.consume_auth_code(
            code=code,
            client_id=client["client_id"],
            redirect_uri=redirect_uri,
            resource="https://hub.example/other",
            code_verifier=verifier,
        )
        is None
    )
    assert (
        store.consume_auth_code(
            code=code,
            client_id=client["client_id"],
            redirect_uri=redirect_uri,
            resource=MCP_RESOURCE,
            code_verifier=other,
        )
        is None
    )
    # Still consumable once with correct bindings.
    assert (
        store.consume_auth_code(
            code=code,
            client_id=client["client_id"],
            redirect_uri=redirect_uri,
            resource=MCP_RESOURCE,
            code_verifier=verifier,
        )
        is not None
    )


def test_concurrent_auth_code_consume_one_winner(tmp_path: Path) -> None:
    store = OAuthStore(tmp_path / "connect.sqlite3")
    client, code, verifier, redirect_uri = _register_and_code(store)
    results: list[object] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait()
        results.append(
            store.consume_auth_code(
                code=code,
                client_id=client["client_id"],
                redirect_uri=redirect_uri,
                resource=MCP_RESOURCE,
                code_verifier=verifier,
            )
        )

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    winners = [r for r in results if r is not None]
    assert len(winners) == 1
    assert results.count(None) == 1


def test_access_token_valid_wrong_expired_and_hashed(tmp_path: Path) -> None:
    db = tmp_path / "connect.sqlite3"
    store = OAuthStore(db)
    client = store.register_client(
        client_name="cursor",
        redirect_uris=["http://127.0.0.1:9999/callback"],
    )
    token = store.issue_access_token(client_id=client["client_id"], resource=MCP_RESOURCE)
    assert token.startswith("ahoauth_")
    assert store.valid_access_token(token)
    assert not store.valid_access_token("ahoauth_not-real")
    assert not store.valid_access_token("ahcli_not-oauth")

    raw_blob = db.read_bytes()
    assert token.encode() not in raw_blob
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT token_hash FROM oauth_access_tokens").fetchall()
        assert rows
        assert all(token not in (row[0] or "") for row in rows)

    store.expire_access_token_now(token)
    assert not store.valid_access_token(token)


def test_auth_code_absent_from_sqlite(tmp_path: Path) -> None:
    db = tmp_path / "connect.sqlite3"
    store = OAuthStore(db)
    _client, code, _verifier, _redirect = _register_and_code(store)
    assert code.encode() not in db.read_bytes()
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT code_hash FROM oauth_auth_codes").fetchall()
        assert rows
        assert all(code not in (row[0] or "") for row in rows)


def test_static_bearer_still_authorizes_mcp_with_oauth_store(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        auth_token="secret",
        public_url="https://hub.example",
    )
    headers = {
        "Authorization": "Bearer secret",
        **MCP_ACCEPT,
        "Content-Type": "application/json",
    }
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as client:
        assert client.post("/mcp", headers=MCP_ACCEPT).status_code == 401
        response = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        assert response.status_code == 200


def test_oauth_token_authorizes_mcp_not_rest(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        auth_token="secret",
        public_url="https://hub.example",
    )
    store = OAuthStore(tmp_path / "connect.sqlite3")
    client_row = store.register_client(
        client_name="cursor",
        redirect_uris=["http://127.0.0.1:9999/callback"],
    )
    token = store.issue_access_token(
        client_id=client_row["client_id"], resource=MCP_RESOURCE
    )
    headers = {
        "Authorization": f"Bearer {token}",
        **MCP_ACCEPT,
        "Content-Type": "application/json",
    }
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as client:
        mcp = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        assert mcp.status_code == 200
        # OAuth tokens must not satisfy REST auth_dependency.
        assert client.get("/api/overview", headers={"Authorization": f"Bearer {token}"}).status_code == 401
