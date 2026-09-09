from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.models import Thread
from adhd_hub.openclaw_config import (
    OpenClawConfig,
    load_openclaw_config,
    openclaw_config_path,
    save_openclaw_config,
)
from adhd_hub.service import HubService


def test_openclaw_config_encrypts_and_redacts_token(tmp_path: Path) -> None:
    config = OpenClawConfig(
        alerts_enabled=True,
        webhook_url="http://openclaw:18789/hooks/wake/",
        token="very-private-hook-token",
        stale_nudge_cron="0 18 * * 1-5",
    )
    path = save_openclaw_config(tmp_path, config, auth_token="hub-access-token")

    raw = path.read_text(encoding="utf-8")
    assert "very-private-hook-token" not in raw
    assert path.stat().st_mode & 0o777 == 0o600
    assert "token" not in config.public_dict()
    assert config.public_dict()["token_configured"] is True

    defaults = OpenClawConfig()
    loaded = load_openclaw_config(
        tmp_path,
        env_defaults=defaults,
        auth_token="hub-access-token",
    )
    assert loaded.token == "very-private-hook-token"
    assert loaded.webhook_url == "http://openclaw:18789/hooks/wake"

    wrong_key = load_openclaw_config(
        tmp_path,
        env_defaults=defaults,
        auth_token="replacement-hub-token",
    )
    assert wrong_key.token == ""


def test_openclaw_web_settings_save_preserve_clear_and_test(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path, auth_token="secret"))
    headers = {"Authorization": "Bearer secret", "X-Hub-Request": "1"}
    with TestClient(app) as client:
        saved = client.put(
            "/api/openclaw/config",
            headers=headers,
            json={
                "alerts_enabled": True,
                "webhook_url": "http://openclaw:18789/hooks/wake",
                "agent_url": "",
                "token": "hook-secret",
                "stale_nudge_cron": "15 8 * * 1-5",
                "stale_days": 4,
                "remind_cooldown_days": 5,
                "digest_max_nudge": 3,
            },
        )
        assert saved.status_code == 200
        assert saved.json()["token_configured"] is True
        assert "token" not in saved.json()
        assert "hook-secret" not in openclaw_config_path(tmp_path).read_text(encoding="utf-8")

        preserved = client.put(
            "/api/openclaw/config",
            headers=headers,
            json={"token": None, "stale_days": 6},
        )
        assert preserved.status_code == 200
        assert app.state.service.openclaw_config().token == "hook-secret"
        assert app.state.service.settings.stale_days == 6

        changed_target = client.put(
            "/api/openclaw/config",
            headers=headers,
            json={"webhook_url": "http://other-openclaw:18789/hooks/wake"},
        )
        assert changed_target.status_code == 200
        assert changed_target.json()["token_configured"] is False

        client.put(
            "/api/openclaw/config",
            headers=headers,
            json={"token": "replacement-secret"},
        ).raise_for_status()

        app.state.service.openclaw.agent = AsyncMock(return_value=True)
        tested = client.post("/api/openclaw/test", headers=headers, json={})
        assert tested.status_code == 200
        assert tested.json()["ok"] is True

        cleared = client.put(
            "/api/openclaw/config",
            headers=headers,
            json={"clear_token": True},
        )
        assert cleared.status_code == 200
        assert cleared.json()["token_configured"] is False

        reloaded = load_openclaw_config(
            tmp_path,
            env_defaults=OpenClawConfig(token="environment-secret"),
            auth_token="secret",
        )
        assert reloaded.token == ""


def test_openclaw_web_settings_reject_unsafe_values(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path, auth_token="secret"))
    headers = {"Authorization": "Bearer secret", "X-Hub-Request": "1"}
    with TestClient(app) as client:
        unsafe = client.put(
            "/api/openclaw/config",
            headers=headers,
            json={"webhook_url": "file:///etc/passwd"},
        )
        assert unsafe.status_code == 400

        bad_schedule = client.put(
            "/api/openclaw/config",
            headers=headers,
            json={"stale_nudge_cron": "not a cron"},
        )
        assert bad_schedule.status_code == 400


async def test_failed_openclaw_alert_is_not_marked_as_reminded(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path, auth_token="secret"))
    thread = Thread(
        id="stale-one",
        summary="Return to the small next step",
        project_slug="demo",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    service.list_stale_threads = Mock(return_value=[thread])
    service.store.touch_reminded = Mock()
    service.openclaw.notify_stale_threads = AsyncMock(return_value=False)

    result = await service.run_stale_nudge()

    assert result == {"nudged": 0, "openclaw": False}
    service.store.touch_reminded.assert_not_called()
