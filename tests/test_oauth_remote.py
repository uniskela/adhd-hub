"""OAuth over direct/forwarded loopback; no external OpenClaw or SSH dependency."""

from __future__ import annotations

import logging
import select
import socket
import socketserver
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import ProxyHandler, build_opener

import pytest
from httpx import ASGITransport, AsyncClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.connect_auth import generate_pkce
from adhd_hub.connect_login import _start_callback_server
from adhd_hub.oauth import AUTH_CODE_SECONDS

RESOURCE = "https://hub.example/mcp"
BROWSER = {"Origin": "https://hub.example", "X-Hub-Request": "1"}


@contextmanager
def _forward_to(port: int):
    """Model SSH's byte-preserving local forward, not its authentication layer."""

    class Forwarder(socketserver.BaseRequestHandler):
        def handle(self):
            with socket.create_connection(("127.0.0.1", port), timeout=5) as upstream:
                peers = (self.request, upstream)
                while True:
                    ready, _, _ = select.select(peers, [], [], 5)
                    if not ready:
                        return
                    for source in ready:
                        data = source.recv(65536)
                        if not data:
                            return
                        target = upstream if source is self.request else self.request
                        target.sendall(data)

    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Forwarder) as server:
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
        worker.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            worker.join(timeout=5)


async def _authorize(client: AsyncClient, redirect: str, state: str):
    reg = await client.post(
        "/api/oauth/register",
        json={
            "client_name": "remote gateway regression",
            "redirect_uris": [redirect],
        },
    )
    assert reg.status_code == 201
    client_id = reg.json()["client_id"]
    login = await client.post("/api/auth/login", headers=BROWSER, json={"token": "secret"})
    assert login.status_code == 200
    verifier, challenge = generate_pkce()
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "resource": RESOURCE,
    }
    consent = await client.get("/api/oauth/authorize", params=params)
    assert consent.status_code == 200
    result = await client.post(
        "/api/oauth/authorize",
        headers=BROWSER,
        data={**params, "decision": "allow"},
    )
    assert result.status_code == 200
    return params, verifier, result.json()["redirect"]


def _app(tmp_path: Path):
    return create_app(
        Settings(data_dir=tmp_path, auth_token="secret", public_url="https://hub.example")
    )


@pytest.mark.parametrize("forwarded", [False, True], ids=["local", "remote-forwarded"])
async def test_callback_delivery_state_and_single_use(
    tmp_path: Path,
    forwarded: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # This is the real Hub CLI receiver, not a stand-in implementation of state checking.
    # OpenClaw owns its equivalent state check; we do not claim to test that binary.
    expected_state = "original-session-0123456789"
    caplog.set_level(logging.INFO)
    gateway, received = _start_callback_server(expected_state)
    try:
        with _forward_to(gateway.server_port) as forwarded_port:
            browser_port = forwarded_port if forwarded else gateway.server_port
            redirect = f"http://127.0.0.1:{browser_port}/callback"
            async with AsyncClient(
                transport=ASGITransport(app=_app(tmp_path)),
                base_url="https://hub.example",
            ) as hub:
                params, verifier, callback = await _authorize(hub, redirect, expected_state)
                query = parse_qs(urlparse(callback).query)
                code = query["code"][0]
                assert query["state"] == [expected_state]
                # urllib avoids HTTPX's URL-bearing INFO log for the callback request.
                browser = build_opener(ProxyHandler({}))
                for wrong_state in ["", "different-session"]:
                    invalid = redirect + "?" + urlencode({"code": code, "state": wrong_state})
                    with browser.open(invalid, timeout=5):
                        pass
                    assert not received.event.is_set()
                    assert received.code is None
                with pytest.raises(HTTPError) as wrong_path:
                    browser.open(redirect + "/other?" + urlencode(query, doseq=True), timeout=5)
                assert wrong_path.value.code == 404
                assert not received.event.is_set()
                with browser.open(callback, timeout=5) as response:
                    assert response.status == 200
                assert received.event.wait(timeout=2)
                assert received.code == code
                assert received.state == expected_state
                exchange = {
                    "grant_type": "authorization_code",
                    "client_id": params["client_id"],
                    "redirect_uri": redirect,
                    "resource": RESOURCE,
                    "code_verifier": verifier,
                    "code": received.code,
                }
                token = await hub.post("/api/oauth/token", data=exchange)
                assert token.status_code == 200
                assert token.json()["token_type"] == "Bearer"
                replay = await hub.post("/api/oauth/token", data=exchange)
                assert replay.status_code == 400
                assert replay.json() == {"error": "invalid_grant"}
                assert code not in caplog.text
                assert verifier not in caplog.text
                assert token.json()["access_token"] not in caplog.text
    finally:
        gateway.shutdown()
        gateway.server_close()


@pytest.mark.parametrize("mismatch", ["redirect", "client", "verifier", "expired"])
async def test_remote_code_rejects_wrong_binding_or_expiry(
    tmp_path: Path,
    mismatch: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redirect = "http://127.0.0.1:8989/oauth/callback"
    async with AsyncClient(
        transport=ASGITransport(app=_app(tmp_path)),
        base_url="https://hub.example",
    ) as hub:
        params, verifier, callback = await _authorize(hub, redirect, "gateway-session")
        exchange = {
            "grant_type": "authorization_code",
            "client_id": params["client_id"],
            "redirect_uri": redirect,
            "resource": RESOURCE,
            "code_verifier": verifier,
            "code": parse_qs(urlparse(callback).query)["code"][0],
        }
        if mismatch == "redirect":
            # Even another valid HTTPS URI is not interchangeable with the registered URI.
            exchange["redirect_uri"] = "https://gateway.example/oauth/callback"
        elif mismatch == "client":
            other = await hub.post("/api/oauth/register", json={"redirect_uris": [redirect]})
            exchange["client_id"] = other.json()["client_id"]
        elif mismatch == "verifier":
            exchange["code_verifier"] = generate_pkce()[0]
        else:
            import time

            future = time.time() + AUTH_CODE_SECONDS + 1
            monkeypatch.setattr("adhd_hub.oauth.time.time", lambda: future)
        result = await hub.post("/api/oauth/token", data=exchange)
        assert result.status_code == 400
        assert result.json() == {"error": "invalid_grant"}


@pytest.mark.parametrize(
    "bad_redirect",
    [
        "https://gateway.example/oauth/callback",
        "http://127.0.0.1:8989/other",
        "http://127.0.0.1:8990/oauth/callback",
        "http://gateway.example:8989/oauth/callback",
    ],
)
async def test_remote_authorize_never_rewrites_or_accepts_unregistered_callback(
    tmp_path: Path,
    bad_redirect: str,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_app(tmp_path)),
        base_url="https://hub.example",
    ) as hub:
        params, _, _ = await _authorize(
            hub,
            "http://127.0.0.1:8989/oauth/callback",
            "gateway-session",
        )
        params["redirect_uri"] = bad_redirect
        for method in ["GET", "POST"]:
            if method == "GET":
                result = await hub.get("/api/oauth/authorize", params=params)
            else:
                result = await hub.post(
                    "/api/oauth/authorize",
                    headers=BROWSER,
                    data={**params, "decision": "allow"},
                )
            assert result.status_code == 400
            assert result.json() == {"error": "invalid_redirect_uri"}
            assert "location" not in result.headers
