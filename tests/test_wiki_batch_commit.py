"""Wiki sync batches PROGRESS.md updates into one forge commit per wave."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from adhd_hub.forge.config import ForgeConfig, ForgeProvider
from adhd_hub.forge.wiki_sync import WikiForgeSync


def _wiki_cfg() -> ForgeConfig:
    return ForgeConfig(
        provider=ForgeProvider.gitea,
        token="tok",
        base_url="https://git.example/api/v1",
        owner="alex",
        repo="projects",
        wiki_enabled=True,
        wiki_path="",
        wiki_branch="main",
    )


def _prepare_wiki(tmp_path: Path) -> Path:
    wiki = tmp_path / "wiki"
    (wiki / "projects" / "flowtari").mkdir(parents=True)
    (wiki / "projects" / "adhd-hub").mkdir(parents=True)
    (wiki / "INDEX.md").write_text("# Index\n", encoding="utf-8")
    (wiki / "projects" / "flowtari" / "PROGRESS.md").write_text("# A\n", encoding="utf-8")
    (wiki / "projects" / "adhd-hub" / "PROGRESS.md").write_text("# B\n", encoding="utf-8")
    return wiki


def test_push_wiki_tree_batches_into_one_commit(tmp_path: Path) -> None:
    wiki = _prepare_wiki(tmp_path)
    sync = WikiForgeSync(_wiki_cfg())

    def fake_get(url, headers=None, params=None):
        resp = MagicMock()
        if "/branches/" in url:
            resp.status_code = 200
            resp.json.return_value = {
                "commit": {
                    "sha": "parentsha",
                    "commit": {"tree": {"sha": "basetree"}},
                }
            }
            return resp
        resp.status_code = 404
        return resp

    def fake_post(url, headers=None, json=None):
        resp = MagicMock()
        resp.status_code = 201
        if url.endswith("/git/blobs"):
            resp.json.return_value = {"sha": f"blob-{json['content'][:8]}"}
        elif url.endswith("/git/trees"):
            assert "base_tree" in json
            assert len(json["tree"]) == 3
            resp.json.return_value = {"sha": "newtree"}
        elif url.endswith("/git/commits"):
            assert json["message"].startswith("adhd-hub: sync wiki")
            assert "PROGRESS.md" in json["message"]
            assert json["parents"] == ["parentsha"]
            resp.json.return_value = {"sha": "newcommit"}
        else:
            resp.json.return_value = {}
        return resp

    def fake_patch(url, headers=None, json=None):
        resp = MagicMock()
        resp.status_code = 200
        assert url.endswith("/git/refs/heads/main")
        assert json["sha"] == "newcommit"
        resp.json.return_value = {}
        return resp

    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.side_effect = fake_get
        client.post.side_effect = fake_post
        client.patch.side_effect = fake_patch
        with patch.object(sync, "put_file", side_effect=AssertionError("no per-file put")):
            out = sync.push_wiki_tree(wiki)

    assert out["batched"] is True
    assert out["commit_sha"] == "newcommit"
    assert len(out["uploaded"]) == 3
    assert "INDEX.md" in out["uploaded"]


def test_push_wiki_tree_skips_unchanged(tmp_path: Path) -> None:
    wiki = _prepare_wiki(tmp_path)
    sync = WikiForgeSync(_wiki_cfg())

    def fake_get(url, headers=None, params=None):
        resp = MagicMock()
        resp.status_code = 200
        if "INDEX.md" in url:
            content = "# Index\n"
        elif "flowtari" in url:
            content = "# A\n"
        else:
            content = "# B\n"
        import base64

        resp.json.return_value = {
            "type": "file",
            "sha": "x",
            "content": base64.b64encode(content.encode()).decode(),
        }
        return resp

    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.side_effect = fake_get
        out = sync.push_wiki_tree(wiki)

    assert out.get("unchanged") is True
    assert out["uploaded"] == []
    assert out["unchanged_files"] == [
        "INDEX.md",
        "projects/adhd-hub/PROGRESS.md",
        "projects/flowtari/PROGRESS.md",
    ]
    assert out["batched"] is True
