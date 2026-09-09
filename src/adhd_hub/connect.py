"""Client wire-up: MCP, AGENTS, skills, discovery, and Hub-backed install script."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from adhd_hub.project_setup import install_agent_guidance, install_skills

CURSOR_MCP_KEY = "adhd-hub"
CODEX_SERVER_KEY = "adhd-hub"
RULE_FILENAME = "adhd-hub.mdc"

# Adapters live next to package data when installed from source checkout.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADAPTERS = _REPO_ROOT / "adapters"


@dataclass
class StepResult:
    name: str
    status: str  # ok | skipped | error | warn
    detail: str


@dataclass
class ConnectReport:
    hub_url: str
    steps: list[StepResult] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str) -> None:
        self.steps.append(StepResult(name, status, detail))

    @property
    def ok(self) -> bool:
        return not any(s.status == "error" for s in self.steps)


def normalize_hub_url(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    if not cleaned:
        raise ValueError("hub URL is empty")
    if not re.match(r"^https?://", cleaned, re.IGNORECASE):
        raise ValueError("hub URL must start with http:// or https://")
    return cleaned


def resolve_hub_url(explicit: str | None = None) -> str:
    for candidate in (
        explicit,
        os.environ.get("ADHD_HUB_PUBLIC_URL"),
        os.environ.get("ADHD_HUB_HUB_URL"),
        os.environ.get("ADHD_HUB_URL"),
    ):
        if candidate and candidate.strip():
            return normalize_hub_url(candidate)
    return normalize_hub_url("http://127.0.0.1:8787")


def mcp_url_for(hub_url: str) -> str:
    return f"{normalize_hub_url(hub_url)}/mcp"


def cursor_mcp_snippet(hub_url: str) -> dict[str, Any]:
    return {
        "url": mcp_url_for(hub_url),
        "headers": {"Authorization": "Bearer ${env:ADHD_HUB_AUTH_TOKEN}"},
    }


def _http_json(url: str, *, token: str | None = None, timeout: float = 8.0) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers, method="GET")
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body) if body else {}
    if not isinstance(data, dict):
        raise TypeError(f"unexpected JSON from {url}")
    return data


def probe_hub(hub_url: str, *, token: str | None = None) -> tuple[bool, str]:
    base = normalize_hub_url(hub_url)
    try:
        health = _http_json(f"{base}/api/health", token=token)
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        return False, f"unreachable ({exc})"
    version = health.get("version") or health.get("status") or "ok"
    return True, f"health ok ({version})"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise ValueError(f"refusing to modify symlink: {path}")
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def merge_cursor_mcp(path: Path, hub_url: str) -> str:
    data = _read_json(path) if path.exists() else {}
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise TypeError(f"{path}: mcpServers must be an object")
    snippet = cursor_mcp_snippet(hub_url)
    previous = servers.get(CURSOR_MCP_KEY)
    servers[CURSOR_MCP_KEY] = snippet
    if previous == snippet and path.exists():
        return "unchanged"
    _write_json(path, data)
    return "updated" if previous else "created"


def cursor_user_mcp_path() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


def cursor_project_mcp_path(project: Path) -> Path:
    return project / ".cursor" / "mcp.json"


def install_cursor_rule(project: Path) -> str:
    source = _ADAPTERS / "cursor-rule.mdc"
    if not source.is_file():
        # Packaged wheel may omit adapters; embed a minimal rule.
        content = _FALLBACK_CURSOR_RULE
    else:
        content = source.read_text(encoding="utf-8")
    dest_dir = project / ".cursor" / "rules"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / RULE_FILENAME
    if dest.exists() and dest.is_symlink():
        raise ValueError(f"refusing to modify symlink: {dest}")
    existed = dest.is_file()
    if existed and dest.read_text(encoding="utf-8") == content:
        return "unchanged"
    dest.write_text(content, encoding="utf-8")
    return "updated" if existed else "created"


_FALLBACK_CURSOR_RULE = """---
description: ADHD Progress Hub — check overlap and save progress on unfinished work
alwaysApply: true
---

# ADHD Progress Hub

When this workspace involves starting, resuming, or leaving half-finished work:

1. Call MCP `adhd-hub` → `resolve_project`, then `session_digest`, then `check_overlap`.
2. On pause, `upsert_progress` with a short Now / Done / Next / Return cue.
3. When finished, `mark_done` on the known thread id only.

Never invent hub state. Never send secrets or full transcripts.
"""


def merge_codex_mcp(path: Path, hub_url: str) -> str:
    """Merge [mcp_servers.adhd-hub] into Codex config.toml (simple line rewrite)."""
    block_lines = [
        f"[mcp_servers.{CODEX_SERVER_KEY}]",
        f'url = "{mcp_url_for(hub_url)}"',
        'bearer_token_env_var = "ADHD_HUB_AUTH_TOKEN"',
        "",
    ]
    block = "\n".join(block_lines)
    if path.exists() and path.is_symlink():
        raise ValueError(f"refusing to modify symlink: {path}")
    original = path.read_text(encoding="utf-8") if path.is_file() else ""
    pattern = re.compile(
        rf"^\[mcp_servers\.{re.escape(CODEX_SERVER_KEY)}\]\n(?:(?!^\[).*\n?)*",
        re.MULTILINE,
    )
    if pattern.search(original):
        updated = pattern.sub(block, original)
        action = "unchanged" if updated == original else "updated"
    else:
        prefix = original.rstrip()
        updated = (prefix + "\n\n" + block) if prefix else block
        action = "created" if not original else "updated"
    if updated != original:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated if updated.endswith("\n") else updated + "\n", encoding="utf-8")
    return action


def codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def merge_claude_mcp(path: Path, hub_url: str) -> str:
    data = _read_json(path) if path.exists() else {}
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise TypeError(f"{path}: mcpServers must be an object")
    snippet = {
        "type": "http",
        "url": mcp_url_for(hub_url),
        "headers": {"Authorization": "Bearer ${env:ADHD_HUB_AUTH_TOKEN}"},
    }
    previous = servers.get(CURSOR_MCP_KEY)
    servers[CURSOR_MCP_KEY] = snippet
    if previous == snippet and path.exists():
        return "unchanged"
    _write_json(path, data)
    return "updated" if previous else "created"


def claude_user_mcp_path() -> Path:
    # Common Claude Code user MCP location; merge is idempotent if absent.
    return Path.home() / ".claude" / "mcp.json"


def find_candidate_projects(roots: list[Path], *, limit: int = 50) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        root = root.expanduser().resolve()
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            path = Path(dirpath)
            # Prune heavy / irrelevant trees
            dirnames[:] = [
                d
                for d in dirnames
                if d not in {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}
                and not d.startswith(".")
            ]
            marker = (path / ".git").exists() or "AGENTS.md" in filenames or (path / ".cursor").is_dir()
            if marker:
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    found.append(resolved)
                    if len(found) >= limit:
                        return found
    return found


def register_project(hub_url: str, project: Path, *, token: str) -> str:
    base = normalize_hub_url(hub_url)
    workspace = str(project.resolve())
    query = f"workspace_path={quote(workspace)}&create=true"
    req = Request(
        f"{base}/api/projects/resolve?{query}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise TypeError("unexpected resolve response")
    slug = data.get("slug") or "?"
    return str(slug)


def install_openclaw_skills(source: str) -> int:
    command = ["npx", "skills", "add", source, "-g", "-a", "openclaw"]
    print("Running:", " ".join(command))
    return subprocess.run(command, check=False).returncode


def render_install_sh(hub_url: str) -> str:
    """Shell script served by the Hub — never embeds auth tokens."""
    base = normalize_hub_url(hub_url)
    return f"""#!/bin/sh
# ADHD Progress Hub client wire-up (generated by {base}/install.sh)
# Does not embed tokens. Set ADHD_HUB_AUTH_TOKEN in your environment for MCP.
set -eu
HUB_URL="${{ADHD_HUB_PUBLIC_URL:-{base}}}"
PROJECT="${{1:-.}}"
export ADHD_HUB_PUBLIC_URL="$HUB_URL"

if command -v adhd-hub >/dev/null 2>&1; then
  exec adhd-hub connect "$PROJECT" --hub "$HUB_URL" --agents cursor --skills --cursor-rule
fi

if command -v uvx >/dev/null 2>&1; then
  exec uvx --from adhd-hub adhd-hub connect "$PROJECT" --hub "$HUB_URL" --agents cursor --skills --cursor-rule
fi

if command -v uv >/dev/null 2>&1; then
  echo "adhd-hub not on PATH. Try: uv tool install adhd-hub" >&2
  echo "Or from a checkout: uv run adhd-hub connect \\"$PROJECT\\" --hub \\"$HUB_URL\\"" >&2
  exit 1
fi

echo "Install the ADHD Hub CLI first (uv tool install adhd-hub), then re-run:" >&2
echo "  curl -fsSL $HUB_URL/install.sh | sh -s -- $PROJECT" >&2
exit 1
"""


def run_connect(
    *,
    project: Path,
    hub_url: str,
    agents: list[str],
    scope: str,
    install_skills_flag: bool,
    skills_source: str,
    cursor_rule: bool,
    openclaw_skills: bool,
    register: bool,
    find_roots: list[Path] | None,
    token: str | None,
) -> ConnectReport:
    hub_url = normalize_hub_url(hub_url)
    report = ConnectReport(hub_url=hub_url)
    project = project.expanduser().resolve()

    ok, detail = probe_hub(hub_url, token=token)
    report.add("hub probe", "ok" if ok else "warn", detail)

    if not project.is_dir():
        report.add("project", "error", f"not a directory: {project}")
        return report
    report.add("project", "ok", str(project))

    agents_set = {a.strip().lower() for a in agents if a.strip()}

    if "cursor" in agents_set:
        try:
            if scope == "user":
                path = cursor_user_mcp_path()
                action = merge_cursor_mcp(path, hub_url)
                report.add("cursor MCP (user)", "ok", f"{action}: {path}")
            else:
                path = cursor_project_mcp_path(project)
                action = merge_cursor_mcp(path, hub_url)
                report.add("cursor MCP (project)", "ok", f"{action}: {path}")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            report.add("cursor MCP", "error", str(exc))

        if cursor_rule:
            try:
                action = install_cursor_rule(project)
                report.add(
                    "cursor rule",
                    "ok",
                    f"{action}: {project / '.cursor' / 'rules' / RULE_FILENAME}",
                )
            except (OSError, ValueError) as exc:
                report.add("cursor rule", "error", str(exc))

    if "codex" in agents_set:
        try:
            path = codex_config_path()
            action = merge_codex_mcp(path, hub_url)
            report.add("codex MCP", "ok", f"{action}: {path}")
        except (OSError, ValueError, TypeError) as exc:
            report.add("codex MCP", "error", str(exc))

    if "claude" in agents_set or "claude-code" in agents_set:
        try:
            path = claude_user_mcp_path()
            action = merge_claude_mcp(path, hub_url)
            report.add("claude MCP", "ok", f"{action}: {path}")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            report.add("claude MCP", "error", str(exc))

    try:
        path, action = install_agent_guidance(project)
        report.add("AGENTS.md", "ok", f"{action}: {path}")
    except (OSError, ValueError) as exc:
        report.add("AGENTS.md", "error", str(exc))

    if install_skills_flag:
        if shutil.which("npx") is None:
            report.add("skills", "error", "npx not found on PATH")
        else:
            code = install_skills(skills_source)
            report.add(
                "skills",
                "ok" if code == 0 else "error",
                f"npx skills add {skills_source} -g (exit {code})",
            )
    else:
        report.add("skills", "skipped", "pass --skills to install globally")

    if openclaw_skills:
        if shutil.which("npx") is None:
            report.add("openclaw skills", "error", "npx not found on PATH")
        else:
            code = install_openclaw_skills(skills_source)
            report.add(
                "openclaw skills",
                "ok" if code == 0 else "error",
                f"npx skills add {skills_source} -g -a openclaw (exit {code})",
            )
            report.add(
                "openclaw hooks",
                "warn",
                f"Configure webhook + token in {hub_url}/ui → Settings → Connections",
            )
    else:
        report.add("openclaw skills", "skipped", "pass --openclaw-skills to install")

    if register:
        auth = token or os.environ.get("ADHD_HUB_AUTH_TOKEN")
        if not auth or auth == "change-me":
            report.add("register", "error", "set ADHD_HUB_AUTH_TOKEN to register the project")
        else:
            try:
                slug = register_project(hub_url, project, token=auth)
                report.add("register", "ok", f"project slug={slug}")
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                report.add("register", "error", str(exc))
    else:
        report.add("register", "skipped", "pass --register to create/resolve on the Hub")

    if find_roots:
        candidates = find_candidate_projects(find_roots)
        listing = ", ".join(str(p) for p in candidates[:20]) or "(none)"
        more = f" (+{len(candidates) - 20} more)" if len(candidates) > 20 else ""
        report.add("find", "ok", f"{len(candidates)} candidates: {listing}{more}")

    return report


def run_doctor(*, hub_url: str, project: Path | None, token: str | None) -> ConnectReport:
    hub_url = normalize_hub_url(hub_url)
    report = ConnectReport(hub_url=hub_url)
    ok, detail = probe_hub(hub_url, token=token)
    report.add("hub", "ok" if ok else "error", detail)

    token_set = bool(token or os.environ.get("ADHD_HUB_AUTH_TOKEN"))
    report.add(
        "ADHD_HUB_AUTH_TOKEN",
        "ok" if token_set else "warn",
        "set in environment" if token_set else "unset (MCP clients need it)",
    )

    user_mcp = cursor_user_mcp_path()
    if user_mcp.is_file():
        try:
            data = _read_json(user_mcp)
            has = CURSOR_MCP_KEY in (data.get("mcpServers") or {})
            report.add("cursor user MCP", "ok" if has else "warn", str(user_mcp))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            report.add("cursor user MCP", "error", str(exc))
    else:
        report.add("cursor user MCP", "warn", f"missing {user_mcp}")

    codex = codex_config_path()
    if codex.is_file():
        try:
            text = codex.read_text(encoding="utf-8")
            has = f"[mcp_servers.{CODEX_SERVER_KEY}]" in text
            report.add("codex MCP", "ok" if has else "warn", str(codex))
        except OSError as exc:
            report.add("codex MCP", "error", str(exc))
    else:
        report.add("codex MCP", "warn", f"missing {codex}")

    if project is not None:
        project = project.expanduser().resolve()
        report.add("project", "ok" if project.is_dir() else "error", str(project))
        proj_mcp = cursor_project_mcp_path(project)
        if proj_mcp.is_file():
            try:
                data = _read_json(proj_mcp)
                has = CURSOR_MCP_KEY in (data.get("mcpServers") or {})
                report.add("cursor project MCP", "ok" if has else "warn", str(proj_mcp))
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                report.add("cursor project MCP", "error", str(exc))
        else:
            report.add("cursor project MCP", "warn", f"missing {proj_mcp}")
        agents = project / "AGENTS.md"
        try:
            if agents.is_file() and "adhd-hub:project-agent:start" in agents.read_text(
                encoding="utf-8"
            ):
                report.add("AGENTS.md", "ok", "managed block present")
            else:
                report.add("AGENTS.md", "warn", "managed block missing")
        except OSError as exc:
            report.add("AGENTS.md", "error", str(exc))
        rule = project / ".cursor" / "rules" / RULE_FILENAME
        report.add("cursor rule", "ok" if rule.is_file() else "warn", str(rule))

    report.add(
        "skills CLI",
        "ok" if shutil.which("npx") else "warn",
        "npx available" if shutil.which("npx") else "npx not found",
    )
    return report


def print_report(report: ConnectReport) -> None:
    print(f"Hub: {report.hub_url}")
    for step in report.steps:
        mark = {"ok": "OK", "skipped": "--", "warn": "!!", "error": "XX"}.get(
            step.status, step.status
        )
        print(f"  [{mark}] {step.name}: {step.detail}")
