"""Opt-in AI scan-line client + cache behaviour."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx

from adhd_hub.ai_client import generate_ai_scan_line
from adhd_hub.clarity import SCAN_LINE_SOURCE_AI, SCAN_LINE_SOURCE_HEURISTIC
from adhd_hub.config import Settings
from adhd_hub.models import Thread, ThreadStatus, ThreadUpsert
from adhd_hub.service import HubService


def _thread(**kwargs) -> Thread:
    now = datetime.now(UTC)
    base = {
        "id": "t-ai",
        "summary": "Ship AI scan lines",
        "status": ThreadStatus.open,
        "project_slug": "demo",
        "focus": "Keep summaries calm",
        "created_at": now,
        "updated_at": now,
    }
    base.update(kwargs)
    return Thread(**base)


def test_generate_ai_scan_line_uses_openai_compatible_response(monkeypatch):
    settings = Settings(
        data_dir=Path("/tmp/unused"),
        auth_token="t",
        ai_base_url="http://127.0.0.1:11434/v1",
        ai_model="llama3.2",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Calm next step: wire opt-in AI scan lines"}}
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="http://127.0.0.1:11434") as client:
        # generate_ai_scan_line builds absolute URL; pass client without base conflict
        line = generate_ai_scan_line(settings, _thread(), client=client)
    assert line == "Calm next step: wire opt-in AI scan lines"


def test_generate_ai_scan_line_falls_back_on_error():
    settings = Settings(
        data_dir=Path("/tmp/unused"),
        auth_token="t",
        ai_base_url="http://127.0.0.1:9/v1",
        ai_timeout_seconds=0.05,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "nope"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        assert generate_ai_scan_line(settings, _thread(), client=client) is None


def test_disabled_without_base_url_uses_heuristic(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    thread = service.upsert_thread(
        ThreadUpsert(
            summary="Title",
            project_slug="demo",
            focus="Heuristic when AI off",
            source_tool="pytest",
        )
    )
    pub = service.thread_public_dict(thread)
    assert pub["scan_line"] == "Heuristic when AI off"
    assert pub["scan_line_source"] == SCAN_LINE_SOURCE_HEURISTIC


def test_ai_cache_used_when_fingerprint_matches(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="t",
        ai_base_url="http://ai.test/v1",
        ai_model="test",
    )
    service = HubService(settings)
    thread = service.upsert_thread(
        ThreadUpsert(
            summary="Title",
            project_slug="demo",
            focus="Original focus",
            source_tool="pytest",
        )
    )

    def fake_generate(settings_arg, thread_arg, *, client=None):
        return "AI rewritten calm scan line"

    monkeypatch.setattr("adhd_hub.ai_client.generate_ai_scan_line", fake_generate)
    service.refresh_scan_line_ai(thread)
    pub = service.thread_public_dict(thread)
    assert pub["scan_line"] == "AI rewritten calm scan line"
    assert pub["scan_line_source"] == SCAN_LINE_SOURCE_AI

    # Fingerprint change → heuristic until refresh
    monkeypatch.setattr(service, "refresh_scan_line_ai", lambda *a, **k: None)
    updated = service.upsert_thread(
        ThreadUpsert(
            id=thread.id,
            summary="Title",
            project_slug="demo",
            focus="Changed focus",
            source_tool="pytest",
        )
    )
    pub2 = service.thread_public_dict(updated)
    assert pub2["scan_line"] == "Changed focus"
    assert pub2["scan_line_source"] == SCAN_LINE_SOURCE_HEURISTIC
