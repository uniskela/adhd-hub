from __future__ import annotations

from pathlib import Path

from adhd_hub.config import Settings
from adhd_hub.forge import ForgeFacade
from adhd_hub.forge.config import ForgeConfig, ForgeProvider
from adhd_hub.openclaw import OpenClawBridge
from adhd_hub.openclaw_config import OpenClawConfig
from adhd_hub.openclaw_facade import OpenClawFacade
from adhd_hub.service import HubService


def _service(tmp_path: Path) -> HubService:
    return HubService(
        Settings(
            data_dir=tmp_path / "data",
            auth_token="test-token",
            stale_days=3,
            digest_limit=5,
            overlap_limit=5,
        )
    )


def test_hub_wires_forge_and_openclaw_facades(tmp_path: Path) -> None:
    service = _service(tmp_path)
    assert isinstance(service._forge, ForgeFacade)
    assert isinstance(service._openclaw_ops, OpenClawFacade)
    assert isinstance(service.openclaw, OpenClawBridge)


def test_forge_config_via_facade(tmp_path: Path) -> None:
    service = _service(tmp_path)
    saved = service.save_forge_config(
        ForgeConfig(
            provider=ForgeProvider.gitea,
            base_url="https://git.example/api/v1",
            token="facade-token",
            owner="alex",
            repo="homelab",
            wiki_enabled=True,
        )
    )
    assert saved.owner == "alex"
    loaded = service.forge_config()
    assert loaded.token == "facade-token"
    assert loaded.wiki_enabled is True
    assert service._forge.forge_config().repo == "homelab"


def test_openclaw_config_via_facade(tmp_path: Path) -> None:
    service = _service(tmp_path)
    saved = service.save_openclaw_config(
        OpenClawConfig(
            alerts_enabled=True,
            webhook_url="http://openclaw:18789/hooks/wake",
            token="hook-secret",
            stale_days=4,
            digest_max_nudge=3,
        )
    )
    assert saved.token == "hook-secret"
    loaded = service.openclaw_config()
    assert loaded.stale_days == 4
    assert loaded.alerts_enabled is True
    assert service.settings.stale_days == 4
    assert service.settings.digest_max_nudge == 3
    assert service.openclaw.alerts_enabled is True
    assert service._openclaw_ops.openclaw_config().token == "hook-secret"


def test_openclaw_pair_failure_via_facade(tmp_path: Path) -> None:
    service = _service(tmp_path)
    started = service.start_openclaw_pair(hub_origin="http://hub.test")

    failed = service.submit_openclaw_pair(
        {
            "user_code": started["user_code"],
            "error_code": "hooks_token_secretref_unsupported",
        }
    )

    assert failed["status"] == "failed"
    assert failed["error_code"] == "hooks_token_secretref_unsupported"
    assert failed["token_present"] is False
