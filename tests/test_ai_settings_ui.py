"""AI config persistence + manual scan-line rewrite API."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from adhd_hub.ai_client import ai_configured
from adhd_hub.ai_config import AiConfig, ai_from_settings, load_ai_config, save_ai_config
from adhd_hub.clarity import SCAN_LINE_SOURCE_AI, SCAN_LINE_SOURCE_HEURISTIC
from adhd_hub.config import Settings
from adhd_hub.models import ThreadUpsert
from adhd_hub.service import HubService


def test_ai_from_settings_opts_in_when_env_url_set(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        auth_token="secret-token",
        ai_base_url="http://127.0.0.1:11434/v1",
        ai_model="llama3.2",
    )
    cfg = ai_from_settings(settings)
    assert cfg.enabled is True
    assert cfg.base_url == "http://127.0.0.1:11434/v1"
    assert cfg.is_active()


def test_ai_configured_requires_enabled_and_url(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_token="t", ai_base_url="http://ai.test/v1")
    settings.ai_enabled = False
    assert ai_configured(settings) is False
    settings.ai_enabled = True
    assert ai_configured(settings) is True
    settings.ai_base_url = None
    assert ai_configured(settings) is False


def test_ai_config_roundtrip_encrypts_api_key(tmp_path: Path) -> None:
    auth = "hub-auth-token-value"
    cfg = AiConfig(
        enabled=True,
        base_url="http://127.0.0.1:11434/v1",
        model="llama3.2",
        api_key="sk-test-secret",
        timeout_seconds=2.0,
    )
    save_ai_config(tmp_path, cfg, auth_token=auth)
    raw = (tmp_path / "ai.json").read_text(encoding="utf-8")
    assert "sk-test-secret" not in raw
    assert "api_key_encrypted" in raw
    loaded = load_ai_config(
        tmp_path,
        env_defaults=AiConfig(),
        auth_token=auth,
    )
    assert loaded.api_key == "sk-test-secret"
    assert loaded.public_dict()["api_key_configured"] is True
    assert "api_key" not in loaded.public_dict()


def test_hubservice_applies_saved_ai_config(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", auth_token="t")
    service = HubService(settings)
    assert service.ai_config().is_active() is False
    saved = service.save_ai_config(
        AiConfig(
            enabled=True,
            base_url="http://127.0.0.1:11434/v1",
            model="mistral",
            api_key="k",
        )
    )
    assert saved.is_active()
    assert service.settings.ai_enabled is True
    assert service.settings.ai_base_url == "http://127.0.0.1:11434/v1"
    assert service.settings.ai_model == "mistral"
    assert service.settings.ai_api_key == "k"
    # Reload from disk
    again = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    assert again.ai_config().api_key == "k"
    assert again.ai_config().model == "mistral"


def test_rewrite_scan_line_falls_back_when_ai_off(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    thread = service.upsert_thread(
        ThreadUpsert(summary="Title", focus="Stay calm", source_tool="pytest")
    )
    out = service.rewrite_scan_line(thread.id)
    assert out["ai_attempted"] is False
    assert out["thread"]["scan_line"] == "Stay calm"
    assert out["thread"]["scan_line_source"] == SCAN_LINE_SOURCE_HEURISTIC


def test_rewrite_scan_line_force_writes_ai_cache(tmp_path: Path, monkeypatch) -> None:
    service = HubService(
        Settings(
            data_dir=tmp_path / "data",
            auth_token="t",
            ai_base_url="http://ai.test/v1",
        )
    )
    monkeypatch.setattr(
        "adhd_hub.ai_client.generate_ai_scan_line",
        lambda *a, **k: "AI calm rewrite",
    )
    thread = service.upsert_thread(
        ThreadUpsert(summary="Title", focus="Original", source_tool="pytest")
    )
    out = service.rewrite_scan_line(thread.id)
    assert out["ai_attempted"] is True
    assert out["thread"]["scan_line"] == "AI calm rewrite"
    assert out["thread"]["scan_line_source"] == SCAN_LINE_SOURCE_AI


def test_rewrite_scan_line_clears_cache_on_provider_failure(
    tmp_path: Path, monkeypatch
) -> None:
    service = HubService(
        Settings(
            data_dir=tmp_path / "data",
            auth_token="t",
            ai_base_url="http://ai.test/v1",
        )
    )
    monkeypatch.setattr(
        "adhd_hub.ai_client.generate_ai_scan_line",
        lambda *a, **k: "Cached AI line",
    )
    thread = service.upsert_thread(
        ThreadUpsert(summary="Title", focus="Heuristic focus", source_tool="pytest")
    )
    assert service.thread_public_dict(thread)["scan_line"] == "Cached AI line"
    monkeypatch.setattr(
        "adhd_hub.ai_client.generate_ai_scan_line", lambda *a, **k: None
    )
    out = service.rewrite_scan_line(thread.id)
    assert out["ai_attempted"] is True
    assert "heuristic" in out["message"].lower()
    assert out["thread"]["scan_line"] == "Heuristic focus"
    assert out["thread"]["scan_line_source"] == SCAN_LINE_SOURCE_HEURISTIC


def test_ai_config_api_and_scan_line_route(tmp_path: Path, monkeypatch) -> None:
    from adhd_hub.app import create_app

    settings = Settings(data_dir=tmp_path / "data", auth_token="test-token")
    app = create_app(settings)
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}

    empty = client.get("/api/ai/config", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["active"] is False
    assert empty.json()["api_key_configured"] is False

    saved = client.put(
        "/api/ai/config",
        headers=headers,
        json={
            "enabled": True,
            "base_url": "http://127.0.0.1:11434/v1",
            "model": "llama3.2",
            "api_key": "secret-key",
            "timeout_seconds": 3,
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["active"] is True
    assert body["api_key_configured"] is True
    assert "api_key" not in body

    # Blank api_key keeps existing
    kept = client.put(
        "/api/ai/config",
        headers=headers,
        json={
            "enabled": True,
            "base_url": "http://127.0.0.1:11434/v1",
            "model": "llama3.2",
            "timeout_seconds": 3,
        },
    )
    assert kept.json()["api_key_configured"] is True

    # Enable without URL rejected
    bad = client.put(
        "/api/ai/config",
        headers=headers,
        json={"enabled": True, "base_url": ""},
    )
    assert bad.status_code == 400

    monkeypatch.setattr(
        "adhd_hub.ai_client.generate_ai_scan_line",
        lambda *a, **k: "From API rewrite",
    )
    hub: HubService = app.state.service
    thread = hub.upsert_thread(
        ThreadUpsert(summary="API thread", focus="Focus text", source_tool="pytest")
    )
    resp = client.post(
        f"/api/threads/{thread.id}/scan-line",
        headers=headers,
        json={},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["thread"]["scan_line"] == "From API rewrite"
    assert payload["ai_attempted"] is True


def test_ui_exposes_ai_settings_and_rewrite_control() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    index = (root / "src/adhd_hub/ui/index.html").read_text(encoding="utf-8")
    assert 'id="ai_enabled"' in index
    assert 'id="btn-save-ai"' in index
    assert 'id="btn-load-ai-models"' in index
    assert 'id="ai_base_url_preset"' in index
    assert 'id="ai_base_url_list"' in index
    assert "https://api.openai.com/v1" in index
    assert "https://generativelanguage.googleapis.com/v1beta/openai/" in index
    assert "http://127.0.0.1:11434/v1" in index
    assert '<select id="ai_model">' in index
    assert 'list="ai_base_url_list"' in index
    assert 'id="ai_timeout"' in index
    assert 'value="15"' in index
    assert 'min="1"' in index
    assert 'max="30"' in index
    assert 'id="btn-rewrite-all-scan"' in index
    assert 'id="btn-rewrite-all-scan-mobile"' in index
    assert "Rewrite all scan lines" in index
    work = (root / "src/adhd_hub/ui/js/work.js").read_text(encoding="utf-8")
    assert "data-rewrite-scan" in work
    assert "Rewrite scan line" in work
    assert "rewriteAllProjectScanLines" in work
    assert "/projects/" in work and "scan-lines" in work
    assert "Are you sure?" in work
    assert "rewrite-scan-lines" in work
    assert "This may take a moment." in work
    assert "(0/${" not in work
    assert "sticky: true" in work
    assert "refreshSiblingTabCounts" in work
    state = (root / "src/adhd_hub/ui/js/state.js").read_text(encoding="utf-8")
    assert "_toastApplyTimer" in state
    assert "opts.sticky" in state
    css = (root / "src/adhd_hub/ui/app.css").read_text(encoding="utf-8")
    assert "text-overflow: ellipsis" in css
    assert ".thread-scan" in css
    assert "line-clamp: 2" in css
    assert "-webkit-line-clamp: 2" in css
    for chunk in css.split(".thread-scan"):
        block = chunk.split("}", 1)[0]
        assert "white-space: nowrap" not in block
    settings = (root / "src/adhd_hub/ui/js/settings.js").read_text(encoding="utf-8")
    assert "loadAiConfig" in settings
    assert "/ai/config" in settings
    assert "testAndLoadAiModels" in settings
    assert "/ai/models" in settings
    assert "fillAiModelList" in settings
    assert "AI_BASE_URL_PRESETS" in settings
    assert "syncAiBaseUrlPreset" in settings
    assert "applyAiBaseUrlPreset" in settings
    assert "normalizeAiBaseUrl" in settings
    assert "matchAiBaseUrlPreset" in settings
    assert "never a stale preset" in settings or "URL field is source of truth" in settings
    assert "do not wipe a typed custom URL" in settings
    assert "(saved)" in settings
    assert "fromSelect" not in settings
    assert 'const sel = $("ai_model")' in settings
    boot = (root / "src/adhd_hub/ui/js/boot.js").read_text(encoding="utf-8")
    assert "rewriteAllProjectScanLines" in boot
    assert "btn-rewrite-all-scan" in boot
    assert "btn-rewrite-all-scan-mobile" in boot
    assert "btn-load-ai-models" in boot
    assert "testAndLoadAiModels" in boot
    assert "applyAiBaseUrlPreset" in boot
    assert "syncAiBaseUrlPreset" in boot
    assert "ai_base_url_preset" in boot


def test_ai_base_url_preset_match_logic_in_settings_js() -> None:
    """Preset restore: exact-after-normalize match; unknown → Custom (empty)."""
    from pathlib import Path

    settings = (
        Path(__file__).resolve().parents[1] / "src/adhd_hub/ui/js/settings.js"
    ).read_text(encoding="utf-8")
    # Gemini preset has trailing slash; AiConfig persists without — must still match.
    assert "normalizeAiBaseUrl" in settings
    assert "replace(/\\/+$/, \"\")" in settings or "replace(/\\/+$/," in settings
    assert "matchAiBaseUrlPreset" in settings
    assert "AI_BASE_URL_PRESETS.find" in settings
    # Custom leaves typed URL alone
    assert "do not wipe a typed custom URL" in settings
    # Save / Test use field, not preset select
    assert 'base_url: $("ai_base_url")?.value.trim()' in settings
    assert 'base_url: baseUrl' in settings
    assert "ai_base_url_preset" not in settings.split("aiConfigPayload")[1].split(
        "export async function saveAiConfig"
    )[0]


def test_list_ai_models_parses_openai_compatible_payload() -> None:
    from adhd_hub.ai_client import list_ai_models

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url).endswith("/v1/models")
        assert request.headers.get("Authorization") == "Bearer sk-test"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "llama3.2"},
                    {"id": "mistral"},
                    {"id": "llama3.2"},
                    {"id": "models/gemini-3.6-flash"},
                    {"id": "models/gemini-2.5-flash"},
                    {"object": "model"},
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = list_ai_models(
            base_url="http://127.0.0.1:11434/v1",
            api_key="sk-test",
            client=client,
        )
    assert result["ok"] is True
    assert result["models"] == ["gemini-3.6-flash", "llama3.2", "mistral"]
    assert "3 models" in result["message"]
    assert "deprecated-for-new-users" in result["message"]


def test_list_ai_models_calm_failure_without_secrets() -> None:
    from adhd_hub.ai_client import list_ai_models

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_api_key sk-leaked"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = list_ai_models(
            base_url="http://ai.test/v1",
            api_key="sk-secret-value",
            client=client,
        )
    assert result["ok"] is False
    assert result["models"] == []
    assert "sk-secret" not in result["message"]
    assert "Could not load models" in result["message"]


def test_ai_models_api_route(tmp_path: Path, monkeypatch) -> None:
    from adhd_hub.app import create_app

    settings = Settings(data_dir=tmp_path / "data", auth_token="test-token")
    app = create_app(settings)
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}

    missing = client.post("/api/ai/models", headers=headers, json={})
    assert missing.status_code == 400

    saved = client.put(
        "/api/ai/config",
        headers=headers,
        json={
            "enabled": True,
            "base_url": "http://127.0.0.1:11434/v1",
            "model": "llama3.2",
            "api_key": "saved-secret",
            "timeout_seconds": 3,
        },
    )
    assert saved.status_code == 200

    monkeypatch.setattr(
        "adhd_hub.ai_client.list_ai_models",
        lambda **kwargs: (
            {
                "ok": True,
                "models": ["llama3.2", "mistral"],
                "message": "Connected · 2 models",
            }
            if kwargs.get("api_key") == "saved-secret"
            and kwargs.get("base_url") == "http://127.0.0.1:11434/v1"
            else {"ok": False, "models": [], "message": "bad key"}
        ),
    )
    ok = client.post("/api/ai/models", headers=headers, json={})
    assert ok.status_code == 200
    assert ok.json()["models"] == ["llama3.2", "mistral"]

    # Draft URL change must not reuse the saved key for a new host.
    seen: dict[str, str] = {}

    def capture(**kwargs):
        seen["api_key"] = kwargs.get("api_key") or ""
        seen["base_url"] = kwargs.get("base_url") or ""
        return {
            "ok": True,
            "models": ["other"],
            "message": "Connected · 1 model",
        }

    monkeypatch.setattr("adhd_hub.ai_client.list_ai_models", capture)
    draft = client.post(
        "/api/ai/models",
        headers=headers,
        json={"base_url": "http://other.ai/v1"},
    )
    assert draft.status_code == 200
    assert seen["base_url"] == "http://other.ai/v1"
    assert seen["api_key"] == ""

    monkeypatch.setattr(
        "adhd_hub.ai_client.list_ai_models",
        lambda **kwargs: {
            "ok": False,
            "models": [],
            "message": "Could not load models from that base URL.",
        },
    )
    failed = client.post(
        "/api/ai/models",
        headers=headers,
        json={"base_url": "http://127.0.0.1:11434/v1"},
    )
    assert failed.status_code == 502
    assert "Could not load models" in failed.json()["detail"]
    assert "saved-secret" not in failed.text


def test_rewrite_project_scan_lines_noops_when_ai_off(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_thread(
        ThreadUpsert(
            summary="A",
            focus="Focus A",
            project_slug="batch-proj",
            source_tool="pytest",
        )
    )
    service.upsert_thread(
        ThreadUpsert(
            summary="B",
            focus="Focus B",
            project_slug="batch-proj",
            source_tool="pytest",
        )
    )
    out = service.rewrite_project_scan_lines("batch-proj", delay_seconds=0)
    assert out["ai_attempted"] is False
    assert out["completed"] == 0
    assert out["total"] == 2
    assert "off" in out["message"].lower()
    assert len(out["threads"]) == 2


def test_rewrite_project_scan_lines_batches_open_threads(
    tmp_path: Path, monkeypatch
) -> None:
    service = HubService(
        Settings(
            data_dir=tmp_path / "data",
            auth_token="t",
            ai_base_url="http://ai.test/v1",
        )
    )
    monkeypatch.setattr(
        "adhd_hub.ai_client.generate_ai_scan_line",
        lambda *a, **k: None,
    )

    open_a = service.upsert_thread(
        ThreadUpsert(
            summary="Open A",
            focus="Focus A",
            project_slug="batch-proj",
            source_tool="pytest",
        )
    )
    open_b = service.upsert_thread(
        ThreadUpsert(
            summary="Open B",
            focus="Focus B",
            project_slug="batch-proj",
            source_tool="pytest",
        )
    )
    other = service.upsert_thread(
        ThreadUpsert(
            summary="Other project",
            focus="Elsewhere",
            project_slug="other-proj",
            source_tool="pytest",
        )
    )
    done = service.upsert_thread(
        ThreadUpsert(
            summary="Done here",
            focus="Finished focus",
            project_slug="batch-proj",
            source_tool="pytest",
        )
    )
    service.mark_done(done.id)

    calls: list[str] = []
    sleeps: list[float] = []

    def fake_generate(settings, thread, client=None):
        calls.append(thread.id)
        return f"AI line for {thread.summary}"

    monkeypatch.setattr("adhd_hub.ai_client.generate_ai_scan_line", fake_generate)
    monkeypatch.setattr("time.sleep", lambda seconds: sleeps.append(seconds))

    out = service.rewrite_project_scan_lines("batch-proj", delay_seconds=0.25)
    assert out["ai_attempted"] is True
    assert out["ok"] is True
    assert out["total"] == 2
    assert out["completed"] == 2
    assert out["ai_ok"] == 2
    assert out["fallback"] == 0
    assert out["failed"] == 0
    assert set(calls) == {open_a.id, open_b.id}
    assert other.id not in calls
    assert done.id not in calls
    assert sleeps == [0.25]  # delay between the two calls, not before the first
    by_id = {t["id"]: t for t in out["threads"]}
    assert by_id[open_a.id]["scan_line"] == "AI line for Open A"
    assert by_id[open_a.id]["scan_line_source"] == SCAN_LINE_SOURCE_AI
    assert by_id[open_b.id]["scan_line_source"] == SCAN_LINE_SOURCE_AI


def test_rewrite_project_scan_lines_partial_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    service = HubService(
        Settings(
            data_dir=tmp_path / "data",
            auth_token="t",
            ai_base_url="http://ai.test/v1",
        )
    )
    monkeypatch.setattr(
        "adhd_hub.ai_client.generate_ai_scan_line",
        lambda *a, **k: None,
    )
    first = service.upsert_thread(
        ThreadUpsert(
            summary="First",
            focus="Heuristic first keep going",
            project_slug="partial",
            source_tool="pytest",
        )
    )
    second = service.upsert_thread(
        ThreadUpsert(
            summary="Second",
            focus="Heuristic second keep going",
            project_slug="partial",
            source_tool="pytest",
        )
    )
    seen = {"n": 0}

    def flaky_generate(settings, thread, client=None):
        seen["n"] += 1
        if thread.id == first.id:
            return "Keep rewriting calm ADHD-friendly scan lines for My work"
        return None

    monkeypatch.setattr("adhd_hub.ai_client.generate_ai_scan_line", flaky_generate)
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)

    out = service.rewrite_project_scan_lines("partial", delay_seconds=0)
    assert out["ai_attempted"] is True
    assert out["ai_ok"] == 1
    assert out["fallback"] == 1
    assert out["completed"] == 2
    assert "heuristic" in out["message"].lower()
    by_id = {t["id"]: t for t in out["threads"]}
    assert by_id[first.id]["scan_line_source"] == SCAN_LINE_SOURCE_AI
    assert by_id[second.id]["scan_line_source"] == SCAN_LINE_SOURCE_HEURISTIC
    assert second.id  # used above for clarity
    assert seen["n"] == 2


def test_rewrite_project_scan_lines_api_route(
    tmp_path: Path, monkeypatch
) -> None:
    from adhd_hub.app import create_app

    settings = Settings(data_dir=tmp_path / "data", auth_token="test-token")
    app = create_app(settings)
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}
    hub: HubService = app.state.service
    hub.save_ai_config(
        AiConfig(
            enabled=True,
            base_url="http://127.0.0.1:11434/v1",
            model="llama3.2",
        )
    )
    monkeypatch.setattr(
        "adhd_hub.ai_client.generate_ai_scan_line",
        lambda *a, **k: None,
    )
    hub.upsert_thread(
        ThreadUpsert(
            summary="API batch",
            focus="Focus text for heuristic",
            project_slug="api-batch",
            source_tool="pytest",
        )
    )
    monkeypatch.setattr(
        "adhd_hub.ai_client.generate_ai_scan_line",
        lambda *a, **k: "Keep rewriting calm ADHD-friendly scan lines for batch",
    )
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
    resp = client.post(
        "/api/projects/api-batch/scan-lines",
        headers=headers,
        json={},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ai_attempted"] is True
    assert payload["ai_ok"] == 1
    assert "batch" in payload["threads"][0]["scan_line"].lower()
