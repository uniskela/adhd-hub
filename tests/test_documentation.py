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
    assert '{ "Roadmap" = "plans/improvement-roadmap.md" }' in nav
    assert '{ "Brand guide" = "brand-guide.md" }' in nav

    hidden_from_primary_nav = [
        "Review improvements",
        "Next waves",
        "ADHD Hub foundation",
        "Projects CRUD revamp",
        "Thread outcome model",
        "Rewards roadmap",
        "Indexer schedule",
    ]
    for label in hidden_from_primary_nav:
        assert f'{{ "{label}" =' not in nav


def test_historical_docs_are_excluded_from_site_search() -> None:
    historical_pages = [
        REPO_ROOT / "docs" / "review-improvements.md",
        REPO_ROOT / "docs" / "rewards-roadmap.md",
        REPO_ROOT / "docs" / "plans" / "adhd-hub-foundation.md",
        REPO_ROOT / "docs" / "plans" / "next-waves.md",
        REPO_ROOT / "docs" / "plans" / "projects-crud-ui-revamp.md",
        REPO_ROOT / "docs" / "plans" / "thread-outcome-model.md",
    ]
    expected_front_matter = "---\nsearch:\n  exclude: true\n---\n"

    for path in historical_pages:
        assert path.read_text(encoding="utf-8").startswith(expected_front_matter)


def test_public_docs_use_one_canonical_roadmap() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    compatibility = (REPO_ROOT / "docs" / "plans" / "next-waves.md").read_text(
        encoding="utf-8"
    )

    assert "docs/plans/improvement-roadmap.md" in readme
    assert "docs/plans/next-waves.md" not in readme
    assert "plans/improvement-roadmap.md" in index
    assert "plans/next-waves.md" not in index
    assert "improvement-roadmap.md" in compatibility
    assert "canonical planning tracker" in compatibility


def test_public_docs_do_not_embed_maintainer_machine_examples() -> None:
    paths = [
        REPO_ROOT / "docs" / "setup.md",
        REPO_ROOT / "docs" / "deploy-homelab.md",
        REPO_ROOT / "docs" / "indexer-schedule.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert r"Z:\Projects\adhd-hub" not in text
    assert "100.115.187.7" not in text
