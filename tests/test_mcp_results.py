"""Output schemas preserve service JSON, including branch omissions and extras."""

from datetime import datetime

import pytest
from pydantic import TypeAdapter

from adhd_hub.config import Settings
from adhd_hub.mcp_results import (
    GuidanceHealthResult,
    ProgressResult,
    ProjectResult,
    SessionDigestResult,
    ThreadResult,
)
from adhd_hub.models import ProgressUpsert, Project, Reminder, SessionDigest, Thread, ThreadUpsert
from adhd_hub.service import HubService


def assert_wire_preserved(result_type, payload):
    adapter = TypeAdapter(result_type)
    assert adapter.dump_python(adapter.validate_python(payload), mode="json") == payload
    # Service enrichments and additive future fields must survive the SDK adapter.
    enriched = payload | {"future_field": {"values": [None, "unchanged"]}}
    assert adapter.dump_python(adapter.validate_python(enriched), mode="json") == enriched


def test_session_and_thread_models_preserve_enrichment_nulls_and_timestamps():
    stamp = datetime.fromisoformat("2026-01-02T03:04:05.123456+02:00")
    thread = Thread(
        id="thread",
        summary="Publish schema PR",
        goal="Open PR",
        resume_step="Run tests/test_mcp.py",
        created_at=stamp,
        updated_at=stamp,
    )
    reminder = Reminder(id="reminder", message="Review PR", created_at=stamp)
    digest = SessionDigest(
        open_count=1, stale_count=0, items=[thread], due_reminders=[reminder], guidance=None
    ).model_dump(mode="json")
    digest["items"][0]["completion"]["future_evidence"] = "retained"
    digest["items"][0]["return_cue"]["future_signal"] = "retained"
    assert_wire_preserved(SessionDigestResult, digest)
    assert digest["items"][0]["created_at"] == "2026-01-02T03:04:05.123456+02:00"
    assert digest["due_reminders"][0]["due_at"] is None
    assert_wire_preserved(ThreadResult, thread.model_dump(mode="json"))
    project = Project(slug="schema", title="Schema", created_at=stamp, updated_at=stamp)
    assert_wire_preserved(ProjectResult, project.model_dump(mode="json"))


def test_service_progress_branches_and_guidance_record_keep_wire_shape(tmp_path):
    service = HubService(Settings(data_dir=tmp_path, auth_token="test"))
    saved = service.upsert_progress(
        ProgressUpsert(project_slug="schema", title="Schema quality", goal="Open schema PR")
    )
    assert saved["created_thread"] is True
    assert "candidates" not in saved
    assert saved["thread"]["completion"]["ready"] is True
    assert saved["thread"]["updated_at"].endswith("Z")
    assert_wire_preserved(ProgressResult, saved)

    notes_only = service.upsert_progress(
        ProgressUpsert(
            project_slug="schema", content="Document a decision", create_thread_if_missing=False
        )
    )
    assert notes_only["thread"] is None
    assert notes_only["thread_id"] is None
    assert_wire_preserved(ProgressResult, notes_only)

    service.upsert_thread(
        ThreadUpsert(summary="Unrelated finishable outcome", project_slug="schema")
    )
    selection = service.upsert_progress(ProgressUpsert(project_slug="schema", content="Checkpoint"))
    assert selection["needs_thread_selection"] is True
    assert "created_thread" not in selection
    assert "thread" not in selection
    assert len(selection["candidates"]) == 2
    assert_wire_preserved(ProgressResult, selection)

    guidance = service.record_guidance_verification(project_slug="schema", agent_guidance_version=7)
    assert isinstance(guidance["guidance"], str)
    assert_wire_preserved(GuidanceHealthResult, guidance)
    assert_wire_preserved(SessionDigestResult, service.session_digest().model_dump(mode="json"))


@pytest.mark.parametrize(
    ("result_type", "payload"),
    [
        (ProjectResult, {"error": "not_found"}),
        (ProgressResult, {"error": "project_slug or workspace_path required"}),
        (ProgressResult, {"error": "not_found", "detail": "thread not found: missing"}),
        (ThreadResult, {"error": "not_found", "id": "missing"}),
        (ThreadResult, {"error": "thread paused", "id": "unfinished"}),
        (GuidanceHealthResult, {"error": "project_slug or workspace_path required"}),
    ],
)
def test_error_envelopes_do_not_gain_success_fields(result_type, payload):
    assert_wire_preserved(result_type, payload)
