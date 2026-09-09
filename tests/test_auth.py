from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.auth import COOKIE_NAME, BrowserSessions
from adhd_hub.config import Settings, load_settings


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(data_dir=tmp_path, auth_token="secret"))) as client:
        yield client


def test_browser_login_logout_and_csrf(client):
    headers = {"X-Hub-Request": "1", "Origin": "http://testserver"}
    assert client.post("/api/auth/login", json={"token": "secret"}).status_code == 403
    assert (
        client.post("/api/auth/login", headers=headers, json={"token": "wrong"}).status_code == 401
    )
    response = client.post("/api/auth/login", headers=headers, json={"token": "secret"})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "secret" not in cookie
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/overview").status_code == 200
    old_session = client.cookies.get(COOKIE_NAME)
    payload = {"summary": "Resume browser work", "project_slug": "browser"}
    assert client.post("/api/threads", json=payload).status_code == 403
    assert (
        client.post(
            "/api/threads", headers={**headers, "Origin": "https://evil.example"}, json=payload
        ).status_code
        == 403
    )
    assert client.post("/api/threads", headers=headers, json=payload).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/overview").status_code == 401
    client.cookies.set(COOKIE_NAME, old_session, path="/api")
    assert client.get("/api/overview").status_code == 401


def test_configured_public_url_is_accepted_behind_tls_proxy(tmp_path):
    public_origin = "https://adhd.pike.homes"
    app = create_app(
        Settings(data_dir=tmp_path, auth_token="secret", public_url=public_origin)
    )
    with TestClient(app, base_url="http://adhd-hub.internal:8787") as client:
        response = client.post(
            "/api/auth/login",
            headers={"X-Hub-Request": "1", "Origin": public_origin},
            json={"token": "secret"},
        )

    assert response.status_code == 200


def test_secure_cookie_and_bearer_compatibility(tmp_path):
    with TestClient(
        create_app(Settings(data_dir=tmp_path, auth_token="secret")), base_url="https://testserver"
    ) as client:
        response = client.post(
            "/api/auth/login", headers={"X-Hub-Request": "1"}, json={"token": "secret"}
        )
        assert "Secure" in response.headers["set-cookie"]
        assert (
            client.get("/api/overview", headers={"Authorization": "Bearer wrong"}).status_code
            == 401
        )
        assert (
            client.post(
                "/api/threads",
                headers={"Authorization": "Bearer secret"},
                json={"summary": "CLI work"},
            ).status_code
            == 200
        )
        # Browser sessions never authorize MCP.
        assert client.post("/mcp", json={}).status_code == 401
        assert client.post("/mcp", json={}).headers["www-authenticate"] == "Bearer"


def test_session_expiry_and_capacity():
    sessions = BrowserSessions()
    token = sessions.create()
    assert sessions.valid(token)
    sessions.tokens[token] = 0
    assert not sessions.valid(token)
    assert not sessions.valid("invented")
    for _ in range(1030):
        sessions.create()
    assert len(sessions.tokens) == 1024
    assert token not in sessions.tokens


def test_network_bind_requires_token(tmp_path):
    with pytest.raises(ValueError, match="ADHD_HUB_AUTH_TOKEN"):
        create_app(Settings(data_dir=tmp_path, host="0.0.0.0", auth_token="change-me"))


def test_config_environment_overrides_toml(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text('auth_token = "toml-token"\npublic_url = "https://toml.example"\n')
    monkeypatch.setenv("ADHD_HUB_AUTH_TOKEN", "env-token")
    monkeypatch.setenv("ADHD_HUB_PUBLIC_URL", "https://hub.example/")
    settings = load_settings(config)
    assert settings.auth_token == "env-token"
    assert settings.resolve_public_url() == "https://hub.example"


def test_public_url_fallback():
    assert Settings(_env_file=None).resolve_public_url() is None
    assert (
        Settings(hub_url="http://localhost:8787/").resolve_public_url() == "http://localhost:8787"
    )


def test_password_setup_login_change_and_recovery(client, tmp_path):
    headers = {"X-Hub-Request": "1"}
    assert client.get("/api/auth/status").json()["password_configured"] is False
    client.post("/api/auth/login", headers=headers, json={"token": "secret"})
    old_session = client.cookies.get(COOKIE_NAME)
    payload = {
        "current_method": "token",
        "current_secret": "secret",
        "password": "a memorable private phrase",
    }
    assert client.put("/api/auth/password", json=payload).status_code == 403
    response = client.put("/api/auth/password", headers=headers, json=payload)
    assert response.status_code == 200
    assert client.get("/api/auth/status").json()["password_configured"] is True
    new_session = client.cookies.get(COOKIE_NAME)
    assert old_session != new_session
    client.cookies.set(COOKIE_NAME, old_session, domain="testserver.local", path="/api")
    assert client.get("/api/overview").status_code == 401
    client.cookies.clear()
    assert (
        client.post("/api/auth/login", headers=headers, json={"password": "wrong"}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", headers=headers, json={"password": payload["password"]}
        ).status_code
        == 200
    )
    # Dashboard passwords never work as REST or MCP bearer credentials.
    assert (
        client.get(
            "/api/overview", headers={"Authorization": f"Bearer {payload['password']}"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/mcp", headers={"Authorization": f"Bearer {payload['password']}"}, json={}
        ).status_code
        == 401
    )
    response = client.put(
        "/api/auth/password",
        headers=headers,
        json={
            "current_method": "password",
            "current_secret": payload["password"],
            "password": "an entirely different phrase",
        },
    )
    assert response.status_code == 200
    assert (
        client.post(
            "/api/auth/login", headers=headers, json={"password": payload["password"]}
        ).status_code
        == 401
    )
    # A forgotten password can be reset with the independent server token.
    assert client.put("/api/auth/password", headers=headers, json=payload).status_code == 200
    password_file = tmp_path / "dashboard-password.hash"
    assert payload["password"] not in password_file.read_text()
    assert password_file.stat().st_mode & 0o777 == 0o600


def test_password_validation_and_throttling(client):
    headers = {"X-Hub-Request": "1"}
    assert (
        client.put(
            "/api/auth/password",
            headers=headers,
            json={
                "current_method": "token",
                "current_secret": "secret",
                "password": "short",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/auth/login", headers=headers, json={"token": "secret", "password": "x"}
        ).status_code
        == 422
    )
    for _ in range(5):
        assert (
            client.post(
                "/api/auth/login", headers=headers, json={"password": "incorrect"}
            ).status_code
            == 401
        )
    response = client.post("/api/auth/login", headers=headers, json={"token": "secret"})
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    # Password-reset attempts share the same rate limit.
    assert (
        client.put(
            "/api/auth/password",
            headers=headers,
            json={
                "current_method": "token",
                "current_secret": "secret",
                "password": "a memorable private phrase",
            },
        ).status_code
        == 429
    )


def test_password_persists_across_restart_and_corrupt_file_recovers(tmp_path):
    headers = {"X-Hub-Request": "1"}
    settings = Settings(data_dir=tmp_path, auth_token="secret")
    payload = {
        "current_method": "token",
        "current_secret": "secret",
        "password": "a memorable private phrase",
    }
    with TestClient(create_app(settings)) as first:
        assert first.put("/api/auth/password", headers=headers, json=payload).status_code == 200
    with TestClient(create_app(settings)) as second:
        assert (
            second.post(
                "/api/auth/login", headers=headers, json={"password": payload["password"]}
            ).status_code
            == 200
        )
        (tmp_path / "dashboard-password.hash").write_text("broken")
        assert (
            second.post(
                "/api/auth/login", headers=headers, json={"password": payload["password"]}
            ).status_code
            == 503
        )
        assert second.put("/api/auth/password", headers=headers, json=payload).status_code == 200


def test_default_token_cannot_enable_password(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, auth_token="change-me"))) as client:
        response = client.put(
            "/api/auth/password",
            headers={"X-Hub-Request": "1"},
            json={
                "current_method": "token",
                "current_secret": "change-me",
                "password": "a memorable private phrase",
            },
        )
        assert response.status_code == 409
        assert not (tmp_path / "dashboard-password.hash").exists()


def test_throttle_expires(monkeypatch):
    from adhd_hub.auth import LoginThrottle

    now = 1000
    monkeypatch.setattr("adhd_hub.auth.time.monotonic", lambda: now)
    throttle = LoginThrottle()
    for _ in range(5):
        throttle.check("client")
    with pytest.raises(HTTPException) as error:
        throttle.check("client")
    assert error.value.status_code == 429
    now += 61
    throttle.check("client")
    assert len(throttle.attempts["client"]) == 1


@pytest.mark.parametrize(
    "path,method,payload,secrets",
    [
        (
            "/api/auth/login",
            "post",
            {"token": "private-token", "password": "private-password"},
            ["private-token", "private-password"],
        ),
        (
            "/api/auth/password",
            "put",
            {"current_secret": "recovery-secret", "password": "tiny-phrase"},
            ["recovery-secret", "tiny-phrase"],
        ),
        (
            "/api/auth/login",
            "post",
            {"password": {"nested-secret": "private-value"}},
            ["nested-secret", "private-value"],
        ),
    ],
)
def test_auth_validation_never_echoes_credentials(client, path, method, payload, secrets):
    response = getattr(client, method)(path, headers={"X-Hub-Request": "1"}, json=payload)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    for secret in secrets:
        assert secret not in response.text
    assert "input" not in response.json()["detail"][0]


def test_non_auth_validation_keeps_useful_errors(client):
    response = client.post("/api/threads", headers={"Authorization": "Bearer secret"}, json={})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "summary"]
