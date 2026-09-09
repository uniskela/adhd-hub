from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings


def test_mcp_discovery_validation_and_progress(tmp_path):
    settings = Settings(data_dir=tmp_path, auth_token="secret")
    headers = {
        "Authorization": "bearer secret",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as client:

        def rpc(method, params=None, path="/mcp"):
            return client.post(
                path,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params or {},
                },
                follow_redirects=False,
            )

        response = rpc(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        assert response.status_code == 200
        for path in ("/mcp", "/mcp/"):
            response = rpc("tools/list", path=path)
            assert response.status_code == 200
            tools = {tool["name"]: tool for tool in response.json()["result"]["tools"]}
            assert tools["list_projects"]["annotations"]["readOnlyHint"] is True
            assert tools["list_projects"]["inputSchema"]["properties"]["limit"]["minimum"] == 1
            assert (
                "create_thread_if_missing" in tools["upsert_progress"]["inputSchema"]["properties"]
            )
        invalid = rpc("tools/call", {"name": "list_projects", "arguments": {"limit": -1}})
        assert invalid.json()["result"]["isError"] is True
        result = rpc(
            "tools/call",
            {
                "name": "upsert_progress",
                "arguments": {
                    "project_slug": "review",
                    "content": "Review complete",
                    "create_thread_if_missing": False,
                },
            },
        )
        assert not result.json()["result"].get("isError")
        threads = client.get("/api/threads", headers={"Authorization": "Bearer secret"}).json()
        assert threads == []
