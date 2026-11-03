"""Bounded, read-only Streamable HTTP diagnostics; never return remote error text."""

from __future__ import annotations

import ipaddress
import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx


def validate_mcp_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.scheme not in {"http", "https"}
    ):
        raise ValueError("MCP URL must be HTTP(S) without credentials, query or fragment")
    _ = parsed.port
    if parsed.scheme != "https" and parsed.hostname != "localhost":
        try:
            loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise ValueError("MCP requires HTTPS outside loopback; use your private HTTPS endpoint")


def _response_messages(response: httpx.Response, deadline: float) -> Iterator[Any]:
    buffer = ""
    total = 0
    sse = response.headers.get("content-type", "").split(";")[0] == "text/event-stream"
    for chunk in response.iter_text():
        total += len(chunk)
        if total > 1_048_576 or time.monotonic() > deadline:
            raise ValueError("MCP response exceeded size/time limit")
        buffer = (buffer + chunk).replace("\r\n", "\n")
        if sse:
            while "\n\n" in buffer:
                event, buffer = buffer.split("\n\n", 1)
                data = "\n".join(
                    line[5:].lstrip() for line in event.splitlines() if line.startswith("data:")
                )
                if data:
                    yield json.loads(data)
    if not sse:
        yield json.loads(buffer)


def _rpc_response(response: httpx.Response, request_id: int, deadline: float) -> dict[str, Any]:
    for message in _response_messages(response, deadline):
        if (
            isinstance(message, dict)
            and message.get("jsonrpc") == "2.0"
            and type(message.get("id")) is int
            and message["id"] == request_id
        ):
            return message
    raise ValueError("MCP response did not contain the requested JSON-RPC result")


@dataclass(repr=False)
class _MCPConnection:
    client: httpx.Client
    url: str
    headers: dict[str, str]
    deadline: float
    result: dict[str, Any]

    def post(self, method: str, request_id: int | None, params=None) -> dict[str, Any]:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if request_id is not None:
            payload["id"] = request_id
        if params is not None:
            payload["params"] = params
        # Only an equivalent /mcp -> /mcp/ redirect may carry credentials.
        for attempt in range(2):
            with self.client.stream(
                "POST", self.url, json=payload, headers=self.headers,
                timeout=remaining, follow_redirects=False,
            ) as response:
                status = response.status_code
                self.result["endpoint_reachable"] = True
                self.result["http_status"] = status
                if status in {307, 308} and attempt == 0:
                    target = urljoin(self.url, response.headers.get("location", ""))
                    if target != self.url.rstrip("/") + "/":
                        raise ValueError("MCP redirect refused; verify the configured endpoint")
                    self.url = target
                    continue
                return self._read_result(response, request_id)
        raise ValueError("MCP redirect limit exceeded")

    def _read_result(self, response: httpx.Response, request_id: int | None) -> dict[str, Any]:
        if response.status_code >= 300:
            raise httpx.HTTPStatusError(
                "MCP HTTP failure", request=response.request, response=response
            )
        if session := response.headers.get("mcp-session-id"):
            self.headers["Mcp-Session-Id"] = session
        if request_id is None:
            return {}
        message = _rpc_response(response, request_id, self.deadline)
        if "error" in message or not isinstance(message.get("result"), dict):
            raise ValueError("MCP returned a JSON-RPC error or malformed result")
        return message["result"]


def _discover_tools(connection: _MCPConnection, authenticated: bool) -> set[str]:
    initialized = connection.post(
        "initialize", 1,
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "adhd-hub-doctor", "version": "1"},
        },
    )
    protocol = initialized.get("protocolVersion")
    if not isinstance(protocol, str) or not isinstance(initialized.get("serverInfo"), dict):
        raise TypeError("MCP initialize result is malformed")
    connection.headers["MCP-Protocol-Version"] = protocol
    connection.result["initialized"] = True
    connection.result["authentication"] = "successful" if authenticated else "not required by endpoint"
    connection.post("notifications/initialized", None)
    names = set()
    cursor = None
    for page in range(64):
        listed = connection.post("tools/list", page + 2, {"cursor": cursor} if cursor else {})
        tools = listed.get("tools")
        if not isinstance(tools, list) or any(not isinstance(t, dict) for t in tools):
            raise ValueError("MCP tools/list result is malformed")
        names.update(t["name"] for t in tools if isinstance(t.get("name"), str))
        cursor = listed.get("nextCursor")
        if not cursor:
            return names
        if not isinstance(cursor, str):
            raise TypeError("MCP tools/list cursor is malformed")
    raise ValueError("MCP tools/list exceeded page limit")


def _http_failure(result: dict[str, Any], status: int, authenticated: bool) -> None:
    if status in {401, 403}:
        result["authentication"] = "rejected" if authenticated else "missing credentials"
        result["detail"] = f"HTTP {status}: credentials missing, rejected, expired or insufficient"
    else:
        result["detail"] = f"HTTP {status}: MCP endpoint failed; check URL and reverse proxy"


def probe_mcp(
    url: str,
    *,
    token: str | None = None,
    timeout: float = 8.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Verify initialize + tools/list directly, without launching a coding agent.

    Only pass the credential available to the caller being diagnosed. A saved
    CLI session is deliberately not loaded here. Expiry is determined by HTTP.
    """
    result: dict[str, Any] = {
        "endpoint_reachable": False,
        "authentication": "not verified",
        "initialized": False,
        "tools_discovered": False,
        "tool_count": 0,
        "http_status": None,
        "detail": "",
        "verification": "direct HTTP probe",
    }
    owned = client is None
    try:
        validate_mcp_url(url)
        if client is None:
            from adhd_hub.ssl_trust import ensure_os_truststore

            ensure_os_truststore()
            client = httpx.Client(timeout=timeout, follow_redirects=False)
        deadline = time.monotonic() + timeout
        headers = {"Accept": "application/json, text/event-stream"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        connection = _MCPConnection(client, url, headers, deadline, result)
        names = _discover_tools(connection, authenticated=bool(token))
        result["tool_count"] = len(names)
        result["tools_discovered"] = "get_overview" in names
        result["detail"] = (
            "MCP tools discovered (including get_overview)"
            if "get_overview" in names
            else "MCP responded but expected ADHD Hub tool get_overview is missing"
        )
    except httpx.HTTPStatusError as exc:
        _http_failure(result, exc.response.status_code, authenticated=bool(token))
    except (httpx.TimeoutException, TimeoutError):
        result["detail"] = "MCP request timed out"
    except (httpx.HTTPError, OSError):
        result["detail"] = "MCP transport/TLS failure; check network, certificate trust and URL"
    except (ValueError, TypeError):
        result["detail"] = "Invalid MCP URL, redirect or response; requires HTTPS outside loopback"
    finally:
        if owned and client is not None:
            client.close()
    return result
