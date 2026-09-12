from __future__ import annotations

from pathlib import Path

from adhd_hub.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_environment_reference_covers_every_settings_field() -> None:
    text = (REPO_ROOT / "docs" / "environment-variables.md").read_text(encoding="utf-8")
    expected = {f"ADHD_HUB_{name.upper()}" for name in Settings.model_fields}
    missing = sorted(name for name in expected if f"`{name}`" not in text)
    assert missing == []


def test_installation_and_environment_reference_are_in_docs_nav() -> None:
    nav = (REPO_ROOT / "zensical.toml").read_text(encoding="utf-8")
    assert '"installation.md"' in nav
    assert '"environment-variables.md"' in nav


def test_docs_navigation_has_calm_information_architecture() -> None:
    nav = (REPO_ROOT / "zensical.toml").read_text(encoding="utf-8")
    for group in ["Start here", "Using the Hub", "Deploy & configure", "Project"]:
        assert f'{{ "{group}" = [' in nav
    assert '{ "Connect an agent" = "connect.md" }' in nav
    assert '{ "Dashboard" = "dashboard.md" }' in nav
