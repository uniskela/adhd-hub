from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.models import ReminderCreate, ReminderKind, ThreadUpsert
from adhd_hub.service import HubService


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
            assert "thread_id" in tools["upsert_progress"]["inputSchema"]["properties"]
            assert "force_new_thread" in tools["upsert_progress"]["inputSchema"]["properties"]
            assert "goal" in tools["upsert_progress"]["inputSchema"]["properties"]
            assert "repo_url" in tools["upsert_project"]["inputSchema"]["properties"]
            for name in (
                "pause_thread",
                "dismiss_thread",
                "list_reminders",
                "get_overview",
                "register_workspace",
                "push_openclaw_memory",
            ):
                assert name in tools
            assert tools["get_overview"]["annotations"]["readOnlyHint"] is True
            assert tools["list_reminders"]["annotations"]["readOnlyHint"] is True
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


def test_mcp_wave2_tools_pause_dismiss_overview_register(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", auth_token="secret")
    app = create_app(settings)
    headers = {
        "Authorization": "bearer secret",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    service: HubService = app.state.service
    thread = service.upsert_thread(
        ThreadUpsert(summary="Ship wave 2", project_slug="wave-two", source_tool="cursor")
    )
    service.set_reminder(ReminderCreate(message="Breathe", kind=ReminderKind.session))

    with TestClient(app, base_url="http://127.0.0.1:8787") as client:

        def call(name: str, arguments: dict | None = None):
            return client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments or {}},
                },
            )

        client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )

        overview = call("get_overview")
        assert not overview.json()["result"].get("isError")
        # MCP structured content is usually in content[0].text JSON
        body = overview.json()["result"]
        text = body["content"][0]["text"]
        assert "open" in text

        reminders = call("list_reminders", {"due_only": True})
        assert "Breathe" in reminders.json()["result"]["content"][0]["text"]

        paused = call(
            "pause_thread",
            {"thread_id": thread.id, "next_step": "Open the PR draft"},
        )
        assert "Open the PR draft" in paused.json()["result"]["content"][0]["text"]
        refreshed = service.store.get_thread(thread.id)
        assert refreshed is not None
        assert refreshed.resume_step == "Open the PR draft"
        assert refreshed.paused_at is not None

        workspace = tmp_path / "sites" / "my-app"
        workspace.mkdir(parents=True)
        registered = call(
            "register_workspace",
            {
                "workspace_path": str(workspace),
                "title": "My App",
                "create_open_thread": True,
            },
        )
        assert "my-app" in registered.json()["result"]["content"][0]["text"].lower() or "My App" in (
            registered.json()["result"]["content"][0]["text"]
        )
        assert service.store.get_project("my-app") is not None

        dismissed = call("dismiss_thread", {"thread_id": thread.id, "note": "Not now"})
        assert not dismissed.json()["result"].get("isError")
        gone = service.store.get_thread(thread.id)
        assert gone is not None
        assert gone.status.value == "dismissed"


def test_openclaw_memory_digest_and_sync(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_thread(
        ThreadUpsert(summary="Polish docs", project_slug="docs", source_tool="cursor")
    )
    title, body = service.openclaw_memory_digest(note="Keep it short")
    assert "ADHD Hub" in title
    assert "Polish docs" in body
    assert "Keep it short" in body
    assert "transcript" not in body.lower()

    # Whitespace-only resume_step must not crash digest
    blank = service.upsert_thread(
        ThreadUpsert(summary="Whitespace pause", project_slug="docs", source_tool="cursor")
    )
    service.store.pause_thread(blank.id, "real step")
    with service.store._conn() as conn:
        conn.execute("UPDATE threads SET resume_step = ? WHERE id = ?", ("   \n  ", blank.id))
    _, body2 = service.openclaw_memory_digest()
    assert "Whitespace pause" in body2

    service.openclaw.sync_memory_note_sync = lambda title, content: True  # type: ignore[method-assign]
    out = service.push_openclaw_memory_sync(note="ack please")
    assert out["ok"] is True
    assert out["ack"] == "saved"


async def test_stale_nudge_pushes_memory_roundtrip(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="secret"))
    from adhd_hub.models import Thread

    thread = Thread(
        id="stale-two",
        summary="Resume the draft",
        project_slug="demo",
        created_at=datetime.now(UTC) - timedelta(days=5),
        updated_at=datetime.now(UTC) - timedelta(days=5),
    )
    service.list_stale_threads = lambda: [thread]  # type: ignore[method-assign]
    service.store.touch_reminded = lambda ids: None  # type: ignore[method-assign]
    service.openclaw.notify_stale_threads = AsyncMock(return_value=True)
    service.push_openclaw_memory = AsyncMock(  # type: ignore[method-assign]
        return_value={"ok": True, "ack": "saved", "digest_lines": 1}
    )
    result = await service.run_stale_nudge()
    assert result["nudged"] == 1
    assert result["openclaw"] is True
    assert result["memory"]["ack"] == "saved"
    service.push_openclaw_memory.assert_awaited()
    kwargs = service.push_openclaw_memory.await_args.kwargs
    assert kwargs["threads"] == [thread]
    assert "stale" in kwargs["note"].lower()
