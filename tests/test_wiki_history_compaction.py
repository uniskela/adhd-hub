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
    assert 'data-hub-history-fold="1"' in compacted
    assert "Older history (50 lines)" in compacted
    assert compacted.startswith("- line 0")
    assert compacted.splitlines()[9] == "- line 9"
    assert "- line 10" not in compacted.split("<details")[0]
    restored = expand_history_body(compacted)
    assert restored.splitlines() == lines


def test_recompact_does_not_nest_details() -> None:
    lines = [f"- entry {i}" for i in range(50)]
    once = compact_history_body("\n".join(lines), keep_lines=5)
    twice = compact_history_body(once, keep_lines=5)
    assert twice.count("data-hub-history-fold") == 1
    assert expand_history_body(twice).splitlines() == lines


def test_user_details_close_in_history_survives_compact_expand() -> None:
    lines = [f"- line {i}" for i in range(12)]
    lines[8] = "- note with </details> inside"
    full = "\n".join(lines)
    compacted = compact_history_body(full, keep_lines=5)
    assert compacted.count("</details>") == 1  # only the Hub wrapper closer
    inner = compacted.split("<details", 1)[1].rsplit("</details>", 1)[0]
    assert "</details>" not in inner
    restored = expand_history_body(compacted)
    assert restored.splitlines() == lines
    assert expand_history_body(compact_history_body(restored, keep_lines=5)).splitlines() == lines


def test_blank_lines_at_fold_boundary_survive_roundtrip() -> None:
    full = "a\n\nb\nc"
    restored = expand_history_body(compact_history_body(full, keep_lines=2))
    assert restored == full


def test_user_zwsp_sentinel_not_rewritten_outside_fold() -> None:
    sentinel = "<\u200b/details>"
    lines = [f"- line {i}" for i in range(8)]
    lines[1] = f"- pasted {sentinel} marker"
    full = "\n".join(lines)
    restored = expand_history_body(compact_history_body(full, keep_lines=3))
    assert restored.splitlines() == lines
    assert sentinel in restored


def test_quoted_hub_fold_markup_not_unwrapped() -> None:
    quoted = (
        '<details data-hub-history-fold="1">\n'
        "<summary>Older history (2 lines) — expandable; full text preserved</summary>\n"
        "quoted-a\nquoted-b\n"
        "</details>"
    )
    lines = [f"- line {i}" for i in range(6)]
    lines[4] = f"- example:\n{quoted}"
    # Keep as flat lines for compact (join); embed quoted block as one history blob.
    blob = "\n".join(lines[:4] + [quoted] + lines[5:])
    compacted = compact_history_body(blob, keep_lines=2)
    restored = expand_history_body(compacted)
    assert quoted in restored
    assert restored == blob


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
    assert "data-hub-history-fold" in section
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
    assert "data-hub-history-fold" in history or len(history.splitlines()) <= 40
    if "data-hub-history-fold" in history:
        expanded = expand_history_body(history)
        assert "note-0" in expanded
        assert "note-24" in expanded
