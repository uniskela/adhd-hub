from __future__ import annotations

from pathlib import Path

import pytest

from adhd_hub.openclaw_config import OpenClawConfig
from adhd_hub.openclaw_pair import OpenClawPairStore


def test_openclaw_pair_roundtrip(tmp_path: Path) -> None:
    store = OpenClawPairStore(tmp_path)
    started = store.start()
    assert started.status == "waiting"
    assert started.user_code
    submitted = store.submit(
        user_code=started.user_code,
        webhook_url="http://openclaw:18789/hooks/wake",
        agent_url="http://openclaw:18789/hooks/agent",
        token="hook-secret",
    )
    assert submitted.status == "submitted"
    assert submitted.webhook_url.endswith("/hooks/wake")
    assert submitted.token_present is True
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
    store = OpenClawPairStore(tmp_path)
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
    store = OpenClawPairStore(tmp_path)
    started = store.start()
    with pytest.raises(ValueError, match="user_code_mismatch"):
        store.submit(
            user_code="AAAA-BBBB",
            webhook_url="http://openclaw:18789/hooks/wake",
            token="x",
        )
    assert store.status().user_code == started.user_code
