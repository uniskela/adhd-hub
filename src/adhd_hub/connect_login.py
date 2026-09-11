"""CLI login handshake: PKCE + optional localhost callback + poll."""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from adhd_hub.connect import ConnectReport, normalize_hub_url
from adhd_hub.connect_auth import generate_pkce

_CREDENTIALS_MODE = 0o600


def credentials_path() -> Path:
    override = os.environ.get("ADHD_HUB_CREDENTIALS")
    if override and override.strip():
        return Path(override).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "adhd-hub" / "credentials.json"


def _read_credentials() -> dict[str, Any]:
    path = credentials_path()
    if not path.is_file():
        return {"sessions": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {"sessions": {}}
    if not isinstance(data, dict):
        return {"sessions": {}}
    if not isinstance(data.get("sessions"), dict):
        data = {**data, "sessions": {}}
    return data


def _write_credentials(data: dict[str, Any]) -> Path:
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(_CREDENTIALS_MODE)
    except OSError:
        pass
    return path


def load_saved_default_hub() -> str | None:
    """Return the preferred Hub URL from the local credentials file, if any."""
    data = _read_credentials()
    raw = data.get("default_hub")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return normalize_hub_url(raw)
    except ValueError:
        return None


def set_default_hub(hub_url: str) -> Path:
    """Persist preferred Hub URL for future CLI defaults (without requiring login)."""
    hub = normalize_hub_url(hub_url)
    data = _read_credentials()
    data["default_hub"] = hub
    if not isinstance(data.get("sessions"), dict):
        data["sessions"] = {}
    return _write_credentials(data)


def load_saved_token(hub_url: str) -> str | None:
    data = _read_credentials()
    sessions = data.get("sessions")
    if not isinstance(sessions, dict):
        return None
    entry = sessions.get(normalize_hub_url(hub_url))
    if not isinstance(entry, dict):
        return None
    token = entry.get("token")
    if not isinstance(token, str) or not token.strip():
        return None
    expires_at = entry.get("expires_at")
    if isinstance(expires_at, (int, float)) and expires_at <= time.time():
        return None
    return token.strip()


def save_credentials(hub_url: str, token: str, *, expires_in: int | None = None) -> Path:
    data = _read_credentials()
    hub = normalize_hub_url(hub_url)
    data["default_hub"] = hub
    sessions = data.setdefault("sessions", {})
    if not isinstance(sessions, dict):
        sessions = {}
        data["sessions"] = sessions
    entry: dict[str, Any] = {"token": token}
    if expires_in:
        entry["expires_at"] = time.time() + int(expires_in)
    sessions[hub] = entry
    return _write_credentials(data)


def clear_saved_token(hub_url: str) -> bool:
    path = credentials_path()
    if not path.is_file():
        return False
    data = _read_credentials()
    sessions = data.get("sessions")
    if not isinstance(sessions, dict):
        return False
    hub = normalize_hub_url(hub_url)
    removed = sessions.pop(hub, None) is not None
    if data.get("default_hub") == hub:
        data["default_hub"] = next(iter(sessions), None)
    _write_credentials(data)
    return removed


def resolve_cli_token(explicit: str | None, hub_url: str) -> str | None:
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("ADHD_HUB_AUTH_TOKEN") or "").strip()
    if env and env != "change-me":
        return env
    return load_saved_token(hub_url)


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            return resp.status, parsed if isinstance(parsed, dict) else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp else ""
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"detail": body}
        return exc.code, parsed if isinstance(parsed, dict) else {"detail": body}
    except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ConnectionError(str(exc)) from exc


def _error_code(payload: dict[str, Any]) -> str | None:
    detail = payload.get("detail")
    if isinstance(detail, dict) and isinstance(detail.get("error"), str):
        return detail["error"]
    if isinstance(payload.get("error"), str):
        return payload["error"]
    if isinstance(detail, str):
        return detail
    return None


class _CallbackState:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.code: str | None = None
        self.state: str | None = None
        self.error: str | None = None


def _start_callback_server(expected_state: str) -> tuple[ThreadingHTTPServer, _CallbackState]:
    bag = _CallbackState()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path.rstrip("/") != "/callback":
                self.send_error(404)
                return
            qs = parse_qs(parsed.query)
            code = (qs.get("code") or [""])[0]
            state = (qs.get("state") or [""])[0]
            err = (qs.get("error") or [""])[0]
            if err:
                bag.error = err
                bag.event.set()
            elif code and state == expected_state:
                bag.code = code
                bag.state = state
                bag.event.set()
            body = (
                b"<!doctype html><html><body style='font-family:system-ui;padding:2rem'>"
                b"<p>ADHD Hub CLI is connected. You can close this tab.</p>"
                b"</body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, bag


def run_login(
    hub_url: str,
    *,
    open_browser: bool = True,
    timeout: float | None = None,
    report: ConnectReport | None = None,
) -> str:
    """Complete the connect handshake and save a CLI session. Returns the token."""
    hub_url = normalize_hub_url(hub_url)
    report = report or ConnectReport(hub_url=hub_url)
    verifier, challenge = generate_pkce()
    state = secrets.token_urlsafe(16)
    server = None
    callback_url = None
    bag: _CallbackState | None = None
    try:
        server, bag = _start_callback_server(state)
        callback_url = f"http://127.0.0.1:{server.server_address[1]}/callback"
    except OSError as exc:
        report.add("localhost callback", "warn", f"unavailable ({exc}); will poll instead")

    payload: dict[str, Any] = {
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    if callback_url:
        payload["callback_url"] = callback_url
    try:
        status, body = _http_json(f"{hub_url}/api/connect/start", method="POST", payload=payload)
    except ConnectionError as exc:
        report.add("login", "error", f"could not reach Hub ({exc})")
        if server:
            server.shutdown()
        raise
    if status != 200:
        report.add("login", "error", _error_code(body) or f"HTTP {status}")
        if server:
            server.shutdown()
        raise RuntimeError(_error_code(body) or f"connect start failed ({status})")

    user_code = str(body.get("user_code") or "")
    device_code = str(body.get("device_code") or "")
    verify_url = str(body.get("verification_uri_complete") or f"{hub_url}/ui/")
    interval = max(1, int(body.get("interval") or 5))
    expires_in = int(body.get("expires_in") or 600)
    deadline = time.monotonic() + (timeout if timeout is not None else expires_in)

    report.add("connect code", "ok", user_code)
    print(f"Allow this CLI in the Hub UI:\n  {verify_url}")
    print(f"Or Settings → Connections, enter: {user_code}")
    if open_browser:
        try:
            opened = webbrowser.open(verify_url)
            report.add("browser", "ok" if opened else "warn", verify_url)
        except OSError as exc:
            report.add("browser", "warn", str(exc))
    else:
        report.add("browser", "skipped", "--no-browser")

    token: str | None = None
    last_error = "timed out"
    token_body: dict[str, Any] = {}
    try:
        while time.monotonic() < deadline:
            if bag and bag.event.is_set():
                if bag.error:
                    last_error = bag.error
                    break
                if bag.code:
                    try:
                        status, token_body = _http_json(
                            f"{hub_url}/api/connect/token",
                            method="POST",
                            payload={
                                "code": bag.code,
                                "code_verifier": verifier,
                                "state": bag.state or state,
                            },
                        )
                    except ConnectionError as exc:
                        last_error = str(exc)
                        break
                    if status == 200 and token_body.get("access_token"):
                        token = str(token_body["access_token"])
                        break
                    last_error = _error_code(token_body) or f"HTTP {status}"
                    if last_error in {"invalid_grant", "expired_token", "already_used"}:
                        break
            try:
                status, token_body = _http_json(
                    f"{hub_url}/api/connect/token",
                    method="POST",
                    payload={"device_code": device_code, "code_verifier": verifier},
                )
            except ConnectionError as exc:
                last_error = str(exc)
                time.sleep(interval)
                continue
            if status == 200 and token_body.get("access_token"):
                token = str(token_body["access_token"])
                break
            code = _error_code(token_body) or f"HTTP {status}"
            if code == "authorization_pending":
                remaining = deadline - time.monotonic()
                time.sleep(min(interval, max(0.2, remaining)))
                continue
            last_error = code
            if code in {"invalid_grant", "expired_token", "already_used"}:
                break
            time.sleep(min(interval, 2))
    finally:
        if server:
            server.shutdown()

    if not token:
        report.add("login", "error", last_error)
        raise RuntimeError(f"CLI login did not complete ({last_error})")

    path = save_credentials(
        hub_url, token, expires_in=int(token_body.get("expires_in") or 0) or None
    )
    report.add("login", "ok", f"session saved to {path} (not in your shell env)")
    return token


def run_logout(hub_url: str, token: str | None) -> None:
    hub_url = normalize_hub_url(hub_url)
    auth = token or load_saved_token(hub_url)
    if auth:
        try:
            _http_json(f"{hub_url}/api/connect/session", method="DELETE", token=auth)
        except ConnectionError:
            pass
    clear_saved_token(hub_url)
