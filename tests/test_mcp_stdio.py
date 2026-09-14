from __future__ import annotations

import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from adhd_hub import cli


def test_cli_exposes_mcp_stdio_command() -> None:
    args = cli.build_parser().parse_args(["mcp-stdio"])

    assert args.command == "mcp-stdio"
    assert args.func is cli.cmd_mcp_stdio


@pytest.mark.asyncio
async def test_mcp_stdio_lists_and_calls_existing_tool_catalog(tmp_path) -> None:
    env = os.environ.copy()
    env["ADHD_HUB_DATA_DIR"] = str(tmp_path / "data")
    env["ADHD_HUB_AUTH_TOKEN"] = "stdio-test-token"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "adhd_hub.cli", "mcp-stdio"],
        env=env,
    )

    async with (
        stdio_client(params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        initialized = await session.initialize()
        assert initialized.instructions
        assert "resolve_project" in initialized.instructions
        assert "upsert_progress" in initialized.instructions

        listed = await session.list_tools()
        names = {tool.name for tool in listed.tools}
        assert {"resolve_project", "session_digest", "check_overlap", "upsert_progress"} <= names

        overlap = await session.call_tool("check_overlap", {"query": "test"})
        reminders = await session.call_tool("list_reminders", {"due_only": True})
        overview = await session.call_tool("get_overview", {})

        assert overlap.is_error is not True
        assert reminders.is_error is not True
        assert overview.is_error is not True
