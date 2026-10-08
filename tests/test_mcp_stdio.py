from __future__ import annotations

import json
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

        async def call(name, arguments):
            result = await session.call_tool(name, arguments)
            assert result.is_error is not True, result
            assert result.structured_content == json.loads(result.content[0].text)
            return result.structured_content

        # Exercise success, selection and error shapes over the real transport.
        missing = await call(
            "resolve_project", {"project_slug": "missing", "create_if_missing": False}
        )
        assert missing == {"error": "not_found"}
        project = await call("resolve_project", {"project_slug": "contract"})
        assert project["slug"] == "contract"
        assert "result" not in project
        thread = await call(
            "upsert_thread",
            {
                "summary": "Ship contract",
                "project_slug": "contract",
                "goal": "Ship contract",
            },
        )
        assert thread["return_cue"]["quality"] == "missing"
        progress = await call(
            "upsert_progress",
            {
                "project_slug": "contract",
                "thread_id": thread["id"],
                "resume_step": "Open tests/test_mcp_stdio.py",
                "next_steps": [],
            },
        )
        assert progress["thread_id"] == thread["id"]
        assert progress["needs_thread_selection"] is False
        assert progress["thread"]["completion"]["ready"] is True
        await call(
            "upsert_thread", {"summary": "Other unrelated outcome", "project_slug": "contract"}
        )
        selection = await call(
            "upsert_progress", {"project_slug": "contract", "content": "checkpoint"}
        )
        assert selection["needs_thread_selection"] is True
        assert len(selection["candidates"]) == 2
        assert "created_thread" not in selection
        notes = await call(
            "upsert_progress",
            {
                "project_slug": "contract",
                "content": "Decision recorded",
                "create_thread_if_missing": False,
            },
        )
        assert notes["thread"] is None
        invalid = await call(
            "upsert_progress", {"project_slug": "contract", "thread_id": "missing"}
        )
        assert invalid["error"] == "not_found"
        assert "detail" in invalid
        assert await call("mark_done", {"thread_id": "missing"}) == {
            "error": "not_found",
            "id": "missing",
        }
        guidance = await call(
            "report_guidance_health",
            {
                "project_slug": "contract",
                "agent_guidance_version": 7,
            },
        )
        assert guidance["recorded"] is True
        assert isinstance(guidance["guidance"], str)  # Existing JSON-string wire field.
        digest = await call("session_digest", {})
        assert "completion" in digest["items"][0]
        assert "return_cue" in digest["items"][0]
        done = await call("mark_done", {"thread_id": thread["id"]})
        assert done["status"] == "done"
        assert "return_cue" not in done  # mark_done retains its raw Thread wire shape.
