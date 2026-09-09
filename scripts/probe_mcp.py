"""Probe MCP tools/list without printing secrets."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

root = Path(__file__).resolve().parents[1]
env_path = root / ".env"
token = os.environ.get("ADHD_HUB_AUTH_TOKEN", "")
if not token and env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("ADHD_HUB_AUTH_TOKEN="):
            token = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

if not token:
    print("NO_TOKEN_IN_ENV")
    sys.exit(1)

base = os.environ.get("ADHD_HUB_MCP_URL", "http://127.0.0.1:8787/mcp")
# Prefer no trailing slash; Starlette may 307 POST /mcp → /mcp/ if redirect_slashes is on.


def post(payload: dict, session: str | None = None) -> tuple[int, dict[str, str], str]:
    data = json.dumps(payload).encode()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session:
        headers["mcp-session-id"] = session
    req = Request(base, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body
    except HTTPError as e:
        body = e.read().decode()
        return e.code, {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}, body

    except URLError:
        print("Connection failed. Check ADHD_HUB_MCP_URL and that the hub is running.")
        sys.exit(1)


def parse_body(body: str) -> dict:
    # JSON or SSE data: lines
    if body.startswith("{"):
        return json.loads(body)
    for line in body.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return {"raw": body[:500]}


status, headers, body = post(
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "probe", "version": "0.1"},
        },
    }
)
print(f"init_status={status}")

if status != 200:
    print("Initialization failed. Check the endpoint and access token.")
    sys.exit(1)
session = headers.get("mcp-session-id")
print(f"session={'yes' if session else 'no'}")
init_json = parse_body(body)
print(f"init_keys={list(init_json.keys())}")
if "result" in init_json:
    print(f"server={init_json['result'].get('serverInfo')}")
elif "error" in init_json:
    print(f"init_error={init_json['error']}")

post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session=session)
status2, _, body2 = post(
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session=session
)
print(f"tools_status={status2}")
tools_json = parse_body(body2)
tools = (tools_json.get("result") or {}).get("tools") or []
print(f"tool_count={len(tools)}")
print("tool_names=" + ",".join(t.get("name", "?") for t in tools))
if "error" in tools_json:
    print(f"tools_error={tools_json['error']}")

if status2 != 200 or "error" in tools_json or not tools:
    sys.exit(1)
