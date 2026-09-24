"""AI config persistence + manual scan-line rewrite API."""

from __future__ import annotations

from pathlib import Path

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
    work = (root / "src/adhd_hub/ui/js/work.js").read_text(encoding="utf-8")
    assert "data-rewrite-scan" in work
    assert "Rewrite scan line" in work
    settings = (root / "src/adhd_hub/ui/js/settings.js").read_text(encoding="utf-8")
    assert "loadAiConfig" in settings
    assert "/ai/config" in settings
