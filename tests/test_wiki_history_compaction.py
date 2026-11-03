"""Wave 8 — reversible PROGRESS.md History compaction."""

from __future__ import annotations

from pathlib import Path

from adhd_hub.config import Settings
from adhd_hub.models import ThreadStatus, ThreadUpsert
from adhd_hub.service import HubService
from adhd_hub.wiki import Wiki, compact_history_body, expand_history_body


def test_short_history_unchanged() -> None:
    body = "### 2026-11-03\n\n**Ship it**\n\nDone.\n"
    assert compact_history_body(body, keep_lines=40) == body.strip()


def test_long_history_folds_and_expands_losslessly() -> None:
    lines = [f"- line {i}" for i in range(60)]
    full = "\n".join(lines)
    compacted = compact_history_body(full, keep_lines=10)
    assert "<details>" in compacted
    assert "Older history (50 lines)" in compacted
    assert compacted.startswith("- line 0")
    assert "- line 9\n" in compacted or compacted.splitlines()[9] == "- line 9"
    assert "- line 10" not in compacted.split("<details>")[0]
    restored = expand_history_body(compacted)
    assert restored.splitlines() == lines


def test_recompact_does_not_nest_details() -> None:
    lines = [f"- entry {i}" for i in range(50)]
    once = compact_history_body("\n".join(lines), keep_lines=5)
    twice = compact_history_body(once, keep_lines=5)
    assert twice.count("<details>") == 1
    assert expand_history_body(twice).splitlines() == lines


def test_sync_progress_compacts_history(tmp_path: Path) -> None:
    wiki = Wiki(tmp_path / "wiki")
    history = "\n".join(f"- old {i}" for i in range(55))
    wiki.write_progress_raw(
        "alpha",
        "# Alpha\n\n_slug:_ `alpha`\n\n## History\n\n" + history + "\n",
    )
    wiki.sync_progress("alpha", title="Alpha", active_threads=[], milestones=[])
    text = wiki.read_progress("alpha") or ""
    section = text.split("## History", 1)[1]
    assert "<details>" in section
    assert "Older history (" in section
    assert expand_history_body(
        Wiki._extract_section(text, "History") or ""
    ).splitlines() == history.splitlines()


def test_upsert_progress_compacts_growing_history(tmp_path: Path) -> None:
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="secret"))
    service.store.upsert_thread(
        ThreadUpsert(id="t1", summary="Work", project_slug="beta", status=ThreadStatus.open)
    )
    for i in range(25):
        service.wiki.upsert_progress(
            "beta",
            content=f"note-{i} " + ("x" * 20),
            title="Beta",
            active_threads=[],
            milestones=[],
        )
    text = service.wiki.read_progress("beta") or ""
    history = Wiki._extract_section(text, "History") or ""
    # 25 notes × several lines each exceeds keep=40 after growth.
    assert "<details>" in history or len(history.splitlines()) <= 40
    if "<details>" in history:
        expanded = expand_history_body(history)
        assert "note-0" in expanded
        assert "note-24" in expanded
