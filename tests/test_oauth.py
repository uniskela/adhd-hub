from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.auth import COOKIE_NAME
from adhd_hub.config import Settings
from adhd_hub.connect_auth import generate_pkce, verify_pkce
from adhd_hub.oauth import OAuthStore, is_allowed_redirect_uri, is_safe_oauth_return_path

MCP_ACCEPT = {"Accept": "application/json, text/event-stream"}
MCP_RESOURCE = "https://hub.example/mcp"
BROWSER = {"X-Hub-Request": "1", "Origin": "https://hub.example"}
LOOPBACK_REDIRECT = "http://127.0.0.1:9999/callback"


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


def _oauth_settings(tmp_path: Path, **kwargs) -> Settings:
    base = {
        "data_dir": tmp_path,
        "auth_token": "secret",
        "public_url": "https://hub.example",
    }
    base.update(kwargs)
    return Settings(**base)


def _login(client: TestClient) -> None:
    response = client.post("/api/auth/login", headers=BROWSER, json={"token": "secret"})
    assert response.status_code == 200
    assert client.cookies.get(COOKIE_NAME)


def _authorize_query(
    *,
    client_id: str,
    redirect_uri: str = LOOPBACK_REDIRECT,
    challenge: str,
    state: str = "xyz",
    resource: str = MCP_RESOURCE,
) -> dict[str, str]:
    return {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "resource": resource,
    }


def test_is_allowed_redirect_uri_policy() -> None:
    assert is_allowed_redirect_uri("https://app.example/oauth/callback")
    assert is_allowed_redirect_uri("http://127.0.0.1:9999/callback")
    assert is_allowed_redirect_uri("http://localhost:3334/cb")
    assert is_allowed_redirect_uri("http://[::1]:8080/callback")
    assert not is_allowed_redirect_uri("http://evil.example/callback")
    assert not is_allowed_redirect_uri("https://app.example/cb#frag")
    assert not is_allowed_redirect_uri("https://user:pass@app.example/cb")
    assert not is_allowed_redirect_uri("javascript:alert(1)")
    assert not is_allowed_redirect_uri("http://127.0.0.1/callback")  # no port


def test_is_safe_oauth_return_path() -> None:
    ok = "/api/oauth/authorize?response_type=code&client_id=x"
    assert is_safe_oauth_return_path(ok)
    assert not is_safe_oauth_return_path("//evil.example")
    assert not is_safe_oauth_return_path("https://evil.example/api/oauth/authorize")
    assert not is_safe_oauth_return_path("/api/auth/login")
    assert not is_safe_oauth_return_path("/api/oauth/authorize/../token")
    assert not is_safe_oauth_return_path("javascript:alert(1)")


def test_dcr_register_loopback_and_rejects_remote_http(tmp_path: Path) -> None:
    settings = _oauth_settings(tmp_path)
    with TestClient(create_app(settings), base_url="http://testserver") as client:
        ok = client.post(
            "/api/oauth/register",
            json={
                "client_name": "test-client",
                "redirect_uris": [LOOPBACK_REDIRECT],
                "token_endpoint_auth_method": "none",
            },
        )
        assert ok.status_code == 201
        body = ok.json()
        assert body["client_id"]
        assert body["redirect_uris"] == [LOOPBACK_REDIRECT]
        assert body["token_endpoint_auth_method"] == "none"
        assert "client_id_issued_at" in body

        bad = client.post(
            "/api/oauth/register",
            json={
                "client_name": "evil",
                "redirect_uris": ["http://evil.example/callback"],
                "token_endpoint_auth_method": "none",
            },
        )
        assert bad.status_code == 400
        assert bad.json().get("error") == "invalid_redirect_uri"


def test_oauth_disabled_hides_oauth_api_routes(tmp_path: Path) -> None:
    settings = _oauth_settings(tmp_path, oauth_enabled=False)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/oauth/authorize").status_code == 404
        assert client.post("/api/oauth/token").status_code == 404
        assert client.post("/api/oauth/register", json={}).status_code == 404


def test_authorize_unauthenticated_redirects_to_ui_return(tmp_path: Path) -> None:
    settings = _oauth_settings(tmp_path)
    with TestClient(create_app(settings), base_url="http://testserver") as client:
        reg = client.post(
            "/api/oauth/register",
            json={
                "client_name": "cursor",
                "redirect_uris": [LOOPBACK_REDIRECT],
                "token_endpoint_auth_method": "none",
            },
        ).json()
        verifier, challenge = generate_pkce()
        params = _authorize_query(client_id=reg["client_id"], challenge=challenge)
        response = client.get("/api/oauth/authorize", params=params, follow_redirects=False)
        assert response.status_code in {302, 303, 307}
        location = response.headers["location"]
        assert location.startswith("/ui/")
        parsed = urlparse(location)
        q = parse_qs(parsed.query)
        assert "oauth_return" in q
        ret = q["oauth_return"][0]
        assert is_safe_oauth_return_path(ret)
        assert ret.startswith("/api/oauth/authorize?")
        assert "client_id=" in ret
        assert verifier  # keep verifier used so lint stays quiet in RED→GREEN cycle


def test_authorize_invalid_redirect_never_redirects(tmp_path: Path) -> None:
    settings = _oauth_settings(tmp_path)
    with TestClient(create_app(settings), base_url="http://testserver") as client:
        _login(client)
        reg = client.post(
            "/api/oauth/register",
            json={
                "client_name": "cursor",
                "redirect_uris": [LOOPBACK_REDIRECT],
                "token_endpoint_auth_method": "none",
            },
        ).json()
        _, challenge = generate_pkce()
        params = _authorize_query(
            client_id=reg["client_id"],
            challenge=challenge,
            redirect_uri="http://evil.example/steal",
        )
        response = client.get("/api/oauth/authorize", params=params, follow_redirects=False)
        assert response.status_code == 400
        loc = response.headers.get("location", "")
        assert "evil.example" not in loc
        assert "steal" not in (response.text or "")


def test_full_oauth_flow_mcp_only_and_deny_replay(tmp_path: Path) -> None:
    settings = _oauth_settings(tmp_path)
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as client:
        # Metadata still advertises paths
        meta = client.get("/.well-known/oauth-authorization-server").json()
        assert meta["authorization_endpoint"].endswith("/api/oauth/authorize")
        assert meta["token_endpoint"].endswith("/api/oauth/token")
        assert meta["registration_endpoint"].endswith("/api/oauth/register")

        reg = client.post(
            "/api/oauth/register",
            json={
                "client_name": "cursor",
                "redirect_uris": [LOOPBACK_REDIRECT],
                "token_endpoint_auth_method": "none",
            },
        )
        assert reg.status_code == 201
        client_id = reg.json()["client_id"]
        verifier, challenge = generate_pkce()
        state = "st-1"
        params = _authorize_query(client_id=client_id, challenge=challenge, state=state)

        _login(client)
        consent = client.get("/api/oauth/authorize", params=params)
        assert consent.status_code == 200
        assert "text/html" in consent.headers.get("content-type", "")
        assert "Content-Security-Policy" in consent.headers
        assert "frame-ancestors 'none'" in consent.headers["Content-Security-Policy"]
        assert "Allow" in consent.text

        # Plain cross-origin form POST must fail (no CSRF headers)
        bare = client.post(
            "/api/oauth/authorize",
            data={
                "decision": "allow",
                "client_id": client_id,
                "redirect_uri": LOOPBACK_REDIRECT,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
                "resource": MCP_RESOURCE,
                "response_type": "code",
            },
            follow_redirects=False,
        )
        assert bare.status_code == 403

        allow = client.post(
            "/api/oauth/authorize",
            headers=BROWSER,
            data={
                "decision": "allow",
                "client_id": client_id,
                "redirect_uri": LOOPBACK_REDIRECT,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
                "resource": MCP_RESOURCE,
                "response_type": "code",
            },
            follow_redirects=False,
        )
        assert allow.status_code in {302, 303}
        loc = allow.headers["location"]
        assert loc.startswith(LOOPBACK_REDIRECT)
        q = parse_qs(urlparse(loc).query)
        assert q["state"] == [state]
        code = q["code"][0]
        assert code

        token_resp = client.post(
            "/api/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": LOOPBACK_REDIRECT,
                "client_id": client_id,
                "code_verifier": verifier,
                "resource": MCP_RESOURCE,
            },
        )
        assert token_resp.status_code == 200
        assert token_resp.headers.get("cache-control") == "no-store"
        assert token_resp.headers.get("pragma") == "no-cache"
        token_body = token_resp.json()
        access = token_body["access_token"]
        assert token_body["token_type"] == "Bearer"
        assert token_body["expires_in"] > 0
        assert access.startswith("ahoauth_")

        mcp = client.post(
            "/mcp",
            headers={
                "Authorization": f"Bearer {access}",
                **MCP_ACCEPT,
                "Content-Type": "application/json",
            },
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
        assert client.get(
            "/api/overview", headers={"Authorization": f"Bearer {access}"}
        ).status_code == 401

        # Replay code fails
        replay = client.post(
            "/api/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": LOOPBACK_REDIRECT,
                "client_id": client_id,
                "code_verifier": verifier,
                "resource": MCP_RESOURCE,
            },
        )
        assert replay.status_code in {400, 401}
        assert replay.json().get("error")

        # Deny → access_denied
        verifier2, challenge2 = generate_pkce()
        params2 = _authorize_query(
            client_id=client_id, challenge=challenge2, state="deny-me"
        )
        assert client.get("/api/oauth/authorize", params=params2).status_code == 200
        deny = client.post(
            "/api/oauth/authorize",
            headers=BROWSER,
            data={
                "decision": "deny",
                "client_id": client_id,
                "redirect_uri": LOOPBACK_REDIRECT,
                "code_challenge": challenge2,
                "code_challenge_method": "S256",
                "state": "deny-me",
                "resource": MCP_RESOURCE,
                "response_type": "code",
            },
            follow_redirects=False,
        )
        assert deny.status_code in {302, 303}
        dq = parse_qs(urlparse(deny.headers["location"]).query)
        assert dq["error"] == ["access_denied"]
        assert dq["state"] == ["deny-me"]


def test_static_bearer_and_cli_session_still_work_with_oauth_routes(
    tmp_path: Path,
) -> None:
    """Static Bearer regression (CLI covered by test_connect_auth suite)."""
    settings = _oauth_settings(tmp_path)
    headers = {
        "Authorization": "Bearer secret",
        **MCP_ACCEPT,
        "Content-Type": "application/json",
    }
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as client:
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
