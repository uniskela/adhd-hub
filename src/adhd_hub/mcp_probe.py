"""Bounded, read-only Streamable HTTP diagnostics; never return remote error text."""

from __future__ import annotations

import ipaddress
import json
import time
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


def _rpc_response(response: httpx.Response, request_id: int, deadline: float) -> dict[str, Any]:
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
                    message = json.loads(data)
                    if (
                        isinstance(message, dict)
                        and message.get("jsonrpc") == "2.0"
                        and type(message.get("id")) is int
                        and message["id"] == request_id
                    ):
                        return message
    if not sse:
        message = json.loads(buffer)
        if (
            isinstance(message, dict)
            and message.get("jsonrpc") == "2.0"
            and type(message.get("id")) is int
            and message["id"] == request_id
        ):
            return message
    raise ValueError("MCP response did not contain the requested JSON-RPC result")


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

        def post(method: str, request_id: int | None, params=None) -> dict[str, Any]:
            nonlocal url
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
            if request_id is not None:
                payload["id"] = request_id
            if params is not None:
                payload["params"] = params
            # Only an equivalent /mcp -> /mcp/ redirect may carry credentials.
            for attempt in range(2):
                with client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers=headers,
                    timeout=remaining,
                    follow_redirects=False,
                ) as response:
                    status = response.status_code
                    result["endpoint_reachable"] = True
                    result["http_status"] = status
                    if status in {307, 308} and attempt == 0:
                        target = urljoin(url, response.headers.get("location", ""))
                        if target != url.rstrip("/") + "/":
                            raise ValueError("MCP redirect refused; verify the configured endpoint")
                        url = target
                        continue
                    if status >= 300:
                        raise httpx.HTTPStatusError(
                            "MCP HTTP failure", request=response.request, response=response
                        )
                    if session := response.headers.get("mcp-session-id"):
                        headers["Mcp-Session-Id"] = session
                    if request_id is None:
                        return {}
                    message = _rpc_response(response, request_id, deadline)
                    if "error" in message or not isinstance(message.get("result"), dict):
                        raise ValueError("MCP returned a JSON-RPC error or malformed result")
                    return message["result"]
            raise ValueError("MCP redirect limit exceeded")

        initialized = post(
            "initialize",
            1,
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "adhd-hub-doctor", "version": "1"},
            },
        )
        protocol = initialized.get("protocolVersion")
        if not isinstance(protocol, str) or not isinstance(initialized.get("serverInfo"), dict):
            raise TypeError("MCP initialize result is malformed")
        headers["MCP-Protocol-Version"] = protocol
        result["initialized"] = True
        result["authentication"] = "successful" if token else "not required by endpoint"
        post("notifications/initialized", None)
        names = set()
        cursor = None
        for page in range(64):
            listed = post("tools/list", page + 2, {"cursor": cursor} if cursor else {})
            tools = listed.get("tools")
            if not isinstance(tools, list) or any(not isinstance(t, dict) for t in tools):
                raise ValueError("MCP tools/list result is malformed")
            names.update(t["name"] for t in tools if isinstance(t.get("name"), str))
            cursor = listed.get("nextCursor")
            if not cursor:
                break
            if not isinstance(cursor, str):
                raise TypeError("MCP tools/list cursor is malformed")
        else:
            raise ValueError("MCP tools/list exceeded page limit")
        result["tool_count"] = len(names)
        result["tools_discovered"] = "get_overview" in names
        result["detail"] = (
            "MCP tools discovered (including get_overview)"
            if "get_overview" in names
            else "MCP responded but expected ADHD Hub tool get_overview is missing"
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in {401, 403}:
            result["authentication"] = "rejected" if token else "missing credentials"
            result["detail"] = (
                f"HTTP {status}: credentials missing, rejected, expired or insufficient"
            )
        else:
            result["detail"] = f"HTTP {status}: MCP endpoint failed; check URL and reverse proxy"
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
