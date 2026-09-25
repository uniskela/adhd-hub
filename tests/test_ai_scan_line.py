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
    is_likely_chat_model,
    list_ai_models,
    normalize_openai_model_id,
    openai_compat_url,
    structured_scan_prompt,
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
        ("google/gemini-2.5-flash", "gemini-2.5-flash"),
        ("models/google/gemini-2.5-pro", "gemini-2.5-pro"),
        ("llama3.2", "llama3.2"),
        ("models/", "models/"),
        ("", ""),
    ],
)
def test_normalize_openai_model_id_strips_models_prefix(raw: str, expected: str) -> None:
    assert normalize_openai_model_id(raw) == expected


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("gemini-2.5-flash", True),
        ("gemini-2.5-pro", True),
        ("llama3.2", True),
        ("mistral", True),
        ("text-embedding-004", False),
        ("models/gemini-embedding-001", False),
        ("imagen-3.0-generate-002", False),
        ("gemini-2.5-flash-image", False),
        ("gemini-2.5-flash-preview-tts", False),
    ],
)
def test_is_likely_chat_model(model_id: str, expected: bool) -> None:
    assert is_likely_chat_model(model_id) is expected


@pytest.mark.parametrize(
    ("base", "suffix", "expected"),
    [
        (
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            "chat/completions",
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        ),
        (
            "https://generativelanguage.googleapis.com/v1beta/openai",
            "/chat/completions",
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        ),
        (
            "https://generativelanguage.googleapis.com/v1beta/openai//",
            "models",
            "https://generativelanguage.googleapis.com/v1beta/openai/models",
        ),
        ("http://127.0.0.1:11434/v1", "chat/completions", "http://127.0.0.1:11434/v1/chat/completions"),
    ],
)
def test_openai_compat_url_avoids_double_slash(base: str, suffix: str, expected: str) -> None:
    assert openai_compat_url(base, suffix) == expected


def test_structured_scan_prompt_caps_fields_and_skips_forge_conflict_walls() -> None:
    forge_wall = (
        "Thread upserted from Cursor — Title — Desc — more ritual\n"
        + ("forge conflict dump line\n" * 80)
        + ("x" * 2000)
    )
    thread = _thread(
        focus="Keep AI prompts small enough to finish under the timeout",
        resume_step=forge_wall,
        goal="Ship scan-line quality without provider timeouts",
        next_steps=["Cap prompt fields", "Reject short AI", "Ignore forge walls"],
        source_conflicts={
            "resume_step": {
                "previous": "older hub resume",
                "hub": "Run focused pytest for scan-line prompt caps",
                "forge": forge_wall,
            }
        },
    )
    prompt = structured_scan_prompt(thread)
    assert "Run focused pytest for scan-line prompt caps" in prompt
    assert "Thread upserted from" not in prompt
    assert "forge conflict dump" not in prompt
    assert forge_wall[:40] not in prompt
    assert "source_conflicts" not in prompt
    resume_line = next(line for line in prompt.splitlines() if line.startswith("Resume:"))
    assert len(resume_line) <= len("Resume: ") + 120 + 1  # truncate may add …
    assert len(prompt) < 1200


def test_structured_scan_prompt_drops_ritual_resume_without_feeding_wall() -> None:
    ritual = "Thread upserted from Codex — Ship AI — " + ("wall " * 400)
    thread = _thread(resume_step=ritual, focus="Prefer short hub focus when resume is ritual")
    prompt = structured_scan_prompt(thread)
    assert "Thread upserted from" not in prompt
    assert "Prefer short hub focus" in prompt
    assert "Resume:" not in prompt


def test_generate_ai_scan_line_sends_capped_prompt_not_forge_blob() -> None:
    settings = Settings(
        data_dir=Path("/tmp/unused"),
        auth_token="t",
        ai_base_url="http://127.0.0.1:11434/v1",
    )
    forge_wall = "Thread upserted from Cursor\n" + ("conflict resume blob\n" * 100)
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompt = body["messages"][-1]["content"]
        seen["prompt"] = prompt
        assert "conflict resume blob" not in prompt
        assert len(prompt) < 1200
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Keep rewriting calm ADHD-friendly scan lines for My work cards"
                            )
                        }
                    }
                ]
            },
        )

    thread = _thread(
        focus="Keep rewriting calm ADHD-friendly scan lines",
        resume_step=forge_wall,
        source_conflicts={
            "resume_step": {
                "hub": "Finish prompt caps then re-test rewrite",
                "forge": forge_wall,
            }
        },
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_ai_scan_line(settings, thread, client=client)
    assert result.text is not None
    assert "Finish prompt caps" in seen["prompt"]


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
                    {"id": "models/gemini-3.6-flash"},
                    {"id": "models/gemini-2.5-flash"},
                    {"id": "models/text-embedding-004"},
                    {"id": "models/imagen-3.0-generate-002"},
                    {"id": "gemini-2.5-flash-image"},
                    {
                        "id": "models/gemini-exp-dead",
                        "description": "no longer available to new users",
                    },
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
        "gemini-2.5-pro",
        "gemini-3.6-flash",
    ]
    assert "hid 3 non-chat" in result["message"]
    assert "deprecated-for-new-users" in result["message"]
    assert "gemini-3.6-flash" in result["message"]


def test_generate_ai_scan_line_rejects_short_stub():
    settings = Settings(
        data_dir=Path("/tmp/unused"),
        auth_token="t",
        ai_base_url="http://127.0.0.1:11434/v1",
        ai_model="llama3.2",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["max_tokens"] >= 200
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Run"}}]}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_ai_scan_line(
            settings,
            _thread(focus="Keep rewriting calm ADHD-friendly scan lines"),
            client=client,
        )
    assert result.text is None
    assert result.fail_hint is not None
    assert "too short" in result.fail_hint


def test_generate_ai_scan_line_prefers_heuristic_when_ai_much_shorter():
    settings = Settings(
        data_dir=Path("/tmp/unused"),
        auth_token="t",
        ai_base_url="http://127.0.0.1:11434/v1",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Ship the next calm rewrite now please"}}
                ]
            },
        )

    # AI is long enough on its own, but much shorter than the heuristic focus —
    # wait: "Ship the next calm rewrite now please" is ~38 chars; heuristic needs
    # to be > 76 chars for 2x rule. Use a long focus.
    focus = (
        "Finish the AI scan-line quality gate so short stubs never replace a full "
        "heuristic resume step on My work cards"
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_ai_scan_line(
            settings, _thread(focus=focus), client=client
        )
    assert result.text is None
    assert result.fail_hint is not None
    assert "too short" in result.fail_hint


def test_generate_ai_scan_line_accepts_good_complete_line():
    settings = Settings(
        data_dir=Path("/tmp/unused"),
        auth_token="t",
        ai_base_url="http://127.0.0.1:11434/v1",
    )
    good = "Keep rewriting calm ADHD-friendly scan lines for My work cards"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": good}}]}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_ai_scan_line(
            settings, _thread(focus="Keep summaries calm"), client=client
        )
    assert result.text == good
    assert result.fail_hint is None


def test_generate_ai_scan_line_rejects_incomplete_mid_phrase():
    settings = Settings(
        data_dir=Path("/tmp/unused"),
        auth_token="t",
        ai_base_url="http://127.0.0.1:11434/v1",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Draft the pull request ready to"}}
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_ai_scan_line(settings, _thread(), client=client)
    assert result.text is None
    assert result.fail_hint is not None
    assert "incomplete" in result.fail_hint


def test_generate_ai_scan_line_strips_models_prefix_before_post():
    settings = Settings(
        data_dir=Path("/tmp/unused"),
        auth_token="t",
        ai_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ai_model="models/gemini-2.5-flash",
        ai_api_key="sk-test",
    )
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["model"] = body.get("model")
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        assert request.url.path == "/v1beta/openai/chat/completions"
        assert body["model"] == "gemini-2.5-flash"
        assert set(body) >= {"model", "messages", "temperature", "max_tokens"}
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
    assert seen["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )
    assert seen["auth"] == "Bearer sk-test"
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


def test_generate_ai_scan_line_timeout_hint():
    settings = Settings(
        data_dir=Path("/tmp/unused"),
        auth_token="t",
        ai_base_url="http://127.0.0.1:9/v1",
        ai_timeout_seconds=1.0,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_ai_scan_line(settings, _thread(), client=client)
    assert result.text is None
    assert result.fail_hint is not None
    assert "timed out" in result.fail_hint.lower()
    assert "Timeout" in result.fail_hint
    assert "heuristic" in result.fail_hint.lower()


def test_default_ai_timeout_is_fifteen_seconds():
    from adhd_hub.ai_config import DEFAULT_AI_TIMEOUT, MAX_AI_TIMEOUT, AiConfig
    from adhd_hub.config import Settings

    assert DEFAULT_AI_TIMEOUT == 15.0
    assert MAX_AI_TIMEOUT == 30.0
    assert Settings().ai_timeout_seconds == 15.0
    assert AiConfig().timeout_seconds == 15.0


def test_generate_ai_scan_line_404_bare_model_hint_does_not_blame_prefix():
    settings = Settings(
        data_dir=Path("/tmp/unused"),
        auth_token="t",
        ai_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        ai_model="gemini-2.5-flash",
        ai_api_key="sk-secret-value",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "error": {
                    "message": (
                        "This model models/gemini-2.5-flash is no longer available. "
                        "Please update your code to use models/gemini-3.6-flash. "
                        "key=sk-secret-value"
                    )
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_ai_scan_line(settings, _thread(), client=client)
    assert result.text is None
    assert result.fail_hint is not None
    assert "no longer available" in result.fail_hint
    assert "gemini-3.6-flash" in result.fail_hint
    assert "without a models/ prefix" not in result.fail_hint
    assert "Provider:" in result.fail_hint
    assert "sk-secret" not in result.fail_hint


def test_generate_ai_scan_line_404_generic_mentions_current_flash():
    settings = Settings(
        data_dir=Path("/tmp/unused"),
        auth_token="t",
        ai_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        ai_model="gemini-3.6-flash",
        ai_api_key="sk-secret-value",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "model not found"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_ai_scan_line(settings, _thread(), client=client)
    assert result.fail_hint is not None
    assert "404" in result.fail_hint
    assert "gemini-3.6-flash" in result.fail_hint
    assert "v1beta/openai" in result.fail_hint
    assert "sk-secret" not in result.fail_hint


def test_generate_ai_scan_line_404_mentions_prefix_only_when_still_present():
    settings = Settings(
        data_dir=Path("/tmp/unused"),
        auth_token="t",
        # Bypass AiConfig validator so we can assert the rare still-prefixed path.
        ai_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        ai_model="models/",
        ai_api_key="sk-secret-value",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "models/"
        return httpx.Response(404, json={"error": {"message": "not found"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_ai_scan_line(settings, _thread(), client=client)
    assert result.fail_hint is not None
    assert "models/ prefix" in result.fail_hint
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
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "Safe next step after scrubbing sensitive fields"
                        }
                    }
                ]
            },
        )

    # Exceptions in the client are best-effort, so also assert the successful result.
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert (
            generate_ai_scan_line(settings, thread, client=client).text
            == "Safe next step after scrubbing sensitive fields"
        )


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
    from adhd_hub.ai_config import AiConfig

    service.save_ai_config(
        AiConfig(
            enabled=True,
            base_url="https://ai.test",
            auto_review_scan_lines=True,
        )
    )
    thread = service.upsert_thread(ThreadUpsert(summary="Title", focus="Local step"))
    assert service.thread_public_dict(thread)["scan_line"] == "AI line"
    service.settings.ai_base_url = None
    assert service.thread_public_dict(thread)["scan_line"] == "Local step"


def test_auto_review_off_skips_provider_on_upsert(tmp_path: Path, monkeypatch):
    calls = {"n": 0}

    def fake_generate(*a, **k):
        calls["n"] += 1
        return AiScanLineResult(text="Should not run")

    monkeypatch.setattr("adhd_hub.ai_client.generate_ai_scan_line", fake_generate)
    service = HubService(
        Settings(data_dir=tmp_path / "data", auth_token="t", ai_base_url="https://ai.test")
    )
    # Env URL enables AI, but auto review defaults off.
    thread = service.upsert_thread(
        ThreadUpsert(summary="Title", focus="Heuristic focus", source_tool="pytest")
    )
    assert calls["n"] == 0
    pub = service.thread_public_dict(thread)
    assert pub["scan_line"] == "Heuristic focus"
    assert pub["scan_line_source"] == SCAN_LINE_SOURCE_HEURISTIC
    assert pub["scan_line_needs_ai"] is False


def test_scan_line_ensure_skips_when_hash_matches(tmp_path: Path, monkeypatch):
    calls = {"n": 0}

    def fake_generate(*a, **k):
        calls["n"] += 1
        return AiScanLineResult(text="AI calm scan line for ensure")

    monkeypatch.setattr("adhd_hub.ai_client.generate_ai_scan_line", fake_generate)
    service = HubService(
        Settings(data_dir=tmp_path / "data", auth_token="t", ai_base_url="https://ai.test")
    )
    from adhd_hub.ai_config import AiConfig

    service.save_ai_config(
        AiConfig(
            enabled=True,
            base_url="https://ai.test",
            auto_review_scan_lines=True,
        )
    )
    thread = service.upsert_thread(
        ThreadUpsert(summary="Title", focus="Ensure focus", source_tool="pytest")
    )
    assert calls["n"] == 1
    out = service.rewrite_scan_line(thread.id, force=False)
    assert out["skipped"] is True
    assert out["ai_attempted"] is False
    assert calls["n"] == 1
    # Drift → ensure calls provider again.
    updated = service.upsert_thread(
        ThreadUpsert(
            id=thread.id,
            summary="Title",
            project_slug=thread.project_slug,
            focus="Changed focus",
            source_tool="pytest",
        )
    )
    assert calls["n"] == 2
    out2 = service.rewrite_scan_line(updated.id, force=False)
    assert out2["skipped"] is True
    assert calls["n"] == 2


def test_scan_line_input_hash_stable_and_ignores_status() -> None:
    from adhd_hub.ai_client import scan_line_input_hash
    from adhd_hub.models import Thread, ThreadStatus
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    a = Thread(
        id="t1",
        summary="Title",
        status=ThreadStatus.open,
        focus="F",
        goal="G",
        next_steps=["N"],
        blocked_reason=None,
        resume_step="R",
        created_at=now,
        updated_at=now,
    )
    b = Thread(
        id="t1",
        summary="Title",
        status=ThreadStatus.blocked,
        focus="F",
        goal="G",
        next_steps=["N"],
        blocked_reason=None,
        resume_step="R",
        created_at=now,
        updated_at=now,
    )
    assert scan_line_input_hash(a) == scan_line_input_hash(b)
    c = a.model_copy(update={"focus": "Other"})
    assert scan_line_input_hash(a) != scan_line_input_hash(c)


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
            ai_model="gemini-2.5-flash",
        )
    )
    monkeypatch.setattr(
        "adhd_hub.ai_client.generate_ai_scan_line",
        lambda *a, **k: AiScanLineResult(
            fail_hint=(
                "Chat returned 404 for model 'gemini-2.5-flash' at "
                "generativelanguage.googleapis.com/v1beta/openai/chat/completions. "
                "Confirm the base URL ends at …/v1beta/openai (Gemini) or your "
                "provider’s OpenAI-compat root, the model supports chat, and AI "
                "settings were saved."
            )
        ),
    )
    thread = service.upsert_thread(
        ThreadUpsert(summary="Title", focus="Heuristic focus", source_tool="pytest")
    )
    out = service.rewrite_scan_line(thread.id)
    assert out["ai_attempted"] is True
    assert "404" in out["message"]
    assert "gemini-2.5-flash" in out["message"]
    assert "without a models/ prefix" not in out["message"]
    assert out["thread"]["scan_line"] == "Heuristic focus"
    assert out["thread"]["scan_line_source"] == SCAN_LINE_SOURCE_HEURISTIC
