"""Local contract checks; no external score or service is needed."""

from adhd_hub.config import Settings
from adhd_hub.mcp_app import build_mcp
from adhd_hub.service import HubService

PUBLIC_TOOLS = {
    "check_overlap",
    "suggest_duplicate_threads",
    "request_thread_merge",
    "thread_merge_history",
    "list_open_threads",
    "list_projects",
    "resolve_project",
    "upsert_project",
    "rename_project",
    "delete_project",
    "list_pending_actions",
    "upsert_thread",
    "upsert_progress",
    "mark_done",
    "pause_thread",
    "dismiss_thread",
    "confirm_thread_relevant",
    "snooze_thread_triage",
    "list_reminders",
    "get_overview",
    "register_workspace",
    "report_guidance_health",
    "set_reminder",
    "suggest_next_up",
    "session_digest",
    "push_openclaw_memory",
}


async def test_current_catalog_has_useful_parameter_descriptions(tmp_path):
    server = build_mcp(HubService(Settings(data_dir=tmp_path, auth_token="test")))
    tools = {tool.name: tool for tool in await server.list_tools()}
    assert set(tools) == PUBLIC_TOOLS
    for name, tool in tools.items():
        for parameter, schema in tool.input_schema.get("properties", {}).items():
            description = schema.get("description", "").strip()
            assert description and description != parameter, (name, parameter)

    progress = tools["upsert_progress"].input_schema["properties"]
    assert "thread_id" in progress["force_new_thread"]["description"]
    assert "create_thread_if_missing" in progress["force_new_thread"]["description"]
    assert "workspace_path" in progress["project_slug"]["description"]
    assert progress["create_thread_if_missing"]["default"] is True
    assert progress["force_new_thread"]["default"] is False
    assert tools["check_overlap"].input_schema["properties"]["limit"]["minimum"] == 1
    assert tools["snooze_thread_triage"].input_schema["properties"]["days"]["maximum"] == 30


async def test_critical_output_schemas_describe_agent_decisions(tmp_path):
    server = build_mcp(HubService(Settings(data_dir=tmp_path, auth_token="test")))
    tools = {tool.name: tool for tool in await server.list_tools()}
    progress = tools["upsert_progress"].output_schema
    assert progress is not None
    # References may hold nested schemas, but public result fields stay at the root.
    assert {"needs_thread_selection", "candidates", "created_thread", "thread", "error"} <= set(
        progress["properties"]
    )
    session = tools["session_digest"].output_schema
    assert {"open_count", "stale_count", "items", "due_reminders", "guidance"} <= set(
        session["properties"]
    )
    assert any("completion" in model.get("properties", {}) for model in session["$defs"].values())
    assert any("return_cue" in model.get("properties", {}) for model in session["$defs"].values())
    for name in ("resolve_project", "mark_done"):
        schema = tools[name].output_schema
        assert schema is not None
        assert "error" in schema["properties"] or "anyOf" in schema


async def test_annotations_match_side_effects(tmp_path):
    server = build_mcp(HubService(Settings(data_dir=tmp_path, auth_token="test")))
    tools = {tool.name: tool for tool in await server.list_tools()}
    profiles = {
        # read-only, destructive, idempotent, open-world
        (True, False, True, False): {
            "check_overlap",
            "suggest_duplicate_threads",
            "thread_merge_history",
            "list_open_threads",
            "list_projects",
            "list_pending_actions",
            "list_reminders",
            "get_overview",
            "suggest_next_up",
        },
        (False, False, True, False): {"rename_project", "delete_project", "request_thread_merge"},
        (False, False, False, False): {"resolve_project", "set_reminder"},
        (False, True, False, False): {
            "upsert_project",
            "pause_thread",
            "confirm_thread_relevant",
            "snooze_thread_triage",
            "report_guidance_health",
            "session_digest",
        },
        (False, True, False, True): {"upsert_thread", "upsert_progress", "mark_done"},
        (False, True, True, True): {"dismiss_thread"},
        (False, False, True, True): {"register_workspace"},
        (False, False, False, True): {"push_openclaw_memory"},
    }
    assert set().union(*profiles.values()) == PUBLIC_TOOLS
    for expected, names in profiles.items():
        for name in names:
            annotation = tools[name].annotations
            assert annotation is not None
            assert (
                annotation.read_only_hint,
                annotation.destructive_hint,
                annotation.idempotent_hint,
                annotation.open_world_hint,
            ) == expected, name


async def test_typed_outputs_preserve_dictionary_values_and_optional_keys(tmp_path, monkeypatch):
    from types import SimpleNamespace

    service = HubService(Settings(data_dir=tmp_path, auth_token="test"))
    server = build_mcp(service)
    # Future enrichments must survive validation, including nested integration details.
    raw = {
        "project_slug": "test",
        "progress_path": "test/PROGRESS.md",
        "thread_id": None,
        "created_thread": False,
        "needs_thread_selection": False,
        "forge": {"wiki": {"error": "offline", "future_key": 1}},
        "thread": None,
        "future_extension": {"enabled": True},
    }
    monkeypatch.setattr(service, "upsert_progress", lambda payload: raw)
    result = await server.call_tool(
        "upsert_progress", {"project_slug": "test", "content": "Decision"}
    )
    assert result.structured_content == raw
    assert "candidates" not in result.structured_content
    assert "error" not in result.structured_content

    digest = service.session_digest().model_dump(mode="json")
    digest["future_extension"] = "kept"
    monkeypatch.setattr(
        service, "session_digest", lambda **kwargs: SimpleNamespace(model_dump=lambda **kw: digest)
    )
    result = await server.call_tool("session_digest", {})
    assert result.structured_content == digest
