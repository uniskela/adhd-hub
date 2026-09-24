"""Opt-in AI scan-line client + cache behaviour."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from adhd_hub.ai_client import (
    AiScanLineResult,
    generate_ai_scan_line,
    list_ai_models,
    normalize_openai_model_id,
)
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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("models/gemini-2.5-flash", "gemini-2.5-flash"),
        ("Models/gemini-3.8-flash", "gemini-3.8-flash"),
        ("gemini-2.5-flash", "gemini-2.5-flash"),
        ("  models/gemini-2.5-flash  ", "gemini-2.5-flash"),
        ("llama3.2", "llama3.2"),
        ("models/", "models/"),
        ("", ""),
    ],
)
def test_normalize_openai_model_id_strips_models_prefix(raw: str, expected: str) -> None:
    assert normalize_openai_model_id(raw) == expected


def test_list_ai_models_strips_gemini_models_prefix() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/v1beta/openai/models")
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "models/gemini-2.5-flash"},
                    {"id": "models/gemini-2.5-pro"},
                    {"id": "gemini-2.0-flash"},
                    {"id": "models/gemini-2.5-flash"},
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = list_ai_models(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key="sk-test",
            client=client,
        )
    assert result["ok"] is True
    assert result["models"] == [
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ]


def test_generate_ai_scan_line_strips_models_prefix_before_post():
    settings = Settings(
        data_dir=Path("/tmp/unused"),
        auth_token="t",
        ai_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        ai_model="models/gemini-2.5-flash",
    )
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["model"] = body.get("model")
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Calm next step: Gemini chat works"}}
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_ai_scan_line(settings, _thread(), client=client)
    assert seen["model"] == "gemini-2.5-flash"
    assert result.text == "Calm next step: Gemini chat works"
    assert result.fail_hint is None


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
        result = generate_ai_scan_line(settings, _thread(), client=client)
    assert result.text == "Calm next step: wire opt-in AI scan lines"
    assert result.fail_hint is None


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
        result = generate_ai_scan_line(settings, _thread(), client=client)
    assert result.text is None
    assert result.fail_hint is not None
    assert "500" in result.fail_hint
    assert "sk-" not in result.fail_hint


def test_generate_ai_scan_line_404_model_not_found_hint():
    settings = Settings(
        data_dir=Path("/tmp/unused"),
        auth_token="t",
        ai_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        ai_model="models/gemini-2.5-flash",
        ai_api_key="sk-secret-value",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"error": {"message": "model not found sk-secret-value"}}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_ai_scan_line(settings, _thread(), client=client)
    assert result.text is None
    assert result.fail_hint is not None
    assert "404" in result.fail_hint
    assert "models/" in result.fail_hint
    assert "sk-secret" not in result.fail_hint


def test_ai_request_scrubs_every_field_before_sending():
    settings = Settings(auth_token="t", ai_base_url="https://ai.example/v1")
    sensitive = "token=example-sensitive-value /home/private-work https://private.example"
    thread = _thread(
        summary=sensitive,
        focus=sensitive,
        goal=sensitive,
        resume_step=sensitive,
        next_steps=[sensitive],
        blocked_reason=sensitive,
        transcript_ref="transcript-marker",
        chat_ref="chat-marker",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompt = body["messages"][-1]["content"]
        for forbidden in (
            "example-sensitive-value",
            "/home/private-work",
            "https://private.example",
            "transcript-marker",
            "chat-marker",
        ):
            assert forbidden not in prompt
        assert "[redacted]" in prompt
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Safe step"}}]}
        )

    # Exceptions in the client are best-effort, so also assert the successful result.
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert generate_ai_scan_line(settings, thread, client=client).text == "Safe step"


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
    # Do not contact a real provider during the initial mutation.
    monkeypatch.setattr(
        "adhd_hub.ai_client.generate_ai_scan_line",
        lambda *a, **k: AiScanLineResult(),
    )
    thread = service.upsert_thread(
        ThreadUpsert(
            summary="Title",
            project_slug="demo",
            focus="Original focus",
            source_tool="pytest",
        )
    )

    def fake_generate(settings_arg, thread_arg, *, client=None):
        return AiScanLineResult(text="AI rewritten calm scan line")

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


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), 31])
def test_ai_timeout_is_positive_and_bounded(timeout):
    with pytest.raises(ValidationError):
        Settings(ai_timeout_seconds=timeout)


def test_disabling_ai_ignores_old_cached_rewrites(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "adhd_hub.ai_client.generate_ai_scan_line",
        lambda *a, **k: AiScanLineResult(text="AI line"),
    )
    service = HubService(
        Settings(data_dir=tmp_path, auth_token="t", ai_base_url="https://ai.test")
    )
    thread = service.upsert_thread(ThreadUpsert(summary="Title", focus="Local step"))
    assert service.thread_public_dict(thread)["scan_line"] == "AI line"
    service.settings.ai_base_url = None
    assert service.thread_public_dict(thread)["scan_line"] == "Local step"


def test_ai_config_strips_models_prefix_on_save() -> None:
    from adhd_hub.ai_config import AiConfig

    cfg = AiConfig(
        enabled=True,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="models/gemini-2.5-flash",
    )
    assert cfg.model == "gemini-2.5-flash"


def test_rewrite_scan_line_surfaces_404_hint(tmp_path: Path, monkeypatch) -> None:
    service = HubService(
        Settings(
            data_dir=tmp_path / "data",
            auth_token="t",
            ai_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            ai_model="models/gemini-2.5-flash",
        )
    )
    monkeypatch.setattr(
        "adhd_hub.ai_client.generate_ai_scan_line",
        lambda *a, **k: AiScanLineResult(
            fail_hint=(
                "Model not found (404) — check the model id "
                "(use gemini-… without a models/ prefix)."
            )
        ),
    )
    thread = service.upsert_thread(
        ThreadUpsert(summary="Title", focus="Heuristic focus", source_tool="pytest")
    )
    out = service.rewrite_scan_line(thread.id)
    assert out["ai_attempted"] is True
    assert "404" in out["message"]
    assert "models/" in out["message"]
    assert out["thread"]["scan_line"] == "Heuristic focus"
    assert out["thread"]["scan_line_source"] == SCAN_LINE_SOURCE_HEURISTIC
