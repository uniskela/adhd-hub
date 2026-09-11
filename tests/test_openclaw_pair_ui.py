from __future__ import annotations

from pathlib import Path


BOOT_JS = Path(__file__).resolve().parents[1] / "src" / "adhd_hub" / "ui" / "js" / "boot.js"


def test_openclaw_pair_failure_has_safe_ui_status() -> None:
    source = BOOT_JS.read_text(encoding="utf-8")

    assert "hooks_token_secretref_unsupported" in source
    assert "No hook token was saved." in source
    assert "OPENCLAW_SECURE_PROMPT_STUB" in source
    assert "Never print, echo, reveal, or paste the hook token" in source
