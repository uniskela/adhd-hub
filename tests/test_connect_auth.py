from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.auth import COOKIE_NAME
from adhd_hub.config import Settings
from adhd_hub.connect_auth import (
    ConnectStore,
    canonical_loopback_callback,
    generate_pkce,
    generate_user_code,
    normalize_user_code,
    verify_pkce,
)
from adhd_hub.connect_login import (
    credentials_path,
    load_saved_token,
    save_credentials,
)

BROWSER = {"X-Hub-Request": "1", "Origin": "http://testserver"}


def _client(tmp_path: Path, token: str = "secret") -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path, auth_token=token)))


def _login(client: TestClient) -> None:
    response = client.post("/api/auth/login", headers=BROWSER, json={"token": "secret"})
    assert response.status_code == 200


def test_pkce_and_user_code_helpers() -> None:
    verifier, challenge = generate_pkce()
    assert verify_pkce(verifier, challenge)
    assert not verify_pkce(verifier + "x", challenge)
    code = generate_user_code()
    assert normalize_user_code(code) == code
    assert normalize_user_code(code.replace("-", "").lower()) == code
    assert canonical_loopback_callback("http://127.0.0.1:8765/callback") == (
        "http://127.0.0.1:8765/callback"
    )


def test_loopback_callback_rejects_remote() -> None:
    for bad in (
        "https://127.0.0.1:9/callback",
        "http://example.com:9/callback",
        "http://127.0.0.1:9/other",
        "http://0.0.0.0:9/callback",
        "http://127.0.0.1/callback",
    ):
        try:
            canonical_loopback_callback(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_store_expiry_single_use_and_replay(tmp_path: Path) -> None:
    store = ConnectStore(tmp_path / "connect.sqlite3")
    verifier, challenge = generate_pkce()
    grant = store.start_grant(challenge=challenge, state="st", callback_url=None)
    status, token, _expires = store.exchange(
        verifier=verifier, device_code=grant["device_code"]
    )
    assert status == "pending"
    assert token is None

    info = store.approve_user_code(grant["user_code"])
    assert info.status == "approved"

    status, token, expires_in = store.exchange(
        verifier=verifier, device_code=grant["device_code"]
    )
    assert status == "ok"
    assert token and token.startswith("ahcli_")
    assert expires_in > 0
    assert store.valid_session(token)

    try:
        store.exchange(verifier=verifier, device_code=grant["device_code"])
        raise AssertionError("replay should fail")
    except KeyError:
        pass
    assert not store.valid_session("ahcli_not-a-real-token")


def test_store_expired_grant_rejected(tmp_path: Path) -> None:
    store = ConnectStore(tmp_path / "connect.sqlite3")
    verifier, challenge = generate_pkce()
    grant = store.start_grant(challenge=challenge, state=None, callback_url=None)
    store.expire_grant_now(grant["device_code"])
    try:
        store.approve_user_code(grant["user_code"])
        raise AssertionError("expired grant must not approve")
    except KeyError:
        pass
    try:
        store.exchange(verifier=verifier, device_code=grant["device_code"])
        raise AssertionError("expired grant must not exchange")
    except KeyError:
        pass


def test_store_wrong_verifier_rejected(tmp_path: Path) -> None:
    store = ConnectStore(tmp_path / "connect.sqlite3")
    _verifier, challenge = generate_pkce()
    other, _ = generate_pkce()
    grant = store.start_grant(challenge=challenge, state=None, callback_url=None)
    store.approve_user_code(grant["user_code"])
    try:
        store.exchange(verifier=other, device_code=grant["device_code"])
        raise AssertionError("wrong PKCE verifier must fail")
    except PermissionError:
        pass


def test_api_handshake_poll_and_replay(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        verifier, challenge = generate_pkce()
        start = client.post(
            "/api/connect/start",
            json={
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "abc",
                "callback_url": "http://127.0.0.1:34567/callback",
            },
        )
        assert start.status_code == 200
        body = start.json()
        assert "super-secret" not in str(body)
        user_code = body["user_code"]
        device_code = body["device_code"]
        assert body["verification_uri_complete"].endswith(f"?connect={user_code}")

        pending = client.post(
            "/api/connect/token",
            json={"device_code": device_code, "code_verifier": verifier},
        )
        assert pending.status_code == 400
        assert pending.json()["detail"]["error"] == "authorization_pending"

        assert (
            client.post(
                "/api/connect/approve", headers=BROWSER, json={"user_code": user_code}
            ).status_code
            == 401
        )
        _login(client)
        approved = client.post(
            "/api/connect/approve", headers=BROWSER, json={"user_code": user_code}
        )
        assert approved.status_code == 200
        assert approved.json()["redirect"].startswith("http://127.0.0.1:34567/callback?code=")

        token_resp = client.post(
            "/api/connect/token",
            json={"device_code": device_code, "code_verifier": verifier},
        )
        assert token_resp.status_code == 200
        cli_token = token_resp.json()["access_token"]
        assert cli_token.startswith("ahcli_")

        replay = client.post(
            "/api/connect/token",
            json={"device_code": device_code, "code_verifier": verifier},
        )
        assert replay.status_code == 400
        assert replay.json()["detail"]["error"] == "invalid_grant"

        overview = client.get("/api/overview", headers={"Authorization": f"Bearer {cli_token}"})
        assert overview.status_code == 200

        cookie = client.cookies.get(COOKIE_NAME)
        client.cookies.clear()
        listed = client.get("/api/connect/sessions", headers=BROWSER)
        assert listed.status_code == 401
        client.cookies.set(COOKIE_NAME, cookie, path="/api")
        listed = client.get("/api/connect/sessions", headers=BROWSER)
        assert listed.status_code == 200
        assert listed.json()["sessions"]


def test_api_exchange_via_callback_code(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        verifier, challenge = generate_pkce()
        start = client.post(
            "/api/connect/start",
            json={
                "code_challenge": challenge,
                "callback_url": "http://127.0.0.1:9999/callback",
                "state": "xyz",
            },
        )
        user_code = start.json()["user_code"]
        _login(client)
        approved = client.post(
            "/api/connect/approve", headers=BROWSER, json={"user_code": user_code.lower()}
        )
        redirect = approved.json()["redirect"]
        code = redirect.split("code=")[1].split("&")[0]
        exchanged = client.post(
            "/api/connect/token",
            json={"code": code, "code_verifier": verifier, "state": "xyz"},
        )
        assert exchanged.status_code == 200
        replay = client.post(
            "/api/connect/token",
            json={"code": code, "code_verifier": verifier, "state": "xyz"},
        )
        assert replay.status_code == 400


def test_start_rejects_non_loopback_callback(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _verifier, challenge = generate_pkce()
        resp = client.post(
            "/api/connect/start",
            json={
                "code_challenge": challenge,
                "callback_url": "http://evil.example/callback",
            },
        )
        assert resp.status_code == 400


def test_cli_session_authorizes_mcp(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_token="secret")
    store = ConnectStore(tmp_path / "connect.sqlite3")
    verifier, challenge = generate_pkce()
    grant = store.start_grant(challenge=challenge, state=None, callback_url=None)
    store.approve_user_code(grant["user_code"])
    status, token, _expires = store.exchange(verifier=verifier, device_code=grant["device_code"])
    assert status == "ok"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
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


def test_credentials_file_mode_and_lookup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADHD_HUB_CREDENTIALS", str(tmp_path / "creds.json"))
    path = save_credentials("http://hub.example:8787/", "ahcli_test", expires_in=60)
    assert path.is_file()
    assert (path.stat().st_mode & 0o777) == 0o600
    assert load_saved_token("http://hub.example:8787") == "ahcli_test"
    assert credentials_path() == path


def test_ui_connections_copy_has_no_export(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        home = client.get("/ui/")
        assert home.status_code == 200
        text = home.text
        assert "Do <strong>not</strong> export your server access token" in text
        assert "Allow this CLI" in text
        assert "btn-allow-cli" in text
        assert "install-cmd" in text
        assert "export TOKEN=" in text
