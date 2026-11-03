"""Wave 8 global search — local threads, projects, wiki snippets."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings
from adhd_hub.models import ProjectUpsert, ThreadStatus, ThreadUpsert
from adhd_hub.search import normalize_query
from adhd_hub.service import HubService


@pytest.fixture
def service(tmp_path: Path) -> HubService:
    return HubService(Settings(data_dir=tmp_path / "data", auth_token="secret"))


def test_normalize_query_trims_and_caps() -> None:
    assert normalize_query("  hello   world  ") == "hello world"
    assert len(normalize_query("x" * 500)) == 200


def test_search_finds_thread_by_goal(service: HubService) -> None:
    service.store.upsert_project(ProjectUpsert(slug="alpha", title="Alpha"))
    service.store.upsert_thread(
        ThreadUpsert(
            id="t-goal",
            summary="Ordinary title",
            project_slug="alpha",
            goal="Ship zebra-wombat importer",
            focus="Wire retries",
            resume_step="Open importer.py and fix the flake",
        )
    )
    out = service.search_work("zebra-wombat")
    assert out["query"] == "zebra-wombat"
    thread_hits = [h for h in out["hits"] if h["kind"] == "thread"]
    assert thread_hits
    assert thread_hits[0]["id"] == "t-goal"
    assert "zebra-wombat" in (thread_hits[0]["snippet"] or "").casefold()


def test_search_finds_project_and_wiki(service: HubService) -> None:
    service.store.upsert_project(
        ProjectUpsert(slug="beta", title="Beta Tools", tags=["capture-lab"], description="lab notes")
    )
    service.wiki.write_progress_raw(
        "beta",
        "# Progress\n\nRemember the mooncake-token for capture.\n",
    )
    by_tag = service.search_work("capture-lab")
    assert any(h["kind"] == "project" and h["id"] == "beta" for h in by_tag["hits"])

    by_wiki = service.search_work("mooncake-token")
    wiki_hits = [h for h in by_wiki["hits"] if h["kind"] == "wiki"]
    assert wiki_hits
    assert wiki_hits[0]["project_slug"] == "beta"
    assert "mooncake-token" in (wiki_hits[0]["snippet"] or "").casefold()


def test_search_min_query_and_excludes_done_by_default(service: HubService) -> None:
    service.store.upsert_project(ProjectUpsert(slug="gamma", title="Gamma"))
    service.store.upsert_thread(
        ThreadUpsert(
            id="open-one",
            summary="Keep open-searchable",
            project_slug="gamma",
            goal="open-searchable goal",
        )
    )
    done = service.store.upsert_thread(
        ThreadUpsert(
            id="done-one",
            summary="Finished searchable-done",
            project_slug="gamma",
            goal="searchable-done goal",
        )
    )
    service.store.transition_status(done.id, ThreadStatus.done)

    assert service.search_work("x")["hits"] == []
    default = service.search_work("searchable")
    ids = {h["id"] for h in default["hits"] if h["kind"] == "thread"}
    assert "open-one" in ids
    assert "done-one" not in ids

    with_done = service.search_work("searchable-done", include_done=True)
    assert any(h["id"] == "done-one" for h in with_done["hits"])


def test_exact_title_outranks_substring(service: HubService) -> None:
    service.store.upsert_project(ProjectUpsert(slug="rank", title="Rank"))
    service.store.upsert_thread(
        ThreadUpsert(id="exact", summary="clock", project_slug="rank", goal="other")
    )
    service.store.upsert_thread(
        ThreadUpsert(
            id="sub",
            summary="Something else",
            project_slug="rank",
            goal="the clock-off schedule",
        )
    )
    hits = service.search_work("clock")["hits"]
    thread_ids = [h["id"] for h in hits if h["kind"] == "thread"]
    assert thread_ids[0] == "exact"


def test_rest_and_mcp_search(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", auth_token="secret")
    app = create_app(settings)
    svc = app.state.service
    svc.store.upsert_project(ProjectUpsert(slug="api", title="API"))
    svc.store.upsert_thread(
        ThreadUpsert(
            id="api-t",
            summary="REST search thread",
            project_slug="api",
            goal="find-me-via-api",
        )
    )

    headers = {"Authorization": "Bearer secret", "Accept": "application/json, text/event-stream"}
    with TestClient(app, base_url="http://127.0.0.1:8787") as client:
        denied = client.get("/api/search", params={"q": "find-me-via-api"})
        assert denied.status_code in (401, 403)

        ok = client.get(
            "/api/search",
            params={"q": "find-me-via-api", "limit": 10},
            headers={"Authorization": "Bearer secret"},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert any(h["kind"] == "thread" and h["id"] == "api-t" for h in body["hits"])

        def rpc(method: str, params: dict) -> dict:
            return client.post(
                "/mcp",
                headers=headers,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            ).json()

        rpc(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        tools = {t["name"]: t for t in rpc("tools/list", {})["result"]["tools"]}
        assert tools["search_work"]["annotations"]["readOnlyHint"] is True
        result = rpc(
            "tools/call",
            {"name": "search_work", "arguments": {"query": "find-me-via-api"}},
        )["result"]
        assert not result.get("isError"), result
        structured = result["structuredContent"]
        assert any(h["kind"] == "thread" and h["id"] == "api-t" for h in structured["hits"])
