from __future__ import annotations

import json
from pathlib import Path

from adhd_hub.indexer.parsers import parse_claude_file, parse_cursor_file, parse_file_with_origins
from adhd_hub.indexer.patterns import matches_task


def test_matches_task() -> None:
    assert matches_task("I'll migrate the openclaw stack later")
    assert matches_task("TODO: finish the Valkey upgrade")
    assert not matches_task("hello world")


def test_parse_claude_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    path.write_text(
        json.dumps(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "I'll finish the Proxmox migration later"}],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    found = parse_claude_file(path)
    assert found
    assert "migration" in found[0].lower()


def test_parse_cursor_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    path.write_text(
        json.dumps({"role": "user", "content": "remind me to finish the homepage widgets"})
        + "\n",
        encoding="utf-8",
    )
    found = parse_cursor_file(path)
    assert found


def test_pending_reply_origin(tmp_path: Path) -> None:
    path = tmp_path / "pending.jsonl"
    path.write_text(
        json.dumps({"role": "user", "content": "help with migration"})
        + "\n"
        + json.dumps(
            {
                "role": "assistant",
                "content": "Do you want me to continue the Proxmox migration next?",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    items = parse_file_with_origins(path, "cursor")
    assert any(i["origin"] == "pending-reply" for i in items)
