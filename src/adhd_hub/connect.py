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

from adhd_hub.cli_style import paint_status, print_running, style
from adhd_hub.companions import append_companion_steps
from adhd_hub.project_setup import (
    normalize_skills_agents,
    install_agent_guidance,
    install_skills,
)

CURSOR_MCP_KEY = "adhd-hub"
CODEX_SERVER_KEY = "adhd-hub"
RULE_FILENAME = "adhd-hub.mdc"
# Prefer the wheel served by this Hub (same version as /install.*).
# Fall back to GitHub when the Hub has no wheel (source-only runs).
UV_PACKAGE_GIT = "git+https://github.com/uniskela/adhd-hub.git"
UV_PACKAGE_FROM = UV_PACKAGE_GIT  # backwards-compatible alias


def cli_on_path() -> bool:
    """True when a durable ``adhd-hub`` shim is on PATH (not uvx cache / local venv)."""
    path = shutil.which("adhd-hub") or shutil.which("adhd-hub.exe")
    if not path:
        return False
    normalized = str(Path(path).resolve()).replace("\\", "/").lower()
    ephemeral = (
        "/uv/cache/",
        "/cache/uv/",
        "/archive-v0/",
        "/.venv/",
        "/venv/scripts/",
        "/venv/bin/",
    )
    return not any(marker in normalized for marker in ephemeral)


def resolve_uv_package_from(hub_url: str) -> str:
    """Prefer this Hub's wheel URL; fall back to the public git source."""
    base = normalize_hub_url(hub_url)
    try:
        with urlopen(Request(f"{base}/install/cli-wheel.url"), timeout=3) as resp:
            text = resp.read().decode("utf-8", errors="replace").strip()
        if text.startswith("http://") or text.startswith("https://"):
            return text.splitlines()[0].strip()
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        pass
    return UV_PACKAGE_GIT


def _quote_cli_arg(arg: str) -> str:
    if not arg or any(ch.isspace() for ch in arg) or any(ch in arg for ch in '&|()<>^"'):
        return '"' + arg.replace('"', '\\"') + '"'
    return arg


def format_hub_cli_command(hub_url: str, *args: str) -> str:
    """Build a runnable CLI line — use uvx when ``adhd-hub`` is not on PATH."""
    joined = " ".join(_quote_cli_arg(a) for a in args)
    if cli_on_path():
        return f"adhd-hub {joined}"
    pkg = resolve_uv_package_from(hub_url)
    if shutil.which("uvx") or shutil.which("uvx.exe"):
        return f'uvx --refresh --from "{pkg}" adhd-hub {joined}'
    return f"adhd-hub {joined}"


def permanent_cli_install_hint(hub_url: str) -> str | None:
    if cli_on_path():
        return None
    pkg = resolve_uv_package_from(hub_url)
    if shutil.which("uv") or shutil.which("uv.exe"):
        return f'uv tool install "{pkg}"'
    return f'uv tool install "{UV_PACKAGE_GIT}"'

def hub_cli_wheel_url(hub_url: str) -> str:
    """Stable alias; install scripts resolve the PEP 427 name via cli-wheel.url."""
    return f"{normalize_hub_url(hub_url)}/install/adhd-hub.whl"


def hub_cli_wheel_url_file(hub_url: str) -> str:
    return f"{normalize_hub_url(hub_url)}/install/cli-wheel.url"

# Adapters live next to package data when installed from source checkout.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADAPTERS = _REPO_ROOT / "adapters"


@dataclass
class StepResult:
    name: str
    status: str  # ok | skipped | error | warn | missing | manual
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


def _env_flag(name: str, *, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def evaluate_oauth_prm_payload(
    *,
    http_status: int | None = None,
    payload: dict[str, Any] | None = None,
    error: str | None = None,
) -> tuple[str, str]:
    """Classify OAuth protected-resource metadata for doctor (status, detail).

    Never raises; unreachable / non-200 / malformed → ``warn`` (not ``error``).
    """
    if error:
        return "warn", f"unreachable ({error})"[:200]
    if http_status is None:
        return "warn", "no HTTP status from well-known probe"
    if http_status != 200:
        return "warn", f"HTTP {http_status} from oauth-protected-resource"
    if not isinstance(payload, dict):
        return "warn", "malformed PRM (expected JSON object)"
    resource = payload.get("resource")
    servers = payload.get("authorization_servers")
    if not isinstance(resource, str) or not resource.strip():
        return "warn", "malformed PRM (missing resource)"
    if not isinstance(servers, list) or not servers:
        return "warn", "malformed PRM (missing authorization_servers)"
    return "ok", f"PRM ok ({resource.strip()})"


def probe_oauth_discovery(base_url: str, *, timeout: float = 5.0) -> tuple[str, str]:
    """GET well-known OAuth PRM (and soft-check AS metadata). Returns (status, detail)."""
    base = normalize_hub_url(base_url)
    prm_url = f"{base}/.well-known/oauth-protected-resource"
    try:
        payload = _http_json(prm_url, timeout=timeout)
        status, detail = evaluate_oauth_prm_payload(http_status=200, payload=payload)
    except HTTPError as exc:
        status, detail = evaluate_oauth_prm_payload(http_status=int(exc.code))
    except (
        URLError,
        TimeoutError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        status, detail = evaluate_oauth_prm_payload(error=str(exc))

    if status != "ok":
        return status, detail

    as_url = f"{base}/.well-known/oauth-authorization-server"
    try:
        as_payload = _http_json(as_url, timeout=timeout)
        if not isinstance(as_payload, dict) or not as_payload.get("issuer"):
            return "warn", f"{detail}; AS metadata incomplete"
        if not as_payload.get("authorization_endpoint"):
            return "warn", f"{detail}; AS metadata missing authorization_endpoint"
    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        return "warn", f"{detail}; AS metadata unreachable ({exc})"[:220]
    return status, detail


def _is_loopback_hub_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in {"127.0.0.1", "localhost", "::1"}


def _doctor_oauth_checks(report: ConnectReport, hub_url: str) -> None:
    """Probe OAuth well-known on the Hub under diagnosis (Auth-button discovery)."""
    if not _env_flag("ADHD_HUB_OAUTH_ENABLED", default=True):
        report.add(
            "hub oauth discovery",
            "ok",
            "skipped — OAuth disabled (ADHD_HUB_OAUTH_ENABLED=false on this machine)",
        )
        return

    try:
        base = normalize_hub_url(hub_url)
    except ValueError as exc:
        report.add("hub oauth discovery", "warn", f"invalid hub URL ({exc})")
        return

    public_raw = (os.environ.get("ADHD_HUB_PUBLIC_URL") or "").strip()
    public_base: str | None = None
    if public_raw:
        try:
            public_base = normalize_hub_url(public_raw)
        except ValueError as exc:
            report.add(
                "hub oauth discovery",
                "warn",
                f"invalid ADHD_HUB_PUBLIC_URL ({exc})",
            )
            return

    # Auth discovery needs a reachable public issuer. Skip quiet loopback doctor runs
    # unless ADHD_HUB_PUBLIC_URL is set (then we still probe --hub below).
    if public_base is None and _is_loopback_hub_url(base):
        report.add(
            "hub oauth discovery",
            "ok",
            "skipped — set Hub ADHD_HUB_PUBLIC_URL (or pass a non-loopback --hub) to probe Auth discovery",
        )
        return

    status, detail = probe_oauth_discovery(base)
    if public_base is not None and public_base != base:
        detail = f"{detail} · note: ADHD_HUB_PUBLIC_URL={public_base} differs from --hub"
        if status == "ok":
            status = "warn"
    report.add("hub oauth discovery", status, detail)


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


def merge_cursor_mcp(path: Path, hub_url: str, *, dry_run: bool = False) -> str:
    data = _read_json(path) if path.exists() else {}
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise TypeError(f"{path}: mcpServers must be an object")
    snippet = cursor_mcp_snippet(hub_url)
    previous = servers.get(CURSOR_MCP_KEY)
    if previous == snippet and path.exists():
        return "unchanged"
    if dry_run:
        return "would update" if previous else "would create"
    servers[CURSOR_MCP_KEY] = snippet
    _write_json(path, data)
    return "updated" if previous else "created"


def cursor_user_mcp_path() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


def cursor_project_mcp_path(project: Path) -> Path:
    return project / ".cursor" / "mcp.json"


def install_cursor_rule(project: Path, *, dry_run: bool = False) -> str:
    source = _ADAPTERS / "cursor-rule.mdc"
    if not source.is_file():
        # Packaged wheel may omit adapters; embed a minimal rule.
        content = _FALLBACK_CURSOR_RULE
    else:
        content = source.read_text(encoding="utf-8")
    dest_dir = project / ".cursor" / "rules"
    dest = dest_dir / RULE_FILENAME
    if dest.exists() and dest.is_symlink():
        raise ValueError(f"refusing to modify symlink: {dest}")
    existed = dest.is_file()
    if existed and dest.read_text(encoding="utf-8") == content:
        return "unchanged"
    if dry_run:
        return "would update" if existed else "would create"
    dest_dir.mkdir(parents=True, exist_ok=True)
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


def merge_codex_mcp(path: Path, hub_url: str, *, dry_run: bool = False) -> str:
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
    if updated == original:
        return "unchanged"
    if dry_run:
        return "would update" if original else "would create"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated if updated.endswith("\n") else updated + "\n", encoding="utf-8")
    return action


def codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def merge_claude_mcp(path: Path, hub_url: str, *, dry_run: bool = False) -> str:
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
    if previous == snippet and path.exists():
        return "unchanged"
    if dry_run:
        return "would update" if previous else "would create"
    servers[CURSOR_MCP_KEY] = snippet
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


def _npx_bin() -> str | None:
    return shutil.which("npx") or shutil.which("npx.cmd")


def install_openclaw_skills(source: str) -> int:
    npx = _npx_bin()
    if not npx:
        return 127
    command = [
        npx,
        "skills",
        "add",
        source,
        "-g",
        "-y",
        "--skill",
        "*",
        "-a",
        "openclaw",
    ]
    print_running(command)
    return subprocess.run(command, check=False).returncode


def render_install_sh(
    hub_url: str,
    *,
    default_agents: str = "",
    with_i_have_adhd: bool = False,
    with_graphify: bool = False,
    with_rtk: bool = False,
) -> str:
    """POSIX bootstrap for macOS, Linux, and WSL/Git Bash — never embeds auth tokens."""
    base = normalize_hub_url(hub_url)
    baked = (default_agents or "").strip()
    baked_iha = "1" if with_i_have_adhd else "0"
    baked_gf = "1" if with_graphify else "0"
    baked_rtk = "1" if with_rtk else "0"
    return f"""#!/bin/sh
# ADHD Progress Hub client wire-up (generated by {base}/install.sh)
# Works on macOS, Linux, WSL, and Git Bash. Does not embed tokens.
# The CLI opens your browser (or prints a one-time code) so you can Allow it
# in Hub Settings → Connections. A session is saved on disk — do not export
# ADHD_HUB_AUTH_TOKEN into your shell profile for this step.
#
# Usage:
#   curl -fsSL {base}/install.sh | sh -s -- /path/to/project
#   curl -fsSL {base}/install.sh | sh -s -- /path/to/project --register --dry-run
# Env overrides: ADHD_HUB_CONNECT_AGENTS, ADHD_HUB_CONNECT_SCOPE,
#   ADHD_HUB_CONNECT_REGISTER=1, ADHD_HUB_CONNECT_OPENCLAW_SKILLS=1,
#   ADHD_HUB_CONNECT_NO_SKILLS=1, ADHD_HUB_CONNECT_DRY_RUN=1,
#   ADHD_HUB_CONNECT_WITH_I_HAVE_ADHD=1, ADHD_HUB_CONNECT_WITH_GRAPHIFY=1,
#   ADHD_HUB_CONNECT_WITH_RTK=1,
#   ADHD_HUB_CONNECT_FLAGS="--agents cursor,codex"
# Default agents/companions come from Hub Settings → Connections (prefs), then env.
set -eu
HUB_URL="${{ADHD_HUB_PUBLIC_URL:-{base}}}"
PROJECT="."
AGENTS="${{ADHD_HUB_CONNECT_AGENTS:-{baked}}}"
SCOPE="${{ADHD_HUB_CONNECT_SCOPE:-project}}"
SKILLS=1
CURSOR_RULE=1
REGISTER=0
OPENCLAW=0
DRY_RUN=0
WITH_I_HAVE_ADHD={baked_iha}
WITH_GRAPHIFY={baked_gf}
WITH_RTK={baked_rtk}
case "${{ADHD_HUB_CONNECT_REGISTER:-}}" in 1|true|TRUE|yes|YES) REGISTER=1 ;; esac
case "${{ADHD_HUB_CONNECT_OPENCLAW_SKILLS:-}}" in 1|true|TRUE|yes|YES) OPENCLAW=1 ;; esac
case "${{ADHD_HUB_CONNECT_NO_SKILLS:-}}" in 1|true|TRUE|yes|YES) SKILLS=0 ;; esac
case "${{ADHD_HUB_CONNECT_DRY_RUN:-}}" in 1|true|TRUE|yes|YES) DRY_RUN=1 ;; esac
case "${{ADHD_HUB_CONNECT_WITH_I_HAVE_ADHD:-}}" in 1|true|TRUE|yes|YES) WITH_I_HAVE_ADHD=1 ;; esac
case "${{ADHD_HUB_CONNECT_WITH_GRAPHIFY:-}}" in 1|true|TRUE|yes|YES) WITH_GRAPHIFY=1 ;; esac
case "${{ADHD_HUB_CONNECT_WITH_RTK:-}}" in 1|true|TRUE|yes|YES) WITH_RTK=1 ;; esac
EXTRA_FLAGS="${{ADHD_HUB_CONNECT_FLAGS:-}}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --agents)
      AGENTS="$2"
      shift 2
      ;;
    --scope)
      SCOPE="$2"
      shift 2
      ;;
    --hub)
      HUB_URL="$2"
      shift 2
      ;;
    --register)
      REGISTER=1
      shift
      ;;
    --openclaw-skills)
      OPENCLAW=1
      shift
      ;;
    --no-skills)
      SKILLS=0
      shift
      ;;
    --no-cursor-rule)
      CURSOR_RULE=0
      shift
      ;;
    --with-i-have-adhd)
      WITH_I_HAVE_ADHD=1
      shift
      ;;
    --with-graphify)
      WITH_GRAPHIFY=1
      shift
      ;;
    --with-rtk)
      WITH_RTK=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
    *)
      PROJECT="$1"
      shift
      ;;
  esac
done

export ADHD_HUB_PUBLIC_URL="$HUB_URL"
set -- connect "$PROJECT" --hub "$HUB_URL" --agents "$AGENTS" --scope "$SCOPE"
[ "$SKILLS" -eq 1 ] && set -- "$@" --skills
[ "$CURSOR_RULE" -eq 1 ] && set -- "$@" --cursor-rule
[ "$REGISTER" -eq 1 ] && set -- "$@" --register
[ "$OPENCLAW" -eq 1 ] && set -- "$@" --openclaw-skills
[ "$WITH_I_HAVE_ADHD" -eq 1 ] && set -- "$@" --with-i-have-adhd
[ "$WITH_GRAPHIFY" -eq 1 ] && set -- "$@" --with-graphify
[ "$WITH_RTK" -eq 1 ] && set -- "$@" --with-rtk
[ "$DRY_RUN" -eq 1 ] && set -- "$@" --dry-run
# shellcheck disable=SC2086
[ -n "$EXTRA_FLAGS" ] && set -- "$@" $EXTRA_FLAGS

# Prefer this Hub's PEP 427-named wheel URL. Fall back to GitHub on failure.
PKG_FROM=$(curl -fsS "$HUB_URL/install/cli-wheel.url" 2>/dev/null | tr -d '\r\n' || true)
if [ -z "$PKG_FROM" ]; then
  PKG_FROM="{UV_PACKAGE_GIT}"
fi

_adhd_after_connect() {{
  code="$1"
  if [ "$code" -eq 0 ] && ! command -v adhd-hub >/dev/null 2>&1; then
    if command -v uvx >/dev/null 2>&1; then
      echo ""
      echo "Doctor (uvx — adhd-hub is not on PATH yet):"
      echo "  uvx --refresh --from \\"$PKG_FROM\\" adhd-hub doctor --hub \\"$HUB_URL\\" --project \\"$PROJECT\\""
      echo "Optional permanent install: uv tool install \\"$PKG_FROM\\""
    fi
  fi
  exit "$code"
}}

if command -v uvx >/dev/null 2>&1; then
  uvx --refresh --from "$PKG_FROM" adhd-hub "$@"
  _adhd_after_connect $?
fi

if command -v adhd-hub >/dev/null 2>&1; then
  adhd-hub "$@"
  exit $?
fi

if command -v uv >/dev/null 2>&1; then
  echo "adhd-hub not on PATH. Try: uv tool install {UV_PACKAGE_GIT}" >&2
  echo "Or from a checkout: uv run adhd-hub connect \\"$PROJECT\\" --hub \\"$HUB_URL\\"" >&2
  exit 1
fi

echo "Install the ADHD Hub CLI first (uv tool install {UV_PACKAGE_GIT}), then re-run:" >&2
echo "  curl -fsSL $HUB_URL/install.sh | sh -s -- $PROJECT" >&2
echo "Windows PowerShell: irm $HUB_URL/install.ps1 | iex" >&2
exit 1
"""


def render_install_ps1(
    hub_url: str,
    *,
    default_agents: str = "",
    with_i_have_adhd: bool = False,
    with_graphify: bool = False,
    with_rtk: bool = False,
) -> str:
    """Windows PowerShell bootstrap — never embeds auth tokens."""
    base = normalize_hub_url(hub_url)
    baked = (default_agents or "").strip().replace('"', '`"')
    # PowerShell switch defaults: $true / $false
    sw_iha = "$true" if with_i_have_adhd else "$false"
    sw_gf = "$true" if with_graphify else "$false"
    sw_rtk = "$true" if with_rtk else "$false"
    return f"""# ADHD Progress Hub client wire-up (generated by {base}/install.ps1)
# Windows PowerShell 5+ / PowerShell 7. Does not embed tokens.
# The CLI opens your browser (or prints a one-time code) so you can Allow it
# in Hub Settings → Connections. A session is saved on disk — do not put
# ADHD_HUB_AUTH_TOKEN in your profile for this step.
#
# Usage:
#   irm {base}/install.ps1 | iex
#   iex "& {{ $(irm {base}/install.ps1) }} -Project 'C:\\repo' -Register -DryRun"
# Env: ADHD_HUB_CONNECT_AGENTS, ADHD_HUB_CONNECT_SCOPE, ADHD_HUB_CONNECT_REGISTER=1,
#      ADHD_HUB_CONNECT_OPENCLAW_SKILLS=1, ADHD_HUB_CONNECT_NO_SKILLS=1, ADHD_HUB_CONNECT_DRY_RUN=1,
#      ADHD_HUB_CONNECT_WITH_I_HAVE_ADHD=1, ADHD_HUB_CONNECT_WITH_GRAPHIFY=1, ADHD_HUB_CONNECT_WITH_RTK=1
# Default agents/companions come from Hub Settings → Connections (prefs), then env.
param(
  [string]$Project = ".",
  [string]$HubUrl = "",
  [string]$Agents = "",
  # Default must be a ValidateSet member — empty "" breaks `irm | iex`.
  [ValidateSet("project", "user")][string]$Scope = "project",
  [switch]$Register,
  [switch]$OpenClawSkills,
  [switch]$NoSkills,
  [switch]$NoCursorRule,
  [switch]$WithIHaveAdhd,
  [switch]$WithGraphify,
  [switch]$WithRtk,
  [switch]$DryRun
)
$ErrorActionPreference = "Stop"
if (-not $HubUrl) {{
  if ($env:ADHD_HUB_PUBLIC_URL) {{ $HubUrl = $env:ADHD_HUB_PUBLIC_URL }}
  else {{ $HubUrl = "{base}" }}
}}
$HubUrl = $HubUrl.TrimEnd("/")
$env:ADHD_HUB_PUBLIC_URL = $HubUrl
$DefaultAgents = "{baked}"

if (-not $Agents) {{
  if ($env:ADHD_HUB_CONNECT_AGENTS) {{ $Agents = $env:ADHD_HUB_CONNECT_AGENTS }}
  elseif ($DefaultAgents) {{ $Agents = $DefaultAgents }}
}}
if ($env:ADHD_HUB_CONNECT_SCOPE -and $env:ADHD_HUB_CONNECT_SCOPE -in @("project", "user")) {{
  $Scope = $env:ADHD_HUB_CONNECT_SCOPE
}}
function Test-EnvFlag([string]$Name) {{
  $v = [Environment]::GetEnvironmentVariable($Name)
  return @("1", "true", "TRUE", "yes", "YES") -contains $v
}}
if (-not $Register -and (Test-EnvFlag "ADHD_HUB_CONNECT_REGISTER")) {{ $Register = $true }}
if (-not $OpenClawSkills -and (Test-EnvFlag "ADHD_HUB_CONNECT_OPENCLAW_SKILLS")) {{ $OpenClawSkills = $true }}
if (-not $NoSkills -and (Test-EnvFlag "ADHD_HUB_CONNECT_NO_SKILLS")) {{ $NoSkills = $true }}
if (-not $DryRun -and (Test-EnvFlag "ADHD_HUB_CONNECT_DRY_RUN")) {{ $DryRun = $true }}
# Hub Settings → Connections may bake companion defaults into this script.
if (-not $WithIHaveAdhd -and {sw_iha}) {{ $WithIHaveAdhd = $true }}
if (-not $WithGraphify -and {sw_gf}) {{ $WithGraphify = $true }}
if (-not $WithRtk -and {sw_rtk}) {{ $WithRtk = $true }}
if (-not $WithIHaveAdhd -and (Test-EnvFlag "ADHD_HUB_CONNECT_WITH_I_HAVE_ADHD")) {{ $WithIHaveAdhd = $true }}
if (-not $WithGraphify -and (Test-EnvFlag "ADHD_HUB_CONNECT_WITH_GRAPHIFY")) {{ $WithGraphify = $true }}
if (-not $WithRtk -and (Test-EnvFlag "ADHD_HUB_CONNECT_WITH_RTK")) {{ $WithRtk = $true }}

$connectArgs = @(
  "connect", $Project,
  "--hub", $HubUrl,
  "--agents", $Agents,
  "--scope", $Scope
)
if (-not $NoSkills) {{ $connectArgs += "--skills" }}
if (-not $NoCursorRule) {{ $connectArgs += "--cursor-rule" }}
if ($Register) {{ $connectArgs += "--register" }}
if ($OpenClawSkills) {{ $connectArgs += "--openclaw-skills" }}
if ($WithIHaveAdhd) {{ $connectArgs += "--with-i-have-adhd" }}
if ($WithGraphify) {{ $connectArgs += "--with-graphify" }}
if ($WithRtk) {{ $connectArgs += "--with-rtk" }}
if ($DryRun) {{ $connectArgs += "--dry-run" }}
if ($env:ADHD_HUB_CONNECT_FLAGS) {{
  $connectArgs += ($env:ADHD_HUB_CONNECT_FLAGS -split '\\s+' | Where-Object {{ $_ }})
}}

# `exit` after `irm | iex` closes the whole interactive PowerShell window.
# Only propagate exit codes when this script was run as a file (-File).
function Complete-AdhdInstall([int]$Code) {{
  if ($Code -ne 0) {{
    Write-Host ""
    Write-Host "ADHD Hub connect exited with code $Code." -ForegroundColor Yellow
  }} else {{
    Write-Host ""
    Write-Host "Install script finished. You can keep using this shell." -ForegroundColor Green
    # uvx runs an ephemeral CLI — bare `adhd-hub` is often not on PATH afterward.
    if (-not (Get-Command adhd-hub -ErrorAction SilentlyContinue)) {{
      if (Get-Command uvx -ErrorAction SilentlyContinue) {{
        Write-Host ""
        Write-Host "Doctor (uvx — adhd-hub is not on PATH yet):" -ForegroundColor Cyan
        Write-Host ("  uvx --refresh --from `"$pkgFrom`" adhd-hub doctor --hub `"$HubUrl`" --project `"$Project`"")
        Write-Host "Optional permanent install: uv tool install `"$pkgFrom`""
      }}
    }}
  }}
  if ($PSCommandPath) {{ exit $Code }}
}}

# Prefer this Hub's PEP 427-named wheel URL. Fall back to GitHub on failure.
$pkgFrom = "{UV_PACKAGE_GIT}"
try {{
  $pkgFrom = (Invoke-WebRequest -Uri "$HubUrl/install/cli-wheel.url" -UseBasicParsing).Content.Trim()
  if (-not $pkgFrom) {{ $pkgFrom = "{UV_PACKAGE_GIT}" }}
}} catch {{
  $pkgFrom = "{UV_PACKAGE_GIT}"
}}

if (Get-Command uvx -ErrorAction SilentlyContinue) {{
  & uvx --refresh --from $pkgFrom adhd-hub @connectArgs
  Complete-AdhdInstall $LASTEXITCODE
  return
}}

if (Get-Command adhd-hub -ErrorAction SilentlyContinue) {{
  & adhd-hub @connectArgs
  Complete-AdhdInstall $LASTEXITCODE
  return
}}

if (Get-Command uv -ErrorAction SilentlyContinue) {{
  Write-Error "adhd-hub not on PATH. Try: uv tool install {UV_PACKAGE_GIT}"
  Write-Error ("Or from a checkout: uv run adhd-hub connect `"{{0}}`" --hub `"{{1}}`"" -f $Project, $HubUrl)
  Complete-AdhdInstall 1
  return
}}

Write-Host @"
Install the ADHD Hub CLI first (uv tool install {UV_PACKAGE_GIT}), then re-run:
  irm $HubUrl/install.ps1 | iex
  # safer download-then-run:
  iwr $HubUrl/install.ps1 -OutFile $env:TEMP\\adhd-hub-install.ps1
  powershell -ExecutionPolicy Bypass -File $env:TEMP\\adhd-hub-install.ps1 -Project '$Project'
macOS/Linux: curl -fsSL $HubUrl/install.sh | sh -s -- $Project
"@
Complete-AdhdInstall 1
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
    dry_run: bool = False,
    with_i_have_adhd: bool = False,
    with_graphify: bool = False,
    with_rtk: bool = False,
) -> ConnectReport:
    hub_url = normalize_hub_url(hub_url)
    report = ConnectReport(hub_url=hub_url)
    project = project.expanduser().resolve()
    if dry_run:
        report.add("mode", "ok", "dry-run (no files or remote writes)")

    ok, detail = probe_hub(hub_url, token=token)
    report.add("hub probe", "ok" if ok else "warn", detail)

    if not project.is_dir():
        report.add("project", "error", f"not a directory: {project}")
        return report
    report.add("project", "ok", str(project))

    # `*` = skills for every agent; MCP wire-up still targets known clients.
    skills_all_agents = any(a.strip() == "*" for a in agents)
    agents_set = {a.strip().lower() for a in agents if a.strip() and a.strip() != "*"}
    if skills_all_agents and not agents_set:
        agents_set = {"cursor", "codex", "claude"}

    if "cursor" in agents_set:
        try:
            if scope == "user":
                path = cursor_user_mcp_path()
                action = merge_cursor_mcp(path, hub_url, dry_run=dry_run)
                report.add("cursor MCP (user)", "ok", f"{action}: {path}")
            else:
                path = cursor_project_mcp_path(project)
                action = merge_cursor_mcp(path, hub_url, dry_run=dry_run)
                report.add("cursor MCP (project)", "ok", f"{action}: {path}")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            report.add("cursor MCP", "error", str(exc))

        if cursor_rule:
            try:
                action = install_cursor_rule(project, dry_run=dry_run)
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
            action = merge_codex_mcp(path, hub_url, dry_run=dry_run)
            report.add("codex MCP", "ok", f"{action}: {path}")
        except (OSError, ValueError, TypeError) as exc:
            report.add("codex MCP", "error", str(exc))

    if "claude" in agents_set or "claude-code" in agents_set:
        try:
            path = claude_user_mcp_path()
            action = merge_claude_mcp(path, hub_url, dry_run=dry_run)
            report.add("claude MCP", "ok", f"{action}: {path}")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            report.add("claude MCP", "error", str(exc))

    try:
        agents_path = project / "AGENTS.md"
        if dry_run:
            action = "would update" if agents_path.is_file() else "would create"
            report.add("AGENTS.md", "ok", f"{action}: {agents_path}")
        else:
            path, action = install_agent_guidance(project)
            report.add("AGENTS.md", "ok", f"{action}: {path}")
    except (OSError, ValueError) as exc:
        report.add("AGENTS.md", "error", str(exc))

    if install_skills_flag:
        if _npx_bin() is None:
            report.add(
                "skills",
                "warn" if dry_run else "error",
                "npx not found on PATH",
            )
        elif dry_run:
            if skills_all_agents:
                agent_flags = "--agent *"
            else:
                mapped = normalize_skills_agents(sorted(agents_set))
                agent_flags = (
                    " ".join(f"-a {a}" for a in mapped)
                    if mapped
                    else "(no agents — set --agents or Settings → Connections)"
                )
            report.add(
                "skills",
                "ok",
                f"would run: npx skills add {skills_source} -g -y --skill * {agent_flags}",
            )
        else:
            if skills_all_agents:
                targets: list[str] | None = None
                code = install_skills(
                    skills_source,
                    agents=None,
                    all_agents=True,
                )
                agent_note = "--agent *"
            else:
                targets = normalize_skills_agents(sorted(agents_set))
                if not targets:
                    report.add(
                        "skills",
                        "warn",
                        "no agents selected — pick agents in Settings → Connections "
                        "or pass --agents cursor,codex,claude",
                    )
                    code = None
                    agent_note = "(none)"
                else:
                    code = install_skills(
                        skills_source,
                        agents=targets,
                        all_agents=False,
                    )
                    agent_note = ",".join(targets)
            if code is not None:
                report.add(
                    "skills",
                    "ok" if code == 0 else "error",
                    f"npx skills add {skills_source} -g -y ({agent_note}) (exit {code})",
                )
    else:
        report.add("skills", "skipped", "pass --skills to install globally")

    if openclaw_skills:
        if _npx_bin() is None:
            report.add(
                "openclaw skills",
                "warn" if dry_run else "error",
                "npx not found on PATH",
            )
        elif dry_run:
            report.add(
                "openclaw skills",
                "ok",
                f"would run: npx skills add {skills_source} -g -y -a openclaw",
            )
            report.add(
                "openclaw hooks",
                "warn",
                f"Configure webhook + token in {hub_url}/ui → Settings → Connections",
            )
        else:
            code = install_openclaw_skills(skills_source)
            report.add(
                "openclaw skills",
                "ok" if code == 0 else "error",
                f"npx skills add {skills_source} -g -y -a openclaw (exit {code})",
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
            report.add(
                "register",
                "error",
                "sign in with adhd-hub login (or set ADHD_HUB_AUTH_TOKEN) to register",
            )
        elif dry_run:
            report.add(
                "register",
                "ok",
                f"would resolve/create project for {project}",
            )
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

    companion_agents = list(agents)
    append_companion_steps(
        report.add,
        companion_agents,
        with_i_have_adhd=with_i_have_adhd,
        with_graphify=with_graphify,
        with_rtk=with_rtk,
        dry_run=dry_run,
    )

    if report.ok and not dry_run:
        doctor = format_hub_cli_command(
            hub_url,
            "doctor",
            "--hub",
            hub_url,
            "--project",
            str(project),
        )
        report.add(
            "setup complete",
            "ok",
            f"Open {hub_url}/ui · run: {doctor}",
        )
    elif report.ok and dry_run:
        report.add("setup complete", "ok", "dry-run finished — re-run without --dry-run to apply")

    return report


def _doctor_remote_checks(report: ConnectReport, hub_url: str, token: str | None) -> None:
    """Optional authenticated checks against forge / OpenClaw / indexer metadata."""
    auth = token or os.environ.get("ADHD_HUB_AUTH_TOKEN")
    if not auth or auth == "change-me":
        report.add(
            "remote checks",
            "warn",
            "sign in with adhd-hub login (or set ADHD_HUB_AUTH_TOKEN) to probe forge / OpenClaw / indexer",
        )
        return

    base = normalize_hub_url(hub_url)
    try:
        health = _http_json(f"{base}/api/health", token=auth)
        last = health.get("indexer_last_run")
        if last:
            when = last.get("at") if isinstance(last, dict) else last
            report.add("indexer last run", "ok", str(when))
        else:
            report.add("indexer last run", "warn", "no indexer batch recorded yet")
    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        report.add("indexer last run", "warn", f"health probe failed ({exc})")

    try:
        forge = _http_json(f"{base}/api/forge/config", token=auth)
        provider = (forge.get("provider") or "none") if isinstance(forge, dict) else "none"
        if provider in {"", "none"}:
            report.add("forge", "warn", "not configured")
        else:
            owner = forge.get("owner") or "?"
            repo = forge.get("repo") or "?"
            report.add("forge", "ok", f"{provider} {owner}/{repo}")
    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        report.add("forge", "warn", f"unreachable ({exc})")

    try:
        oc = _http_json(f"{base}/api/openclaw/config", token=auth)
        if not isinstance(oc, dict) or not oc.get("configured"):
            report.add("openclaw", "warn", "not configured")
        else:
            report.add(
                "openclaw",
                "ok",
                "configured"
                + (" · alerts on" if oc.get("alerts_enabled") else " · alerts off"),
            )
            # Soft probe: POST test only when alerts enabled (avoid surprise wake).
            if oc.get("alerts_enabled"):
                try:
                    headers = {
                        "Accept": "application/json",
                        "Authorization": f"Bearer {auth}",
                        "Content-Type": "application/json",
                    }
                    req = Request(
                        f"{base}/api/openclaw/test",
                        data=b"{}",
                        headers=headers,
                        method="POST",
                    )
                    with urlopen(req, timeout=10) as resp:
                        body = resp.read().decode("utf-8")
                    data = json.loads(body) if body else {}
                    ok = bool(data.get("ok") or data.get("sent") or data.get("status") == "ok")
                    report.add(
                        "openclaw test",
                        "ok" if ok else "warn",
                        str(data.get("detail") or data.get("message") or data)[:160],
                    )
                except (
                    HTTPError,
                    URLError,
                    TimeoutError,
                    ValueError,
                    TypeError,
                    json.JSONDecodeError,
                    OSError,
                ) as exc:
                    report.add("openclaw test", "warn", str(exc)[:160])
    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        report.add("openclaw", "warn", f"unreachable ({exc})")


def run_doctor(
    *,
    hub_url: str,
    project: Path | None,
    token: str | None,
    agents: list[str] | None = None,
) -> ConnectReport:
    hub_url = normalize_hub_url(hub_url)
    report = ConnectReport(hub_url=hub_url)
    ok, detail = probe_hub(hub_url, token=token)
    report.add("hub", "ok" if ok else "error", detail)

    token_set = bool(token or os.environ.get("ADHD_HUB_AUTH_TOKEN"))
    env_set = bool((os.environ.get("ADHD_HUB_AUTH_TOKEN") or "").strip())
    if token_set and env_set:
        token_detail = "set in environment"
    elif token_set:
        token_detail = "CLI session on disk (not in shell env)"
    else:
        token_detail = "unset — run adhd-hub login, or set ADHD_HUB_AUTH_TOKEN for MCP"
    report.add(
        "hub credentials",
        "ok" if token_set else "warn",
        token_detail,
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
        agents_md = project / "AGENTS.md"
        try:
            if agents_md.is_file() and "adhd-hub:project-agent:start" in agents_md.read_text(
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
        "ok" if _npx_bin() else "warn",
        "npx available" if _npx_bin() else "npx not found",
    )
    append_companion_steps(report.add, list(agents or []))
    _doctor_oauth_checks(report, hub_url)
    if ok:
        _doctor_remote_checks(report, hub_url, token)
    return report


_ATTENTION = frozenset({"warn", "error", "missing", "manual"})
_FIX_THESE = frozenset({"warn", "error", "missing"})
_HUB_NAMES = frozenset({"hub", "hub probe", "register", "setup complete"})
_AGENT_NAMES = frozenset({
    "cursor MCP",
    "cursor MCP (project)",
    "cursor MCP (global)",
    "cursor rule",
    "codex MCP",
    "AGENTS.md",
    "skills",
    "skills CLI",
    "openclaw skills",
})
_COMPANION_PREFIXES = (
    "companion ",
    "companions ",
    "install i-have-adhd",
    "install graphify",
    "install rtk",
)
_GROUP_ORDER = ("Hub", "Agents", "Companions", "Other")


def classify_step_group(name: str) -> str:
    if name in _HUB_NAMES or name.startswith("hub "):
        return "Hub"
    if (
        name in _AGENT_NAMES
        or name.startswith("cursor ")
        or name.startswith("codex ")
        or name.startswith("claude ")
        or name.startswith("openclaw")
    ):
        return "Agents"
    if any(name.startswith(p) for p in _COMPANION_PREFIXES):
        return "Companions"
    return "Other"


def print_report(report: ConnectReport, *, verbose: bool = False) -> None:
    """Print a connect/doctor report with a clear completion banner."""
    print()
    if report.ok:
        print(style("Complete! ADHD Hub is connected.", fg="green", bold=True))
    else:
        print(
            style(
                "Connect finished with errors — see summary below.",
                fg="red",
                bold=True,
            )
        )
    print(f"Hub: {report.hub_url}")

    attention = [s for s in report.steps if s.status in _ATTENTION]
    fix_these = [s for s in report.steps if s.status in _FIX_THESE]
    done_ok_skipped = [s for s in report.steps if s.status in {"ok", "skipped"}]

    if not report.ok:
        print()
        print("Fix these:")
        for i, step in enumerate(fix_these, start=1):
            print(f"  {i}. {step.name} — {step.detail}")
    else:
        print()
        print("Do next:")
        print(f"  - Open the Hub UI: {report.hub_url}/ui")
        if any(s.name == "setup complete" for s in report.steps):
            print("  - Restart your coding agent(s) so MCP + skills reload.")
            print("  - When you pick work up later, agents will see Hub progress.")
            setup = next((s for s in report.steps if s.name == "setup complete"), None)
            if setup and "run:" in setup.detail:
                # Prefer the already-formatted doctor line from setup complete.
                doctor_part = setup.detail.split("run:", 1)[1].strip()
                print(f"  - Verify anytime: {doctor_part}")
            install_hint = permanent_cli_install_hint(report.hub_url)
            if install_hint:
                print(
                    "  - Optional (puts `adhd-hub` on PATH): "
                    f"{install_hint}"
                )
        if any(s.name.startswith("companion ") for s in report.steps):
            print(
                "  - Optional companions (pick what fits — see guide): "
                "https://github.com/uniskela/adhd-hub/blob/main/docs/coding-companions.md"
            )
        print("  - You can close this tab/window when you're done — or keep the shell open.")

    if attention:
        print()
        print("Needs attention:")
        for step in attention:
            mark = paint_status(step.status)
            print(f"  [{mark}] {step.name}: {step.detail}")

    if done_ok_skipped:
        print()
        print("Done:")
        for group in _GROUP_ORDER:
            count = sum(
                1 for s in done_ok_skipped if classify_step_group(s.name) == group
            )
            if count:
                print(f"  {group} · {count} ok")

    if verbose:
        print()
        print("Summary of what ran:")
        for step in report.steps:
            mark = paint_status(step.status)
            print(f"  [{mark}] {step.name}: {step.detail}")

    if not report.ok:
        print()
        print("Fix the XX/!! items above, then re-run the install/connect command.")
