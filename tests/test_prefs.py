from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from adhd_hub.prefs import HubPrefs, load_prefs, save_prefs
from adhd_hub.timeutil import format_timestamp
from adhd_hub.wiki import Wiki


def test_prefs_roundtrip(tmp_path: Path) -> None:
    prefs = HubPrefs(timezone="Australia/Sydney")
    save_prefs(tmp_path, prefs)
    loaded = load_prefs(tmp_path)
    assert loaded.timezone == "Australia/Sydney"


def test_prefs_connect_agents_roundtrip(tmp_path: Path) -> None:
    prefs = HubPrefs(timezone="UTC", connect_agents=["cursor", "claude"])
    save_prefs(tmp_path, prefs)
    loaded = load_prefs(tmp_path)
    assert loaded.connect_agents == ["cursor", "claude"]
    assert loaded.connect_agents_csv() == "cursor,claude"


def test_prefs_connect_companions_roundtrip(tmp_path: Path) -> None:
    prefs = HubPrefs(
        timezone="UTC",
        connect_companions=["graphify", "i-have-adhd"],
    )
    save_prefs(tmp_path, prefs)
    loaded = load_prefs(tmp_path)
    assert loaded.connect_companions == ["graphify", "i-have-adhd"]
    assert loaded.companion_enabled("graphify")
    assert loaded.companion_enabled("i-have-adhd")
    assert not loaded.companion_enabled("rtk")


def test_prefs_accepts_new_opt_in_companions(tmp_path: Path) -> None:
    prefs = HubPrefs(
        timezone="UTC",
        connect_companions=["superpowers", "context7", "agent-browser", "serena"],
    )
    save_prefs(tmp_path, prefs)
    loaded = load_prefs(tmp_path)
    assert loaded.companion_enabled("superpowers")
    assert loaded.companion_enabled("context7")
    assert loaded.companion_enabled("agent-browser")
    assert loaded.companion_enabled("serena")


def test_prefs_rejects_unknown_companion() -> None:
    import pytest

    with pytest.raises(Exception):
        HubPrefs(connect_companions=["not-a-real-tool"])


def test_format_timestamp_sydney() -> None:
    stamp = format_timestamp(
        datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        timezone="Australia/Sydney",
    )
    assert "2026-01-15 23:00" in stamp


def test_wiki_uses_timezone(tmp_path: Path) -> None:
    wiki = Wiki(tmp_path / "wiki", timezone="Australia/Sydney")
    path = wiki.upsert_progress("demo", "hello timezone")
    text = path.read_text(encoding="utf-8")
    assert "hello timezone" in text
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", text)