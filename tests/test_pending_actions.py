from __future__ import annotations

from pathlib import Path

from adhd_hub.config import Settings
from adhd_hub.models import ProjectUpsert
from adhd_hub.service import HubService


def test_mcp_style_delete_queues_pending(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_project(ProjectUpsert(title="Keep Me", slug="keep-me"))
    pending = service.request_delete_project("keep-me", reason="agent cleanup", source_tool="mcp")
    assert pending["pending"] is True
    assert service.store.get_project("keep-me") is not None
    actions = service.list_pending_actions()
    assert len(actions) == 1
    assert actions[0]["kind"] == "delete_project"

    approved = service.approve_pending_action(actions[0]["id"])
    assert approved["approved"] is True
    assert service.store.get_project("keep-me") is None
    assert service.list_pending_actions() == []


def test_reject_pending_rename(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_project(ProjectUpsert(title="Alpha", slug="alpha"))
    req = service.request_rename_project("alpha", "beta", source_tool="cursor")
    assert req["pending"] is True
    aid = req["action"]["id"]
    rejected = service.reject_pending_action(aid)
    assert rejected["rejected"] is True
    assert service.store.get_project("alpha") is not None
    assert service.store.get_project("beta") is None
