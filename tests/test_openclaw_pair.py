from __future__ import annotations

from pathlib import Path

import pytest

from adhd_hub.openclaw_config import OpenClawConfig
from adhd_hub.openclaw_pair import OpenClawPairStore, openclaw_pair_prompt


def test_openclaw_pair_roundtrip(tmp_path: Path) -> None:
    store = OpenClawPairStore(tmp_path, auth_token="hub-secret")
    started = store.start(hub_origin="https://hub.example.test")
    assert started.status == "waiting"
    assert started.user_code
    started_public = started.public_dict()
    assert "error_code" not in started_public
    assert "hooks_token_secretref_unsupported" in started_public["prompt"]
    submitted = store.submit(
        user_code=started.user_code,
        webhook_url="http://openclaw:18789/hooks/wake",
        agent_url="http://openclaw:18789/hooks/agent",
        token="hook-secret",
    )
    assert submitted.status == "submitted"
    assert submitted.webhook_url.endswith("/hooks/wake")
    assert submitted.token_present is True
    pair_path = tmp_path / "openclaw_pair.json"
    assert pair_path.is_file()
    assert (pair_path.stat().st_mode & 0o777) == 0o600
    on_disk = pair_path.read_text(encoding="utf-8")
    assert "hook-secret" not in on_disk
    assert "token_encrypted" in on_disk
    submitted_public = submitted.public_dict()
    assert "error_code" not in submitted_public
    assert "hooks_token_secretref_unsupported" in submitted_public["prompt"]
    current = OpenClawConfig(
        alerts_enabled=False,
        webhook_url="http://old:1/hooks/wake",
        stale_nudge_cron="0 18 * * 1-5",
        stale_days=7,
    )
    config = store.approve_config(current=current)
    assert config.token == "hook-secret"
    assert config.webhook_url.endswith("/hooks/wake")
    assert config.stale_nudge_cron == "0 18 * * 1-5"
    assert config.stale_days == 7
    assert store.status().status == "none"


def test_openclaw_pair_start_preserves_submitted(tmp_path: Path) -> None:
    store = OpenClawPairStore(tmp_path, auth_token="hub-secret")
    started = store.start()
    store.submit(
        user_code=started.user_code,
        webhook_url="http://openclaw:18789/hooks/wake",
        token="hook-secret",
    )
    with pytest.raises(ValueError, match="pair_submitted_pending_approval"):
        store.start()
    assert store.status().status == "submitted"


def test_openclaw_pair_rejects_bad_code(tmp_path: Path) -> None:
    store = OpenClawPairStore(tmp_path, auth_token="hub-secret")
    started = store.start()
    with pytest.raises(ValueError, match="user_code_mismatch"):
        store.submit(
            user_code="AAAA-BBBB",
            webhook_url="http://openclaw:18789/hooks/wake",
            token="x",
        )
    assert store.status().user_code == started.user_code


def test_openclaw_pair_records_protected_token_failure_without_token(tmp_path: Path) -> None:
    store = OpenClawPairStore(tmp_path, auth_token="hub-secret")
    started = store.start()

    failed = store.fail(
        user_code=started.user_code,
        error_code="hooks_token_secretref_unsupported",
    )

    assert failed.status == "failed"
    assert failed.error_code == "hooks_token_secretref_unsupported"
    assert failed.token_present is False
    public = failed.public_dict()
    assert public["error_code"] == "hooks_token_secretref_unsupported"
    assert public["token_present"] is False
    assert '"token"' not in (tmp_path / "openclaw_pair.json").read_text(encoding="utf-8")


def test_openclaw_pair_rejects_unknown_failure_code(tmp_path: Path) -> None:
    store = OpenClawPairStore(tmp_path, auth_token="hub-secret")
    started = store.start()

    with pytest.raises(ValueError, match="invalid_pair_error_code"):
        store.fail(user_code=started.user_code, error_code="unexpected_failure")

    assert store.status().status == "waiting"


def test_openclaw_rejects_metadata_and_link_local_urls() -> None:
    with pytest.raises(ValueError, match="link-local|metadata"):
        OpenClawConfig(webhook_url="http://169.254.169.254/latest/meta-data")
    with pytest.raises(ValueError, match="link-local|metadata"):
        OpenClawConfig(webhook_url="http://metadata.google.internal/computeMetadata/v1/")
    # LAN / Tailscale / loopback still allowed for same-host OpenClaw.
    ok = OpenClawConfig(webhook_url="http://127.0.0.1:18789/hooks/wake")
    assert ok.webhook_url.endswith("/hooks/wake")


def test_openclaw_pair_prompt_requires_protected_token_provisioning() -> None:
    prompt = openclaw_pair_prompt(
        hub_origin="https://hub.example.test",
        user_code="ABCD-EFGH",
    )
    lowered = prompt.lower()

    assert "hooks_token_secretref_unsupported" in prompt
    assert "protected" in lowered
    assert "never print" in lowered
    assert "do not fall back" in lowered
    assert "create or reveal a bearer token" not in lowered
