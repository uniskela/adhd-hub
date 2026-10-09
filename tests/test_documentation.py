from __future__ import annotations

import json
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from adhd_hub.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DOCS = REPO_ROOT / "docs" / "public"
PUBLISHED_PAGES = [
    "authentication.md",
    "brand-guide.md",
    "clock-off-api.md",
    "coding-companions.md",
    "connect.md",
    "continuity-guard.md",
    "cursor-plugin-skill-sync.md",
    "dashboard.md",
    "deploy-homelab.md",
    "environment-variables.md",
    "forge-issue-inbox.md",
    "forge-permissions.md",
    "index.md",
    "indexer-schedule.md",
    "installation.md",
    "mcp-tool-contract.md",
    "merge-dedupe-api.md",
    "notes.md",
    "openclaw-mcp-oauth.md",
    "openclaw.md",
    "plans/adhd-hub-foundation.md",
    "plans/foundation-b3-kickoff.md",
    "plans/improvement-roadmap.md",
    "plans/next-waves.md",
    "plans/projects-crud-ui-revamp.md",
    "plans/thread-outcome-model.md",
    "project-agent-setup.md",
    "project-sync.md",
    "remote-mcp-access.md",
    "return-cue-coaching.md",
    "review-improvements.md",
    "rewards-roadmap.md",
    "setup.md",
    "superpowers/plans/2026-09-11-connect-report-and-companions.md",
    "superpowers/plans/2026-09-11-mcp-oauth-and-mcp-down-visibility.md",
    "superpowers/plans/2026-09-12-foundation-b2a-repo-inbound-authority.md",
    "superpowers/plans/2026-09-12-foundation-b2b-repo-outbound-promote.md",
    "superpowers/plans/2026-09-12-ui-docs-redesign.md",
    "superpowers/plans/2026-09-14-v0.10.1-forge-installer.md",
    "superpowers/plans/2026-09-15-mcp-tool-quality.md",
    "superpowers/plans/2026-10-07-product-hunt-supademo-host.md",
    "superpowers/specs/2026-09-11-connect-report-and-companions-design.md",
    "superpowers/specs/2026-09-11-mcp-oauth-and-mcp-down-visibility-design.md",
    "superpowers/specs/2026-09-12-repo-primary-issue-sync-design.md",
    "superpowers/specs/2026-09-12-source-aware-work-identity-design.md",
    "superpowers/specs/2026-09-12-ui-docs-redesign-design.md",
    "superpowers/specs/2026-09-12-ui-docs-redesign-palette-addendum.md",
    "superpowers/specs/2026-09-15-mcp-tool-quality-design.md",
    "superpowers/specs/2026-10-07-product-hunt-supademo-host-design.md",
    "writing.md",
]


def test_environment_reference_covers_every_settings_field() -> None:
    text = (PUBLIC_DOCS / "environment-variables.md").read_text(encoding="utf-8")
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
    assert '{ "Remote MCP access (tunnels for cloud agents)" = "remote-mcp-access.md" }' in nav
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


def test_remote_mcp_docs_link_to_uniskela_com_portal() -> None:
    """Public Remote MCP links should prefer the .com / Zensical docs portal."""
    index = (PUBLIC_DOCS / "index.md").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    site_url = (REPO_ROOT / "zensical.toml").read_text(encoding="utf-8")
    manifest = (REPO_ROOT / "docs" / "manifest.json").read_text(encoding="utf-8")
    canonical = "https://uniskela.com/docs/adhd-hub/remote-mcp-access/"

    assert f"]({canonical})" in index
    assert canonical in readme
    assert 'site_url = "https://uniskela.com/docs/adhd-hub/"' in site_url
    assert '"source": "docs/public/remote-mcp-access.md"' in manifest
    assert (PUBLIC_DOCS / "remote-mcp-access.md").is_file()


def test_historical_docs_are_excluded_from_site_search() -> None:
    historical_pages = [
        PUBLIC_DOCS / "review-improvements.md",
        PUBLIC_DOCS / "rewards-roadmap.md",
        PUBLIC_DOCS / "plans" / "adhd-hub-foundation.md",
        PUBLIC_DOCS / "plans" / "foundation-b3-kickoff.md",
        PUBLIC_DOCS / "plans" / "next-waves.md",
        PUBLIC_DOCS / "plans" / "projects-crud-ui-revamp.md",
        PUBLIC_DOCS / "plans" / "thread-outcome-model.md",
        *(PUBLIC_DOCS / "superpowers").rglob("*.md"),
    ]
    expected_front_matter = "---\nsearch:\n  exclude: true\n---\n"

    for path in historical_pages:
        text = path.read_text(encoding="utf-8")
        assert text.startswith(expected_front_matter)
        relative = path.relative_to(PUBLIC_DOCS)
        internal = REPO_ROOT / "docs" / "internal" / relative
        assert internal.is_file()
        assert f"https://github.com/uniskela/adhd-hub/blob/main/docs/internal/{relative}" in text
        assert "improvement-roadmap.md" in text
        assert len(text.split()) < 150, (
            f"Published archive page contains implementation detail: {path}"
        )


def test_public_docs_use_one_canonical_roadmap() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    index = (PUBLIC_DOCS / "index.md").read_text(encoding="utf-8")
    compatibility = (PUBLIC_DOCS / "plans" / "next-waves.md").read_text(encoding="utf-8")

    assert "docs/public/plans/improvement-roadmap.md" in readme
    assert "docs/public/plans/next-waves.md" not in readme
    assert "plans/improvement-roadmap.md" in index
    assert "plans/next-waves.md" not in index
    assert "improvement-roadmap.md" in compatibility
    assert "canonical planning tracker" in compatibility
    assert list((REPO_ROOT / "docs").rglob("improvement-roadmap.md")) == [
        PUBLIC_DOCS / "plans" / "improvement-roadmap.md"
    ]


def test_public_docs_do_not_embed_maintainer_machine_examples() -> None:
    paths = [
        PUBLIC_DOCS / "setup.md",
        PUBLIC_DOCS / "deploy-homelab.md",
        PUBLIC_DOCS / "indexer-schedule.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert r"Z:\Projects\adhd-hub" not in text
    assert "100.115.187.7" not in text


def test_docs_build_and_manifest_only_publish_public_sources() -> None:
    project = tomllib.loads((REPO_ROOT / "zensical.toml").read_text(encoding="utf-8"))["project"]
    assert project["docs_dir"] == "docs/public"
    assert not any(path.is_symlink() for path in PUBLIC_DOCS.rglob("*"))

    manifest = json.loads((REPO_ROOT / "docs" / "manifest.json").read_text(encoding="utf-8"))
    pages = manifest["pages"]
    sources = {page["source"] for page in pages}
    slugs = {page["slug"] for page in pages}
    assert len(sources) == len(slugs) == len(pages)
    assert "README.md" in sources
    for page in pages:
        source = Path(page["source"])
        assert (REPO_ROOT / source).is_file()
        if source == Path("README.md"):
            assert page["slug"] == "readme"
        else:
            assert source.is_relative_to("docs/public")
            assert (REPO_ROOT / source).resolve().is_relative_to(PUBLIC_DOCS)
            assert page["slug"] == source.relative_to("docs/public").with_suffix("").as_posix()

    def nav_pages(entries: list[dict]) -> set[str]:
        return {
            page
            for entry in entries
            for value in entry.values()
            for page in (nav_pages(value) if isinstance(value, list) else [value])
        }

    for page in nav_pages(project["nav"]):
        assert (PUBLIC_DOCS / page).is_file()
        assert f"docs/public/{page}" in sources


def test_previously_published_urls_still_have_public_pages() -> None:
    assert [page for page in PUBLISHED_PAGES if not (PUBLIC_DOCS / page).is_file()] == []


def test_public_markdown_links_stay_within_public_docs() -> None:
    parser = MarkdownIt()
    failures = []
    for path in PUBLIC_DOCS.rglob("*.md"):
        for block in parser.parse(path.read_text(encoding="utf-8")):
            for token in block.children or []:
                if token.type == "link_open":
                    target = token.attrGet("href")
                elif token.type == "image":
                    target = token.attrGet("src")
                else:
                    continue
                url = urlsplit(target or "")
                if url.scheme or url.netloc or not url.path:
                    continue
                destination = (path.parent / unquote(url.path)).resolve()
                if not destination.is_relative_to(PUBLIC_DOCS) or not destination.is_file():
                    failures.append(f"{path.relative_to(REPO_ROOT)}: {target}")
    assert failures == []


def test_implementation_contracts_and_agent_assets_have_separate_canonical_homes() -> None:
    for name in ["clock-off-api", "merge-dedupe-api", "mcp-tool-contract", "return-cue-coaching"]:
        assert (REPO_ROOT / "docs" / "internal" / "contracts" / f"{name}.md").is_file()
        assert (PUBLIC_DOCS / f"{name}.md").is_file()

    assert (REPO_ROOT / "docs" / "agents" / "README.md").is_file()
    for source in [
        "AGENTS.md",
        "skills/adhd-hub-session/SKILL.md",
        "skills/adhd-hub-projects/SKILL.md",
        "skills/env-check/SKILL.md",
        "adapters/codex.md",
        "adapters/cursor-rule.mdc",
        "adapters/claude-code.md",
        "adapters/openclaw.md",
    ]:
        assert (REPO_ROOT / source).is_file()
    for root in [PUBLIC_DOCS, REPO_ROOT / "docs" / "agents"]:
        assert not list(root.rglob("AGENTS.md"))
        assert not list(root.rglob("SKILL.md"))
        assert not (root / "skills").exists()
        assert not (root / "adapters").exists()
