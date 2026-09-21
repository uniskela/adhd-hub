#!/usr/bin/env python3
"""Sync Hub skills/rule into adhd-hub-cursorskill (copy + Marketplace rewrites).

Hub remains the content source of truth. This script prepares a cursorskill
checkout for a PR — it never pushes to cursorskill main.

Usage (from Hub repo root):

  # Prepare a local cursorskill checkout (no git push / PR):
  python scripts/sync_cursorskill_plugin.py \\
    --plugin-repo /path/to/adhd-hub-cursorskill \\
    --hub-sha "$(git rev-parse HEAD)" \\
    --dry-run

  # After prepare, CI commits + opens/updates a PR with gh.

Exit codes:
  0 success
  1 validation / rewrite gate failure
  2 usage / path error
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HUB_DOCS_BLOB = "https://github.com/uniskela/adhd-hub/blob/main/docs"
HUB_REPO_URL = "https://github.com/uniskela/adhd-hub"
PLUGIN_REPO = "uniskela/adhd-hub-cursorskill"

# Relative markdown links to Hub docs → absolute blob URLs.
REL_DOCS_LINK_RE = re.compile(r"\]\(\.\./\.\./docs/([^)]+)\)")

# Frontmatter version keys we pin in the plugin README.
VERSION_KEYS = ("hub_skill_version", "hub_guidance_version")

# Paths that may change in the plugin checkout (allowlist).
ALLOWED_RELATIVE_CHANGES = frozenset(
    {
        "skills/adhd-hub-session/SKILL.md",
        "skills/adhd-hub-session/reference.md",
        "skills/adhd-hub-projects/SKILL.md",
        "skills/env-check/SKILL.md",
        "skills/env-check/scripts/check_runtime.sh",
        "rules/adhd-hub.mdc",
        "README.md",
    }
)

# Forbidden leftovers in the mirrored skill/rule tree after rewrites.
FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("relative Hub docs link", re.compile(r"\]\(\.\./\.\./docs/")),
    ("Hub-only probe_mcp.py invocation", re.compile(r"uv run python scripts/probe_mcp\.py")),
    ("Hub-only probe_mcp.py path", re.compile(r"(?<![\w.-])probe_mcp\.py")),
]

# Allowlisted mentions of probe_mcp.py (Marketplace-safe “do not use” wording).
PROBE_ALLOW_RE = re.compile(
    r"Do not rely on Hub-repo-only scripts such as `probe_mcp\.py`",
)

SESSION_SETUP_HUB = (
    "Setup: configure the `/mcp` endpoint for an ADHD Hub instance you operate "
    "and an `Authorization: Bearer` header using an environment variable "
    "(for example, `ADHD_HUB_MCP_TOKEN`). Prefer HTTPS; plain HTTP is only for "
    "loopback, Docker, or a private LAN/Tailscale network controlled by the "
    "operator. Browser session cookies only authorize REST, not MCP. Run "
    "`uv run python scripts/probe_mcp.py` from the repo to verify tool discovery. "
    "Never paste credentials into progress notes. The Hub stores only the "
    "requested project/thread/reminder fields in its configured local "
    "SQLite/Markdown directory; this protocol sends no full transcripts.\n\n"
    "Hub UI: `{ADHD_HUB_PUBLIC_URL}/ui` when configured."
)

SESSION_SETUP_PLUGIN = (
    "Setup: configure this plugin’s MCP variables `ADHD_HUB_MCP_URL` "
    "(your Hub `/mcp` endpoint) and `ADHD_HUB_AUTH_TOKEN` (Bearer matching the "
    "Hub server). Prefer HTTPS; plain HTTP is only for loopback, Docker, or a "
    "private LAN/Tailscale network controlled by the operator. Browser session "
    "cookies only authorize REST, not MCP.\n\n"
    "**Verify after install:** confirm Cursor’s MCP panel lists server "
    "`adhd-hub` with tools such as `resolve_project` and `session_digest`, "
    "and/or `curl` health on your Hub base URL (`GET /api/health`). Do not rely "
    "on Hub-repo-only scripts such as `probe_mcp.py`. Never paste credentials "
    "into progress notes. The Hub stores only the requested "
    "project/thread/reminder fields in its configured local SQLite/Markdown "
    "directory; this protocol sends no full transcripts.\n\n"
    "Hub UI: `{ADHD_HUB_PUBLIC_URL}/ui` when configured. See "
    f"[uniskela/adhd-hub]({HUB_REPO_URL}) for server install and docs."
)

ENV_QUICK_DETECT_HUB = (
    "From a checkout that includes this skill:\n\n"
    "```bash\n"
    "bash skills/env-check/scripts/check_runtime.sh\n"
    "```\n\n"
    "Or after `npx skills add ./skills -g` / `uniskela/adhd-hub`, run the "
    "installed copy of `scripts/check_runtime.sh`."
)

ENV_QUICK_DETECT_PLUGIN = (
    "From this plugin’s root (or the Marketplace install root / "
    "`${CURSOR_PLUGIN_ROOT}` when Cursor documents that path):\n\n"
    "```bash\n"
    "bash skills/env-check/scripts/check_runtime.sh\n"
    "```\n\n"
    "When the skill is resolved from a packaged plugin path, run the same "
    "relative script from that plugin install root. Agents may resolve skills "
    "from the plugin package path rather than the workspace checkout."
)

UPSTREAM_TABLE_RE = re.compile(
    r"(## Upstream sync\n\n.*?\| Field \| Value \|\n\|-------\|-------\|\n)"
    r"(?:\|[^\n]+\n)+",
    re.S,
)


@dataclass(frozen=True)
class PathMap:
    hub: str
    plugin: str
    executable: bool = False


PATH_MAP: tuple[PathMap, ...] = (
    PathMap("skills/adhd-hub-session/SKILL.md", "skills/adhd-hub-session/SKILL.md"),
    PathMap(
        "skills/adhd-hub-session/reference.md",
        "skills/adhd-hub-session/reference.md",
    ),
    PathMap("skills/adhd-hub-projects/SKILL.md", "skills/adhd-hub-projects/SKILL.md"),
    PathMap("skills/env-check/SKILL.md", "skills/env-check/SKILL.md"),
    PathMap(
        "skills/env-check/scripts/check_runtime.sh",
        "skills/env-check/scripts/check_runtime.sh",
        executable=True,
    ),
)


def hub_root() -> Path:
    return Path(__file__).resolve().parents[1]


def die(msg: str, code: int = 2) -> None:
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=True,
    )


def parse_frontmatter_versions(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not text.startswith("---\n"):
        return out
    end = text.find("\n---\n", 4)
    if end == -1:
        return out
    block = text[4:end]
    for line in block.splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in VERSION_KEYS:
            out[key] = value.strip()
    return out


def rewrite_docs_links(text: str) -> str:
    return REL_DOCS_LINK_RE.sub(rf"]({HUB_DOCS_BLOB}/\1)", text)


def adapt_session_reference(text: str) -> str:
    """Marketplace-safe MCP setup / verify language (see marketplace-client-plugin-plan)."""
    if SESSION_SETUP_HUB in text:
        return text.replace(SESSION_SETUP_HUB, SESSION_SETUP_PLUGIN)
    # Already adapted or drifted — apply safer substitutions when Hub wording changes.
    text = text.replace(
        "Run `uv run python scripts/probe_mcp.py` from the repo to verify tool discovery. ",
        "",
    )
    if "ADHD_HUB_MCP_URL" not in text and "ADHD_HUB_MCP_TOKEN" in text:
        text = text.replace(
            "Setup: configure the `/mcp` endpoint for an ADHD Hub instance you operate "
            "and an `Authorization: Bearer` header using an environment variable "
            "(for example, `ADHD_HUB_MCP_TOKEN`).",
            "Setup: configure this plugin’s MCP variables `ADHD_HUB_MCP_URL` "
            "(your Hub `/mcp` endpoint) and `ADHD_HUB_AUTH_TOKEN` "
            "(Bearer matching the Hub server).",
        )
    if "**Verify after install:**" not in text and "probe_mcp.py" in text:
        # Insert verify paragraph before Hub UI line when leftover probe mentions remain.
        text = re.sub(
            r"(Never paste credentials into progress notes\.)",
            "**Verify after install:** confirm Cursor’s MCP panel lists server "
            "`adhd-hub` with tools such as `resolve_project` and `session_digest`, "
            "and/or `curl` health on your Hub base URL (`GET /api/health`). "
            "Do not rely on Hub-repo-only scripts such as `probe_mcp.py`. \\1",
            text,
            count=1,
        )
    if "See [uniskela/adhd-hub]" not in text and "Hub UI:" in text:
        text = text.rstrip() + (
            f" See [uniskela/adhd-hub]({HUB_REPO_URL}) for server install and docs.\n"
        )
    return text


def adapt_env_check(text: str) -> str:
    if ENV_QUICK_DETECT_HUB in text:
        text = text.replace(ENV_QUICK_DETECT_HUB, ENV_QUICK_DETECT_PLUGIN)
    else:
        text = text.replace(
            "From a checkout that includes this skill:",
            "From this plugin’s root (or the Marketplace install root / "
            "`${CURSOR_PLUGIN_ROOT}` when Cursor documents that path):",
        )
        text = re.sub(
            r"\nOr after `npx skills add .*?`.*?\.\n",
            "\nWhen the skill is resolved from a packaged plugin path, run the same "
            "relative script from that plugin install root. Agents may resolve skills "
            "from the plugin package path rather than the workspace checkout.\n",
            text,
            count=1,
            flags=re.S,
        )
    # Rewrite forge inbox link label to match published plugin wording.
    text = text.replace(
        f"[docs/forge-issue-inbox.md]({HUB_DOCS_BLOB}/forge-issue-inbox.md)",
        f"[forge issue inbox]({HUB_DOCS_BLOB}/forge-issue-inbox.md)",
    )
    return text


def adapt_content(plugin_rel: str, text: str) -> str:
    text = rewrite_docs_links(text)
    if plugin_rel == "skills/adhd-hub-session/reference.md":
        text = adapt_session_reference(text)
    elif plugin_rel == "skills/env-check/SKILL.md":
        text = adapt_env_check(text)
    return text


def resolve_rule_source(hub: Path) -> Path:
    preferred = hub / "adapters" / "cursor-rule.mdc"
    fallback = hub / ".cursor" / "rules" / "adhd-hub.mdc"
    if preferred.is_file():
        return preferred
    if fallback.is_file():
        return fallback
    die(f"missing rule source ({preferred} or {fallback})")


def copy_mapped_files(hub: Path, plugin: Path) -> dict[str, str]:
    """Copy + adapt mapped paths. Returns parsed version pins."""
    versions: dict[str, str] = {}

    for item in PATH_MAP:
        src = hub / item.hub
        if not src.is_file():
            die(f"missing Hub source: {item.hub}")
        dest = plugin / item.plugin
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw = src.read_text(encoding="utf-8")
        versions.update({f"{item.plugin}:{k}": v for k, v in parse_frontmatter_versions(raw).items()})
        if item.executable:
            shutil.copy2(src, dest)
            dest.chmod(dest.stat().st_mode | 0o111)
            continue
        adapted = adapt_content(item.plugin, raw)
        dest.write_text(adapted, encoding="utf-8", newline="\n")

    rule_src = resolve_rule_source(hub)
    rule_dest = plugin / "rules" / "adhd-hub.mdc"
    rule_dest.parent.mkdir(parents=True, exist_ok=True)
    rule_text = rule_src.read_text(encoding="utf-8")
    versions.update(
        {f"rules/adhd-hub.mdc:{k}": v for k, v in parse_frontmatter_versions(rule_text).items()}
    )
    rule_dest.write_text(rewrite_docs_links(rule_text), encoding="utf-8", newline="\n")
    return versions


def grep_gate(plugin: Path) -> list[str]:
    errors: list[str] = []
    roots = [plugin / "skills", plugin / "rules"]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".md", ".mdc", ".sh"}:
                continue
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(plugin).as_posix()
            for label, pattern in FORBIDDEN_PATTERNS:
                for match in pattern.finditer(text):
                    snippet = match.group(0)
                    if "probe_mcp" in label:
                        window = text[max(0, match.start() - 100) : match.end() + 60]
                        if PROBE_ALLOW_RE.search(window) or (
                            "Do not rely on Hub-repo-only scripts such as" in window
                            and "probe_mcp.py" in window
                        ):
                            continue
                    errors.append(f"{rel}: forbidden {label}: {snippet!r}")
    return errors


def version_warn(hub: Path, plugin: Path, versions: dict[str, str]) -> list[str]:
    """Warn when mirrored content changed but Hub forgot to bump hub_*_version."""
    warnings: list[str] = []
    pairs = [
        ("skills/adhd-hub-session/SKILL.md", "skills/adhd-hub-session/SKILL.md"),
        ("skills/adhd-hub-projects/SKILL.md", "skills/adhd-hub-projects/SKILL.md"),
        ("skills/env-check/SKILL.md", "skills/env-check/SKILL.md"),
    ]
    for hub_rel, plugin_rel in pairs:
        hub_path = hub / hub_rel
        plugin_path = plugin / plugin_rel
        if not hub_path.is_file() or not plugin_path.is_file():
            continue
        # Compare adapted Hub content to previous plugin body excluding version line noise is hard;
        # warn only when destination already had a version and Hub source version is unchanged
        # while file bytes (post-adapt) differ from previous — handled by caller via git diff.
        key = f"{plugin_rel}:hub_skill_version"
        if key not in versions:
            warnings.append(f"{hub_rel}: missing hub_skill_version frontmatter")
    if "rules/adhd-hub.mdc:hub_guidance_version" not in versions:
        warnings.append("adapters/cursor-rule.mdc: missing hub_guidance_version frontmatter")
    return warnings


def refresh_readme(plugin: Path, hub_sha: str, versions: dict[str, str]) -> None:
    readme = plugin / "README.md"
    if not readme.is_file():
        die("plugin README.md missing")
    text = readme.read_text(encoding="utf-8")
    session_v = versions.get("skills/adhd-hub-session/SKILL.md:hub_skill_version", "?")
    projects_v = versions.get("skills/adhd-hub-projects/SKILL.md:hub_skill_version", "?")
    # Prefer session/projects when equal; show both if they diverge.
    if session_v == projects_v:
        session_projects = session_v
    else:
        session_projects = f"{session_v} / {projects_v}"
    env_v = versions.get("skills/env-check/SKILL.md:hub_skill_version", "?")
    guidance_v = versions.get("rules/adhd-hub.mdc:hub_guidance_version", "?")

    table = (
        "## Upstream sync\n\n"
        "Skills and the Hub rule are mirrored from "
        f"[uniskela/adhd-hub]({HUB_REPO_URL}) with path/link adaptations for "
        "Marketplace packaging. **Hub is the source of truth** — do not hand-edit "
        "mirrored skill/rule bodies here except for packaging emergencies. Sync is "
        "automated from Hub via GitHub Actions and opens a PR on this repo "
        "(never direct-pushes `main`). Contributor docs: "
        f"[Cursor plugin skill sync]({HUB_REPO_URL}/blob/main/docs/cursor-plugin-skill-sync.md).\n\n"
        "| Field | Value |\n"
        "|-------|--------|\n"
        f"| Upstream commit | `{hub_sha}` |\n"
        f"| `hub_skill_version` (session / projects) | `{session_projects}` |\n"
        f"| `hub_skill_version` (env-check) | `{env_v}` |\n"
        f"| `hub_guidance_version` (rule) | `{guidance_v}` |\n"
    )

    if UPSTREAM_TABLE_RE.search(text):
        text = UPSTREAM_TABLE_RE.sub(table, text, count=1)
    elif "## Upstream sync" in text:
        # Replace from heading through the next heading or EOF.
        text = re.sub(
            r"## Upstream sync\n.*?(?=\n## |\Z)",
            table.rstrip() + "\n\n",
            text,
            count=1,
            flags=re.S,
        )
    else:
        text = text.rstrip() + "\n\n" + table

    # Drop the old manual “Record a new SHA…” line if present after replacement leftovers.
    text = re.sub(
        r"\nRecord a new SHA and versions whenever you re-copy from upstream\.\n",
        "\n",
        text,
    )
    readme.write_text(text, encoding="utf-8", newline="\n")


def assert_only_allowed_changes(plugin: Path) -> list[str]:
    """Fail if git status shows paths outside the allowlist."""
    try:
        proc = run(["git", "status", "--porcelain", "-uall"], cwd=plugin, check=True)
    except subprocess.CalledProcessError as exc:
        die(f"git status failed in plugin checkout: {exc.stderr.strip()}")
    bad: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        # porcelain: XY PATH or XY ORIG -> PATH
        path_part = line[3:]
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1]
        rel = path_part.strip().strip('"')
        if rel not in ALLOWED_RELATIVE_CHANGES:
            bad.append(rel)
    return bad


def run_validator(plugin: Path) -> None:
    script = plugin / "scripts" / "validate-template.mjs"
    if not script.is_file():
        die(f"missing validator: {script}", code=1)
    try:
        proc = run(["node", str(script)], cwd=plugin, check=False)
    except FileNotFoundError:
        die("node is required to run scripts/validate-template.mjs", code=1)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        die("plugin validator failed", code=1)
    if "Validation passed." not in proc.stdout:
        die("plugin validator did not report Validation passed.", code=1)


def content_changed_without_version_bump(hub: Path, plugin: Path) -> list[str]:
    """v1: warn (do not block) when skill body changed vs HEAD but version pin unchanged.

    Compares current plugin files to git HEAD for version-bearing paths.
    """
    warnings: list[str] = []
    checks = [
        ("skills/adhd-hub-session/SKILL.md", "hub_skill_version"),
        ("skills/adhd-hub-projects/SKILL.md", "hub_skill_version"),
        ("skills/env-check/SKILL.md", "hub_skill_version"),
        ("rules/adhd-hub.mdc", "hub_guidance_version"),
    ]
    for rel, key in checks:
        path = plugin / rel
        if not path.is_file():
            continue
        try:
            old = run(
                ["git", "show", f"HEAD:{rel}"],
                cwd=plugin,
                check=False,
            )
        except subprocess.CalledProcessError:
            continue
        if old.returncode != 0:
            continue
        new_text = path.read_text(encoding="utf-8")
        old_text = old.stdout
        if new_text == old_text:
            continue
        old_v = parse_frontmatter_versions(old_text).get(key)
        new_v = parse_frontmatter_versions(new_text).get(key)
        if old_v is not None and new_v is not None and old_v == new_v:
            warnings.append(
                f"{rel}: content changed but {key} stayed at {new_v} "
                "(bump the version in Hub on intentional skill/rule edits)"
            )
    return warnings


def write_summary(
    *,
    hub_sha: str,
    versions: dict[str, str],
    warnings: list[str],
    out: Path | None,
) -> str:
    lines = [
        f"Upstream Hub SHA: `{hub_sha}`",
        f"Target plugin: `{PLUGIN_REPO}`",
        "",
        "Copied paths:",
        *[f"- `{item.plugin}` ← `{item.hub}`" for item in PATH_MAP],
        "- `rules/adhd-hub.mdc` ← `adapters/cursor-rule.mdc` (preferred) or `.cursor/rules/adhd-hub.mdc`",
        "",
        "Frontmatter versions:",
    ]
    for key in sorted(versions):
        lines.append(f"- `{key}` = `{versions[key]}`")
    lines += [
        "",
        "Rewrites applied:",
        f"- Relative `../../docs/…` links → `{HUB_DOCS_BLOB}/…`",
        "- `adhd-hub-session/reference.md` MCP setup / verify language (no `probe_mcp.py`)",
        "- `env-check` plugin-root / `${CURSOR_PLUGIN_ROOT}` script guidance",
        "- README Upstream sync table refreshed",
        "- `skills/env-check/scripts/check_runtime.sh` executable bit preserved",
        "",
    ]
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {w}" for w in warnings)
        lines.append("")
    body = "\n".join(lines).rstrip() + "\n"
    if out:
        out.write_text(body, encoding="utf-8")
    return body


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--hub-root",
        type=Path,
        default=None,
        help="Hub repository root (default: parent of scripts/)",
    )
    p.add_argument(
        "--plugin-repo",
        type=Path,
        required=True,
        help="Checkout of uniskela/adhd-hub-cursorskill to modify",
    )
    p.add_argument(
        "--hub-sha",
        required=True,
        help="Hub commit SHA that triggered this sync (pinned in README)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare files only; skip allowlist git-status gate if checkout is unclean for unrelated reasons still runs gate when git repo",
    )
    p.add_argument(
        "--skip-validator",
        action="store_true",
        help="Skip node scripts/validate-template.mjs (not for CI)",
    )
    p.add_argument(
        "--summary-out",
        type=Path,
        default=None,
        help="Write Markdown summary for the PR body",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    hub = (args.hub_root or hub_root()).resolve()
    plugin = args.plugin_repo.resolve()
    hub_sha = args.hub_sha.strip()
    if not re.fullmatch(r"[0-9a-f]{7,40}", hub_sha):
        die(f"invalid --hub-sha: {hub_sha!r}")
    if not hub.is_dir():
        die(f"Hub root not found: {hub}")
    if not plugin.is_dir():
        die(f"plugin checkout not found: {plugin}")
    if not (plugin / ".cursor-plugin" / "plugin.json").is_file():
        die(f"not a cursorskill plugin root: {plugin}")

    versions = copy_mapped_files(hub, plugin)
    refresh_readme(plugin, hub_sha, versions)

    gate_errors = grep_gate(plugin)
    if gate_errors:
        for err in gate_errors:
            print(f"error: {err}", file=sys.stderr)
        die("rewrite grep gate failed", code=1)

    warnings = version_warn(hub, plugin, versions)
    warnings.extend(content_changed_without_version_bump(hub, plugin))

    bad_paths = assert_only_allowed_changes(plugin)
    if bad_paths:
        for rel in bad_paths:
            print(f"error: path outside sync allowlist changed: {rel}", file=sys.stderr)
        die("refusing to stage non-mirrored paths", code=1)

    if not args.skip_validator:
        run_validator(plugin)

    summary = write_summary(
        hub_sha=hub_sha,
        versions=versions,
        warnings=warnings,
        out=args.summary_out,
    )
    print(summary)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if args.dry_run:
        print("dry-run: plugin checkout prepared (no commit/PR).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    # Ensure UTF-8 stdout on Windows CI mirrors; no-op on Linux.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
