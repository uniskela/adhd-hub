"""Optional third-party companions: metadata, detect, recommend, opt-in install.

Companions are independent of ADHD Hub. :data:`COMPANION_SPECS` is the single
declarative source for ids, categories, CLI flags, and upstream attribution.
Install behaviour lives in this module (not a plugin/marketplace framework).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from adhd_hub.cli_style import print_running
from adhd_hub.project_setup import normalize_skills_agents

COMPANIONS_DOC = "https://github.com/uniskela/adhd-hub/blob/main/docs/coding-companions.md"
I_HAVE_ADHD_SOURCE = "ayghri/i-have-adhd"
HUMANIZER_SOURCE = "blader/humanizer"
AGENT_BROWSER_SKILLS_SOURCE = "vercel-labs/agent-browser"
SUPERPOWERS_REPO = "https://github.com/obra/superpowers"
CONTEXT7_REPO = "https://github.com/upstash/context7"
AGENT_BROWSER_REPO = "https://github.com/vercel-labs/agent-browser"
SERENA_REPO = "https://github.com/oraios/serena"
PONYTAIL_REPO = "https://github.com/DietrichGebert/ponytail"
PONYTAIL_REPO_SLUG = "DietrichGebert/ponytail"
CONTEXT7_MCP_PACKAGE = "@upstash/context7-mcp"
RTK_INSTALL_SH_URL = (
    "https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh"
)

# Agents we emit concrete recipes for when the user passes ``*``.
STAR_COMPANION_AGENTS = ("cursor", "codex", "claude", "gemini")

# Only these get concrete Graphify / RTK recipes; others stay manual + docs.
GRAPHIFY_KNOWN_AGENTS = frozenset(STAR_COMPANION_AGENTS)
RTK_KNOWN_AGENTS = frozenset(STAR_COMPANION_AGENTS)
SKILLS_KNOWN_AGENTS = frozenset({"cursor", "codex", "claude"})  # via skills.sh mapping

Status = Literal["ok", "missing", "manual", "warn", "error", "skipped"]

CompanionCategory = Literal[
    "ADHD & interaction",
    "Agent workflow",
    "Code quality",
    "Code intelligence",
    "Execution & verification",
    "Writing",
]

# How Hub wires install for this companion (documentation + branching hints).
InstallMechanism = Literal[
    "skills_sh",
    "binary_and_register",
    "binary_and_init",
    "upstream_plugin",
    "mcp_merge",
    "binary_skill_and_mcp",
    "upstream_per_agent",
]


@dataclass(frozen=True)
class CompanionSpec:
    """Declarative metadata for one opt-in companion (prefs / CLI / docs / UI)."""

    id: str
    display_name: str
    category: CompanionCategory
    description: str
    upstream_repo: str
    license: str
    install_mechanism: InstallMechanism
    cli_flag: str
    privacy_notes: str = ""
    behaviour_notes: str = ""
    skills_source: str | None = None
    settings_label: str = ""

    @property
    def flag_attr(self) -> str:
        """Python kwarg name, e.g. ``with_i_have_adhd``."""
        return "with_" + self.id.replace("-", "_")

    @property
    def settings_checkbox_id(self) -> str:
        return "cc_" + self.id.replace("-", "_")

    @property
    def upstream_url(self) -> str:
        if self.upstream_repo.startswith("http"):
            return self.upstream_repo
        return f"https://github.com/{self.upstream_repo}"

    @property
    def ui_label(self) -> str:
        if self.settings_label:
            return self.settings_label
        return f"{self.display_name} ({self.category})"


# Prefs / Settings checkbox order. Add new companions here first.
COMPANION_SPECS: tuple[CompanionSpec, ...] = (
    CompanionSpec(
        id="i-have-adhd",
        display_name="i-have-adhd",
        category="ADHD & interaction",
        description=(
            "Shapes assistant replies for action-first, numbered steps "
            "(opt-in skill; no ADHD diagnosis required)."
        ),
        upstream_repo="ayghri/i-have-adhd",
        license="MIT",
        install_mechanism="skills_sh",
        cli_flag="--with-i-have-adhd",
        skills_source=I_HAVE_ADHD_SOURCE,
        settings_label="i-have-adhd (reply shape)",
        privacy_notes="Markdown skill / plugin rules — no product telemetry.",
    ),
    CompanionSpec(
        id="superpowers",
        display_name="Superpowers",
        category="Agent workflow",
        description="Agent workflow skills (brainstorm → plan → TDD → review).",
        upstream_repo="obra/superpowers",
        license="MIT",
        install_mechanism="upstream_plugin",
        cli_flag="--with-superpowers",
        settings_label="Superpowers (agent workflow)",
        privacy_notes=(
            "Local skills/plugin; see upstream for any optional telemetry "
            "(visual companion)."
        ),
    ),
    CompanionSpec(
        id="ponytail",
        display_name="Ponytail",
        category="Code quality",
        description=(
            "Encourages agents to prefer the smallest correct implementation, "
            "avoid premature abstractions and review changes for unnecessary "
            "complexity."
        ),
        upstream_repo=PONYTAIL_REPO_SLUG,
        license="MIT",
        install_mechanism="upstream_per_agent",
        cli_flag="--with-ponytail",
        settings_label="Ponytail (code quality / scope control)",
        privacy_notes=(
            "Local plugin/hooks/rules; no Hub telemetry. Upstream may inject "
            "rules via agent hooks — review before enabling."
        ),
        behaviour_notes=(
            "Opt-in only. Hub follows upstream per-agent install "
            "(Claude/Codex plugins, Cursor hooks script, Gemini extension) — "
            "not skills.sh as the primary path. Hub does not set mode; "
            "upstream default applies. Mode switches remain upstream."
        ),
    ),
    CompanionSpec(
        id="graphify",
        display_name="Graphify",
        category="Code intelligence",
        description=(
            "Builds a local knowledge graph of your repo so agents can query "
            "instead of blind grepping."
        ),
        upstream_repo="Graphify-Labs/graphify",
        license="Apache-2.0",
        install_mechanism="binary_and_register",
        cli_flag="--with-graphify",
        settings_label="Graphify (code map)",
        privacy_notes=(
            "Code AST extraction is local. No product telemetry. Docs/media "
            "semantic passes use your assistant or a configured API key."
        ),
    ),
    CompanionSpec(
        id="serena",
        display_name="Serena",
        category="Code intelligence",
        description="Semantic code navigation / editing via MCP.",
        upstream_repo="oraios/serena",
        license="MIT",
        install_mechanism="binary_skill_and_mcp",
        cli_flag="--with-serena",
        settings_label="Serena (semantic navigation, advanced)",
        privacy_notes="Typically local LSP/MCP; confirm upstream if using remote options.",
    ),
    CompanionSpec(
        id="context7",
        display_name="Context7",
        category="Code intelligence",
        description="Up-to-date library docs via MCP/CLI.",
        upstream_repo="upstash/context7",
        license="MIT",
        install_mechanism="mcp_merge",
        cli_flag="--with-context7",
        settings_label="Context7 (library docs)",
        privacy_notes="Queries go to Context7’s service; may need an API key — see upstream.",
    ),
    CompanionSpec(
        id="agent-browser",
        display_name="agent-browser",
        category="Execution & verification",
        description="Browser automation for agents to verify UI.",
        upstream_repo="vercel-labs/agent-browser",
        license="Apache-2.0",
        install_mechanism="binary_skill_and_mcp",
        cli_flag="--with-agent-browser",
        skills_source=AGENT_BROWSER_SKILLS_SOURCE,
        settings_label="agent-browser (browser verification)",
        privacy_notes="Drives a local browser; review upstream before enabling.",
    ),
    CompanionSpec(
        id="rtk",
        display_name="RTK",
        category="Execution & verification",
        description=(
            "Compresses shell/tool output before your agent reads it; optional "
            "hooks rewrite bash commands."
        ),
        upstream_repo="rtk-ai/rtk",
        license="Apache-2.0",
        install_mechanism="binary_and_init",
        cli_flag="--with-rtk",
        settings_label="RTK (shell output)",
        privacy_notes=(
            "Telemetry is opt-in (see upstream TELEMETRY.md). Leave disabled "
            "unless you consent."
        ),
    ),
    CompanionSpec(
        id="humanizer",
        display_name="Humanizer",
        category="Writing",
        description=(
            "Rewrites AI-generated prose to sound more natural while preserving "
            "the original meaning. Best suited to documentation and user-facing "
            "writing."
        ),
        upstream_repo="blader/humanizer",
        license="MIT",
        install_mechanism="skills_sh",
        cli_flag="--with-humanizer",
        skills_source=HUMANIZER_SOURCE,
        settings_label="Humanizer (writing / prose)",
        privacy_notes="Local skill; invoke on demand — no Hub post-processing.",
        behaviour_notes=(
            "Installs the skill only. Does not auto-rewrite agent responses, "
            "source code, YAML/JSON/config, generated structured data, shell "
            "commands, or internal agent state."
        ),
    ),
)

CONNECT_COMPANION_CHOICES: tuple[str, ...] = tuple(c.id for c in COMPANION_SPECS)


def resolve_enabled_companions(**flag_kwargs: bool) -> dict[str, bool]:
    """Map ``with_*`` kwargs to companion id → enabled."""
    return {
        spec.id: bool(flag_kwargs.get(spec.flag_attr, False)) for spec in COMPANION_SPECS
    }


def any_companion_enabled(enabled: dict[str, bool]) -> bool:
    return any(enabled.values())


@dataclass(frozen=True)
class CompanionStep:
    name: str
    status: Status
    detail: str


def resolve_companion_agents(agents: list[str] | None) -> tuple[bool, list[str]]:
    """Return ``(all_star, ordered unique logical agent ids)``.

    ``*`` expands to :data:`STAR_COMPANION_AGENTS`. Empty means manual-only.
    """
    raw = [a.strip().lower() for a in (agents or []) if a and a.strip()]
    all_star = any(a == "*" for a in raw)
    selected = [a for a in raw if a != "*"]
    if all_star:
        ordered: list[str] = []
        seen: set[str] = set()
        for a in list(STAR_COMPANION_AGENTS) + selected:
            key = "claude" if a in {"claude", "claude-code"} else a
            if key not in seen:
                seen.add(key)
                ordered.append(key)
        return True, ordered
    ordered = []
    seen = set()
    for a in selected:
        key = "claude" if a in {"claude", "claude-code"} else a
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return False, ordered


def _which(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _npx_bin() -> str | None:
    return _which("npx", "npx.cmd")


def _uv_tool_bin_dir() -> Path | None:
    """Directory where ``uv tool install`` places shims (often not yet on PATH)."""
    uv = _which("uv", "uv.exe")
    if not uv:
        return None
    try:
        completed = subprocess.run(
            [uv, "tool", "dir", "--bin"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    text = (completed.stdout or "").strip().splitlines()
    if not text:
        return None
    path = Path(text[0].strip())
    return path if path.is_dir() else None


def resolve_graphify_bin() -> str | None:
    """Locate graphify even when ``~/.local/bin`` is not on PATH."""
    found = _which("graphify", "graphify.exe")
    if found:
        return found
    names = ("graphify.exe", "graphify") if sys.platform == "win32" else ("graphify",)
    candidates: list[Path] = []
    local_bin = Path.home() / ".local" / "bin"
    for name in names:
        candidates.append(local_bin / name)
    tool_bin = _uv_tool_bin_dir()
    if tool_bin:
        for name in names:
            candidates.append(tool_bin / name)
    for path in candidates:
        if path.is_file():
            return str(path.resolve())
    return None


def detect_graphify() -> bool:
    return resolve_graphify_bin() is not None


def resolve_rtk_bin() -> str | None:
    found = _which("rtk", "rtk.exe")
    if found:
        return found
    names = ("rtk.exe", "rtk") if sys.platform == "win32" else ("rtk",)
    for name in names:
        path = Path.home() / ".local" / "bin" / name
        if path.is_file():
            return str(path.resolve())
    return None


def detect_rtk() -> bool:
    return resolve_rtk_bin() is not None


def _detect_named_skill(skill_name: str) -> bool | None:
    """Best-effort: True if a known skill dir exists, False if none, None if unknown."""
    home = Path.home()
    candidates = [
        home / ".cursor" / "skills" / skill_name,
        home / ".agents" / "skills" / skill_name,
        home / ".claude" / "skills" / skill_name,
        home / ".codex" / "skills" / skill_name,
        home / ".copilot" / "skills" / skill_name,
        home / ".hermes" / "skills" / skill_name,
    ]
    found_any_root = False
    for path in candidates:
        parent = path.parent
        if parent.is_dir():
            found_any_root = True
        if path.is_dir() and (path / "SKILL.md").is_file():
            return True
    if found_any_root:
        return False
    return None


def detect_i_have_adhd() -> bool | None:
    return _detect_named_skill("i-have-adhd")


def detect_humanizer() -> bool | None:
    return _detect_named_skill("humanizer")


def ponytail_clone_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "adhd-hub" / "companions" / "ponytail"


def _cursor_hooks_mention_ponytail() -> bool:
    hooks = Path.home() / ".cursor" / "hooks.json"
    if not hooks.is_file():
        return False
    try:
        text = hooks.read_text(encoding="utf-8")
    except OSError:
        return False
    return "ponytail" in text.lower()


def detect_ponytail() -> bool | None:
    """Best-effort: True if hooks/plugin wiring present (not merely a managed clone)."""
    home = Path.home()
    if (home / ".cursor" / ".ponytail-active").exists():
        return True
    if _cursor_hooks_mention_ponytail():
        return True
    plugin_hints = [
        home / ".claude" / "plugins" / "ponytail",
        home / ".codex" / "plugins" / "ponytail",
        home / ".gemini" / "extensions" / "ponytail",
    ]
    found_root = False
    for path in plugin_hints:
        if path.parent.is_dir():
            found_root = True
        if path.exists():
            return True
    hooks_dir = home / ".cursor"
    if found_root or hooks_dir.is_dir():
        return False
    return None


def humanizer_commands(agents: list[str], *, all_star: bool) -> list[str]:
    """Shell command lines to install the Humanizer skill via skills.sh."""
    if all_star:
        return [f"npx skills add {HUMANIZER_SOURCE} -g -y --agent '*'"]
    targets = normalize_skills_agents(agents)
    if not targets:
        return []
    flags = " ".join(f"-a {a}" for a in targets)
    return [f"npx skills add {HUMANIZER_SOURCE} -g -y {flags}"]


def ponytail_manual_hint(agents: list[str]) -> str:
    tips: list[str] = []
    for agent in agents:
        if agent == "cursor":
            tips.append(
                "Cursor: git clone DietrichGebert/ponytail && "
                "node ponytail/scripts/cursor-hooks.js install"
            )
        elif agent == "claude":
            tips.append(
                "Claude Code: /plugin marketplace add DietrichGebert/ponytail "
                "then /plugin install ponytail@ponytail"
            )
        elif agent == "codex":
            tips.append(
                "Codex: codex plugin marketplace add DietrichGebert/ponytail "
                "&& codex plugin add ponytail@ponytail"
            )
        elif agent == "gemini":
            tips.append(f"Gemini: gemini extensions install {PONYTAIL_REPO}")
    if not tips:
        tips.append(f"see upstream {PONYTAIL_REPO}")
    return "; ".join(tips) + f" · {COMPANIONS_DOC}"


def i_have_adhd_commands(agents: list[str], *, all_star: bool) -> list[str]:
    """Shell command lines to install the i-have-adhd skill."""
    if all_star:
        return [f"npx skills add {I_HAVE_ADHD_SOURCE} -g -y --agent '*'"]
    targets = normalize_skills_agents(agents)
    if not targets:
        return []
    flags = " ".join(f"-a {a}" for a in targets)
    return [f"npx skills add {I_HAVE_ADHD_SOURCE} -g -y {flags}"]


def graphify_register_commands(agents: list[str], *, all_star: bool) -> list[str]:
    """Commands to register Graphify with selected agents (after binary install)."""
    if not agents and not all_star:
        return []
    if all_star and set(agents) >= set(STAR_COMPANION_AGENTS):
        return [
            "graphify install",
            "graphify cursor install",
            "graphify install --platform codex",
            "graphify install --platform gemini",
            "graphify agents install",
        ]
    cmds: list[str] = []
    seen: set[str] = set()
    for agent in agents:
        if agent not in GRAPHIFY_KNOWN_AGENTS:
            continue
        if agent == "claude":
            line = "graphify install"
        elif agent == "cursor":
            line = "graphify cursor install"
        elif agent == "codex":
            line = "graphify install --platform codex"
        else:  # gemini
            line = "graphify install --platform gemini"
        if line not in seen:
            seen.add(line)
            cmds.append(line)
    return cmds


def rtk_init_commands(agents: list[str], *, all_star: bool) -> list[str]:
    """Commands to init RTK hooks for selected agents (after binary install)."""
    if not agents and not all_star:
        return []
    cmds: list[str] = []
    seen: set[str] = set()
    for agent in agents:
        if agent not in RTK_KNOWN_AGENTS:
            continue
        if agent == "claude":
            line = "rtk init -g"
        elif agent == "codex":
            line = "rtk init -g --codex"
        elif agent == "gemini":
            line = "rtk init -g --gemini"
        else:  # cursor
            line = "rtk init -g --agent cursor"
        if line not in seen:
            seen.add(line)
            cmds.append(line)
    return cmds


def unsupported_agent_note(agents: list[str]) -> str | None:
    unknown = sorted(
        {
            a
            for a in agents
            if a not in GRAPHIFY_KNOWN_AGENTS
            and a not in RTK_KNOWN_AGENTS
            and a not in SKILLS_KNOWN_AGENTS
        }
    )
    if not unknown:
        return None
    return (
        "No auto recipe for agent(s): "
        + ", ".join(unknown)
        + f" — install manually · {COMPANIONS_DOC}"
    )

def rtk_binary_hint() -> str:
    if sys.platform == "win32":
        return (
            "Install rtk.exe from https://github.com/rtk-ai/rtk/releases onto PATH "
            "(see coding-companions.md)"
        )
    return (
        "brew install rtk  # or: curl -fsSL "
        f"{RTK_INSTALL_SH_URL} | sh  — see coding-companions.md"
    )



def resolve_agent_browser_bin() -> str | None:
    found = _which("agent-browser", "agent-browser.cmd", "agent-browser.exe")
    if found:
        return found
    names = (
        ("agent-browser.exe", "agent-browser.cmd", "agent-browser")
        if sys.platform == "win32"
        else ("agent-browser",)
    )
    for name in names:
        path = Path.home() / ".local" / "bin" / name
        if path.is_file():
            return str(path.resolve())
    return None


def detect_agent_browser() -> bool:
    return resolve_agent_browser_bin() is not None


def detect_agent_browser_skill() -> bool | None:
    home = Path.home()
    candidates = [
        home / ".cursor" / "skills" / "agent-browser",
        home / ".agents" / "skills" / "agent-browser",
        home / ".claude" / "skills" / "agent-browser",
        home / ".codex" / "skills" / "agent-browser",
    ]
    found_root = False
    for path in candidates:
        if path.parent.is_dir():
            found_root = True
        if path.is_dir() and (path / "SKILL.md").is_file():
            return True
    if found_root:
        return False
    return None


def resolve_serena_bin() -> str | None:
    found = _which("serena", "serena.exe")
    if found:
        return found
    names = ("serena.exe", "serena") if sys.platform == "win32" else ("serena",)
    candidates: list[Path] = []
    local_bin = Path.home() / ".local" / "bin"
    for name in names:
        candidates.append(local_bin / name)
    tool_bin = _uv_tool_bin_dir()
    if tool_bin:
        for name in names:
            candidates.append(tool_bin / name)
    for path in candidates:
        if path.is_file():
            return str(path.resolve())
    return None


def detect_serena() -> bool:
    return resolve_serena_bin() is not None


def _read_json_obj(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def _write_json_obj(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise ValueError(f"refusing to modify symlink: {path}")
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _mcp_servers_key(data: dict[str, Any]) -> str:
    if "mcpServers" in data:
        return "mcpServers"
    if "servers" in data:
        return "servers"
    return "mcpServers"


def merge_stdio_mcp_json(
    path: Path,
    server_key: str,
    snippet: dict[str, Any],
    *,
    dry_run: bool,
) -> str:
    data = _read_json_obj(path) if path.exists() else {}
    key = _mcp_servers_key(data)
    servers = data.setdefault(key, {})
    if not isinstance(servers, dict):
        raise TypeError(f"{path}: {key} must be an object")
    previous = servers.get(server_key)
    # Preserve an existing entry that already configures this server (env, headers, etc.).
    if isinstance(previous, dict) and previous:
        return "unchanged"
    if previous == snippet and path.exists():
        return "unchanged"
    if dry_run:
        return "would update" if previous else "would create"
    servers[server_key] = snippet
    _write_json_obj(path, data)
    return "updated" if previous else "created"


def merge_codex_stdio_mcp(
    path: Path,
    server_key: str,
    command: str,
    args: list[str],
    *,
    dry_run: bool,
) -> str:
    args_toml = ", ".join(json.dumps(a) for a in args)
    command_toml = json.dumps(command)
    block = (
        f"[mcp_servers.{server_key}]\n"
        f"command = {command_toml}\n"
        f"args = [{args_toml}]\n"
    )
    if path.exists() and path.is_symlink():
        raise ValueError(f"refusing to modify symlink: {path}")
    original = path.read_text(encoding="utf-8") if path.is_file() else ""
    pattern = re.compile(
        rf"^\[mcp_servers\.{re.escape(server_key)}\]\n(?:(?!^\[).*(?:\n|$))*",
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


def context7_mcp_snippet() -> dict[str, Any]:
    return {
        "command": "npx",
        "args": ["-y", CONTEXT7_MCP_PACKAGE],
    }


def serena_mcp_snippet(serena_bin: str | None = None) -> dict[str, Any]:
    exe = serena_bin or resolve_serena_bin() or "serena"
    return {
        "command": exe,
        "args": ["start-mcp-server", "--context", "ide", "--project-from-cwd"],
    }


def detect_context7_mcp() -> bool | None:
    """True if a context7 MCP entry exists in a known client config."""
    checked = False
    cursor = Path.home() / ".cursor" / "mcp.json"
    claude = Path.home() / ".claude" / "mcp.json"
    for path in (cursor, claude):
        if not path.is_file():
            continue
        checked = True
        try:
            data = _read_json_obj(path)
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        servers = data.get("mcpServers") or data.get("servers") or {}
        if isinstance(servers, dict) and "context7" in servers:
            return True
    codex = Path.home() / ".codex" / "config.toml"
    if codex.is_file():
        checked = True
        text = codex.read_text(encoding="utf-8")
        if re.search(r"^\[mcp_servers\.context7\]", text, re.MULTILINE):
            return True
    if checked:
        return False
    return None


def detect_serena_mcp() -> bool | None:
    checked = False
    for path in (Path.home() / ".cursor" / "mcp.json", Path.home() / ".claude" / "mcp.json"):
        if not path.is_file():
            continue
        checked = True
        try:
            data = _read_json_obj(path)
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        servers = data.get("mcpServers") or data.get("servers") or {}
        if isinstance(servers, dict) and "serena" in servers:
            return True
    codex = Path.home() / ".codex" / "config.toml"
    if codex.is_file():
        checked = True
        text = codex.read_text(encoding="utf-8")
        if re.search(r"^\[mcp_servers\.serena\]", text, re.MULTILINE):
            return True
    if checked:
        return False
    return None


def detect_superpowers() -> bool | None:
    home = Path.home()
    plugin_hints = [
        home / ".claude" / "plugins" / "superpowers",
        home / ".cursor" / "plugins" / "superpowers",
        home / ".gemini" / "extensions" / "superpowers",
    ]
    found_root = False
    for path in plugin_hints:
        parent = path.parent
        if parent.is_dir():
            found_root = True
        if path.exists():
            return True
    if found_root:
        return False
    return None


def superpowers_manual_hint(agents: list[str]) -> str:
    tips: list[str] = []
    for agent in agents:
        if agent == "cursor":
            tips.append("Cursor: /add-plugin superpowers")
        elif agent == "claude":
            tips.append(
                "Claude Code: /plugin install superpowers@claude-plugins-official"
            )
        elif agent == "codex":
            tips.append(
                "Codex: follow "
                "https://raw.githubusercontent.com/obra/superpowers/main/.codex/INSTALL.md"
            )
        elif agent == "gemini":
            tips.append(f"Gemini: gemini extensions install {SUPERPOWERS_REPO}")
    if not tips:
        tips.append(f"see upstream {SUPERPOWERS_REPO}")
    return "; ".join(tips) + f" · {COMPANIONS_DOC}"


def recommend_companions(agents: list[str] | None) -> list[CompanionStep]:
    """Soft-detect companions and emit install / docs guidance."""
    all_star, resolved = resolve_companion_agents(agents)
    steps: list[CompanionStep] = [
        CompanionStep(
            "companions note",
            "ok",
            f"Optional companions. Guide: {COMPANIONS_DOC}",
        )
    ]
    note = unsupported_agent_note(resolved)
    if note:
        steps.append(CompanionStep("companions agents", "manual", note))

    detected = detect_i_have_adhd()
    iha_cmds = i_have_adhd_commands(resolved, all_star=all_star)
    if detected is True:
        steps.append(CompanionStep("companion i-have-adhd", "ok", "skill dir present"))
    elif not resolved and not all_star:
        steps.append(
            CompanionStep(
                "companion i-have-adhd",
                "manual",
                f"missing or unknown — pick --agents, then: "
                f"npx skills add {I_HAVE_ADHD_SOURCE} -g -y … · {COMPANIONS_DOC}",
            )
        )
    else:
        status: Status = "missing" if detected is False else "manual"
        detail = "; ".join(iha_cmds) if iha_cmds else f"see {COMPANIONS_DOC}"
        prefix = "not detected" if detected is False else "unknown"
        steps.append(
            CompanionStep(
                "companion i-have-adhd",
                status,
                f"{prefix} — {detail}",
            )
        )

    gf_present = detect_graphify()
    gf_cmds = ["uv tool install graphifyy"] + graphify_register_commands(
        resolved, all_star=all_star
    )
    if gf_present:
        reg = graphify_register_commands(resolved, all_star=all_star)
        extra = f" · register: {'; '.join(reg)}" if reg else ""
        steps.append(CompanionStep("companion graphify", "ok", f"on PATH{extra}"))
    elif not resolved and not all_star:
        steps.append(
            CompanionStep(
                "companion graphify",
                "manual",
                f"uv tool install graphifyy · then register per agent · {COMPANIONS_DOC}",
            )
        )
    else:
        if not graphify_register_commands(resolved, all_star=all_star) and resolved:
            steps.append(
                CompanionStep(
                    "companion graphify",
                    "manual",
                    f"uv tool install graphifyy · register manually for selected agents · {COMPANIONS_DOC}",
                )
            )
        else:
            steps.append(
                CompanionStep("companion graphify", "missing", "; ".join(gf_cmds))
            )

    rtk_present = detect_rtk()
    init_cmds = rtk_init_commands(resolved, all_star=all_star)
    if rtk_present:
        extra = f" · init: {'; '.join(init_cmds)}" if init_cmds else ""
        steps.append(
            CompanionStep(
                "companion rtk",
                "ok",
                f"on PATH{extra} · telemetry opt-in only (leave disabled unless you consent)",
            )
        )
    elif not resolved and not all_star:
        steps.append(
            CompanionStep(
                "companion rtk",
                "manual",
                f"{rtk_binary_hint()} · then rtk init per agent · {COMPANIONS_DOC}",
            )
        )
    elif not init_cmds and resolved:
        steps.append(
            CompanionStep(
                "companion rtk",
                "manual",
                f"{rtk_binary_hint()} · init manually for selected agents · {COMPANIONS_DOC}",
            )
        )
    else:
        parts = [rtk_binary_hint(), *init_cmds, "telemetry opt-in only"]
        steps.append(CompanionStep("companion rtk", "missing", "; ".join(parts)))

    # --- Superpowers (plugin; mostly manual with best-effort Gemini CLI) ---
    sp_detected = detect_superpowers()
    if sp_detected is True:
        steps.append(CompanionStep("companion superpowers", "ok", "plugin/extension present"))
    elif not resolved and not all_star:
        steps.append(
            CompanionStep(
                "companion superpowers",
                "manual",
                f"pick --agents, then install per harness · {SUPERPOWERS_REPO} · {COMPANIONS_DOC}",
            )
        )
    else:
        status_sp: Status = "missing" if sp_detected is False else "manual"
        steps.append(
            CompanionStep(
                "companion superpowers",
                status_sp,
                superpowers_manual_hint(resolved),
            )
        )

    # --- Context7 (MCP docs) ---
    c7 = detect_context7_mcp()
    if c7 is True:
        steps.append(
            CompanionStep(
                "companion context7",
                "ok",
                "MCP entry present · optional API key for higher limits",
            )
        )
    elif not resolved and not all_star:
        steps.append(
            CompanionStep(
                "companion context7",
                "manual",
                f"pick --agents, then Hub merges MCP (npx -y {CONTEXT7_MCP_PACKAGE}) · {CONTEXT7_REPO}",
            )
        )
    else:
        status_c7: Status = "missing" if c7 is False else "manual"
        steps.append(
            CompanionStep(
                "companion context7",
                status_c7,
                f"merge MCP via npx -y {CONTEXT7_MCP_PACKAGE} · optional API key · {COMPANIONS_DOC}",
            )
        )

    # --- agent-browser ---
    ab_bin = detect_agent_browser()
    ab_skill = detect_agent_browser_skill()
    if ab_bin and ab_skill is not False:
        steps.append(
            CompanionStep(
                "companion agent-browser",
                "ok",
                f"on PATH ({resolve_agent_browser_bin()})",
            )
        )
    elif not resolved and not all_star:
        steps.append(
            CompanionStep(
                "companion agent-browser",
                "manual",
                f"npm i -g agent-browser && agent-browser install · skills add · {AGENT_BROWSER_REPO}",
            )
        )
    else:
        status_ab: Status = "missing" if not ab_bin else "manual"
        steps.append(
            CompanionStep(
                "companion agent-browser",
                status_ab,
                f"npm i -g agent-browser; agent-browser install; "
                f"npx skills add {AGENT_BROWSER_SKILLS_SOURCE} -g -y … · {COMPANIONS_DOC}",
            )
        )

    # --- Serena ---
    serena_bin = detect_serena()
    serena_mcp = detect_serena_mcp()
    if serena_bin and serena_mcp is not False:
        steps.append(
            CompanionStep(
                "companion serena",
                "ok",
                f"on PATH ({resolve_serena_bin()})",
            )
        )
    elif not resolved and not all_star:
        steps.append(
            CompanionStep(
                "companion serena",
                "manual",
                f"uv tool install -p 3.13 serena-agent · serena init · MCP merge · {SERENA_REPO}",
            )
        )
    else:
        status_se: Status = "missing" if not serena_bin else "manual"
        steps.append(
            CompanionStep(
                "companion serena",
                status_se,
                f"uv tool install -p 3.13 serena-agent; serena init; merge MCP · {COMPANIONS_DOC}",
            )
        )

    # --- Ponytail (upstream per-agent; not skills.sh primary) ---
    pt = detect_ponytail()
    if pt is True:
        steps.append(
            CompanionStep(
                "companion ponytail",
                "ok",
                "plugin/hooks/clone present · mode is upstream-controlled",
            )
        )
    elif not resolved and not all_star:
        steps.append(
            CompanionStep(
                "companion ponytail",
                "manual",
                f"pick --agents, then install per harness · {PONYTAIL_REPO} · {COMPANIONS_DOC}",
            )
        )
    else:
        status_pt: Status = "missing" if pt is False else "manual"
        steps.append(
            CompanionStep(
                "companion ponytail",
                status_pt,
                ponytail_manual_hint(resolved),
            )
        )

    # --- Humanizer (skills.sh; invoke on demand — never auto post-process) ---
    hz = detect_humanizer()
    hz_cmds = humanizer_commands(resolved, all_star=all_star)
    if hz is True:
        steps.append(
            CompanionStep(
                "companion humanizer",
                "ok",
                "skill dir present · invoke /humanizer when rewriting prose",
            )
        )
    elif not resolved and not all_star:
        steps.append(
            CompanionStep(
                "companion humanizer",
                "manual",
                f"missing or unknown — pick --agents, then: "
                f"npx skills add {HUMANIZER_SOURCE} -g -y … · {COMPANIONS_DOC}",
            )
        )
    else:
        status_hz: Status = "missing" if hz is False else "manual"
        detail = "; ".join(hz_cmds) if hz_cmds else f"see {COMPANIONS_DOC}"
        prefix = "not detected" if hz is False else "unknown"
        steps.append(
            CompanionStep(
                "companion humanizer",
                status_hz,
                f"{prefix} — {detail}",
            )
        )

    return steps


def _run(command: list[str], *, dry_run: bool) -> tuple[Status, str]:
    line = " ".join(command)
    if dry_run:
        return "ok", f"would run: {line}"
    if not command:
        return "error", "empty command"
    first = command[0]
    if Path(first).is_file():
        resolved_bin = first
    else:
        resolved_bin = _which(first, f"{first}.cmd", f"{first}.exe")
    if not resolved_bin:
        return "error", f"not on PATH: {first} ({line})"
    command = [resolved_bin, *command[1:]]
    print_running(command, file=sys.stderr)
    code = subprocess.run(command, check=False).returncode
    if code == 0:
        return "ok", f"{line} (exit 0)"
    return "error", f"{line} (exit {code})"


def _optional_result(status: Status, detail: str) -> tuple[Status, str]:
    """Optional companions must not fail Hub connect — demote errors to warn."""
    if status == "error":
        return "warn", f"{detail} · Hub connect still succeeded"
    return status, detail


def _run_rtk_install_sh(*, dry_run: bool) -> tuple[Status, str]:
    """Download upstream RTK install.sh, then run the complete script.

    Download-then-exec avoids piping a live curl stream into ``sh`` (partial
    script risk). Bounded timeouts and exception conversion keep optional
    companion install from hanging or crashing Hub connect.
    """
    line = f"curl -fsSL {RTK_INSTALL_SH_URL} | sh"
    if dry_run:
        return "ok", f"would run: {line}"
    curl = _which("curl")
    sh = _which("sh") or _which("bash")
    if not curl:
        return "error", f"not on PATH: curl ({line})"
    if not sh:
        return "error", f"not on PATH: sh ({line})"
    print_running([curl, "-fsSL", RTK_INSTALL_SH_URL, "|", "sh"], file=sys.stderr)
    # Fixed upstream URL; argv lists only (no shell interpolation).
    try:
        with tempfile.TemporaryDirectory(prefix="adhd-hub-rtk-") as tmp:
            script = Path(tmp) / "install.sh"
            curl_code = subprocess.run(
                [
                    curl,
                    "-fsSL",
                    "--max-time",
                    "120",
                    "-o",
                    str(script),
                    RTK_INSTALL_SH_URL,
                ],
                check=False,
                timeout=150,
            ).returncode
            if curl_code != 0:
                return "error", f"{line} (curl exit {curl_code})"
            if not script.is_file() or script.stat().st_size == 0:
                return "error", f"{line} (empty install script)"
            code = subprocess.run(
                [sh, str(script)],
                check=False,
                timeout=600,
            ).returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "error", f"{line} ({exc})"
    if code == 0:
        return "ok", f"{line} (exit 0)"
    return "error", f"{line} (exit {code})"


def _try_install_rtk_binary(*, dry_run: bool) -> CompanionStep:
    """Best-effort RTK binary install: Homebrew when present, else upstream install.sh."""
    if sys.platform == "win32":
        return CompanionStep(
            "install rtk binary",
            "warn",
            f"{rtk_binary_hint()}. Hub connect still succeeded; install rtk, then "
            "re-run `adhd-hub connect . --with-rtk --agents cursor,codex`.",
        )

    brew = _which("brew")
    if brew:
        status, detail = _optional_result(*_run([brew, "install", "rtk"], dry_run=dry_run))
        if status == "ok" or dry_run:
            return CompanionStep("install rtk binary", status, detail)
        # Brew failed — fall through to install.sh (common on Linux without kegs).

    if not _which("curl"):
        return CompanionStep(
            "install rtk binary",
            "warn",
            "rtk not on PATH and curl not available for upstream install.sh — "
            f"{rtk_binary_hint()}. Hub connect still succeeded; install rtk, then "
            "re-run `adhd-hub connect . --with-rtk --agents cursor,codex`.",
        )

    status, detail = _optional_result(*_run_rtk_install_sh(dry_run=dry_run))
    return CompanionStep("install rtk binary", status, detail)


def _install_skills_sh_source(
    source: str,
    step_name: str,
    resolved: list[str],
    *,
    all_star: bool,
    has_agents: bool,
    dry_run: bool,
) -> list[CompanionStep]:
    """Shared opt-in ``npx skills add`` install for skills.sh companions."""
    if not has_agents:
        return [
            CompanionStep(
                step_name,
                "warn",
                "skipped — pass --agents (or *) for skills.sh targets · " + COMPANIONS_DOC,
            )
        ]
    if all_star:
        cmd = ["npx", "skills", "add", source, "-g", "-y", "--agent", "*"]
        status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
        return [CompanionStep(step_name, status, detail)]
    targets = normalize_skills_agents(resolved)
    if not targets:
        return [
            CompanionStep(
                step_name,
                "warn",
                "no skills.sh-mapped agents — install manually · " + COMPANIONS_DOC,
            )
        ]
    cmd = ["npx", "skills", "add", source, "-g", "-y"]
    for t in targets:
        cmd.extend(["-a", t])
    status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
    return [CompanionStep(step_name, status, detail)]


def _ensure_ponytail_clone(*, dry_run: bool) -> tuple[Status, str, Path | None]:
    """Clone or reuse Hub's managed Ponytail checkout (does not vendor into the Hub repo)."""
    dest = ponytail_clone_dir()
    marker = dest / "scripts" / "cursor-hooks.js"
    if marker.is_file():
        return "ok", f"found: {dest}", dest
    if dry_run:
        return "ok", f"would clone {PONYTAIL_REPO} → {dest}", dest
    git = _which("git", "git.exe")
    if not git:
        detail = (
            f"not on PATH: git (needed to clone {PONYTAIL_REPO_SLUG}) · "
            "Hub connect still succeeded"
        )
        return "warn", detail, None
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not marker.is_file():
        # Incomplete prior attempt — replace.
        shutil.rmtree(dest, ignore_errors=True)
    status, detail = _optional_result(
        *_run([git, "clone", "--depth", "1", PONYTAIL_REPO, str(dest)], dry_run=False)
    )
    if status != "ok" or not marker.is_file():
        return status, detail, None
    return "ok", detail, dest


def _install_ponytail(
    resolved: list[str],
    *,
    all_star: bool,
    has_agents: bool,
    dry_run: bool,
) -> list[CompanionStep]:
    """Upstream per-agent Ponytail install (plugins / Cursor hooks / Gemini)."""
    steps: list[CompanionStep] = []
    if not has_agents:
        steps.append(
            CompanionStep(
                "install ponytail",
                "warn",
                "skipped — pass --agents for harness-specific Ponytail install · "
                + COMPANIONS_DOC,
            )
        )
        return steps

    agents = list(STAR_COMPANION_AGENTS) if all_star else list(resolved)
    cursor_already = _cursor_hooks_mention_ponytail()
    need_clone = any(a == "cursor" for a in agents) and not (
        cursor_already and not dry_run
    )
    clone_path: Path | None = None
    if need_clone:
        status, detail, clone_path = _ensure_ponytail_clone(dry_run=dry_run)
        # Optional companion: never surface raw error (Hub connect must stay green).
        if status == "error":
            status, detail = _optional_result(status, detail)
        steps.append(CompanionStep("install ponytail clone", status, detail))

    for agent in agents:
        if agent == "cursor":
            # Upstream cursor-hooks.js merges into hooks.json; skip when already wired.
            if cursor_already and not dry_run:
                steps.append(
                    CompanionStep(
                        "install ponytail",
                        "ok",
                        "Cursor hooks already reference ponytail — left unchanged "
                        "(mode/activation remains upstream-controlled)",
                    )
                )
                continue
            node = _which("node", "node.exe")
            if not clone_path and not dry_run:
                steps.append(
                    CompanionStep(
                        "install ponytail",
                        "warn",
                        "Cursor hooks need a local clone — "
                        + ponytail_manual_hint(["cursor"]),
                    )
                )
                continue
            script = (clone_path or ponytail_clone_dir()) / "scripts" / "cursor-hooks.js"
            if not node and not dry_run:
                steps.append(
                    CompanionStep(
                        "install ponytail",
                        "warn",
                        "node not on PATH for Cursor hooks — "
                        + ponytail_manual_hint(["cursor"]),
                    )
                )
                continue
            cmd = [node or "node", str(script), "install"]
            status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
            detail = (
                f"{detail} · merges into ~/.cursor/hooks.json (does not replace "
                "unrelated hooks); mode/activation is upstream-controlled"
            )
            steps.append(CompanionStep("install ponytail", status, detail))
        elif agent == "codex":
            codex = _which("codex", "codex.exe")
            if not codex and not dry_run:
                steps.append(
                    CompanionStep(
                        "install ponytail",
                        "warn",
                        "codex CLI not on PATH — " + ponytail_manual_hint(["codex"]),
                    )
                )
                continue
            for cmd in (
                [codex or "codex", "plugin", "marketplace", "add", PONYTAIL_REPO_SLUG],
                [codex or "codex", "plugin", "add", "ponytail@ponytail"],
            ):
                status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
                steps.append(CompanionStep("install ponytail", status, detail))
            steps.append(
                CompanionStep(
                    "install ponytail",
                    "warn",
                    "Codex: open /hooks after install, trust Ponytail lifecycle hooks, "
                    f"start a new thread · {COMPANIONS_DOC}",
                )
            )
        elif agent == "claude":
            steps.append(
                CompanionStep(
                    "install ponytail",
                    "warn",
                    "Hub cannot run Claude Code /plugin interactively — "
                    + ponytail_manual_hint(["claude"]),
                )
            )
        elif agent == "gemini":
            gemini = _which("gemini", "gemini.exe")
            if gemini or dry_run:
                cmd = [
                    gemini or "gemini",
                    "extensions",
                    "install",
                    PONYTAIL_REPO,
                ]
                status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
                steps.append(CompanionStep("install ponytail", status, detail))
            else:
                steps.append(
                    CompanionStep(
                        "install ponytail",
                        "warn",
                        "gemini CLI not on PATH — " + ponytail_manual_hint(["gemini"]),
                    )
                )
        else:
            steps.append(
                CompanionStep(
                    "install ponytail",
                    "warn",
                    f"no auto recipe for {agent} — {ponytail_manual_hint([agent])}",
                )
            )
    return steps


def install_companions(
    agents: list[str] | None,
    *,
    with_i_have_adhd: bool = False,
    with_graphify: bool = False,
    with_rtk: bool = False,
    with_superpowers: bool = False,
    with_context7: bool = False,
    with_agent_browser: bool = False,
    with_serena: bool = False,
    with_ponytail: bool = False,
    with_humanizer: bool = False,
    dry_run: bool = False,
) -> list[CompanionStep]:
    """Opt-in companion installs keyed by selected agents."""
    enabled = resolve_enabled_companions(
        with_i_have_adhd=with_i_have_adhd,
        with_graphify=with_graphify,
        with_rtk=with_rtk,
        with_superpowers=with_superpowers,
        with_context7=with_context7,
        with_agent_browser=with_agent_browser,
        with_serena=with_serena,
        with_ponytail=with_ponytail,
        with_humanizer=with_humanizer,
    )
    if not any_companion_enabled(enabled):
        return []

    with_i_have_adhd = enabled["i-have-adhd"]
    with_graphify = enabled["graphify"]
    with_rtk = enabled["rtk"]
    with_superpowers = enabled["superpowers"]
    with_context7 = enabled["context7"]
    with_agent_browser = enabled["agent-browser"]
    with_serena = enabled["serena"]
    with_ponytail = enabled["ponytail"]
    with_humanizer = enabled["humanizer"]

    all_star, resolved = resolve_companion_agents(agents)
    steps: list[CompanionStep] = []
    has_agents = bool(resolved or all_star)

    if not has_agents:
        # Binary installs (RTK / Graphify) do not need agents; agent-specific
        # steps (init/register/skills/MCP) are skipped below with their own warns.
        steps.append(
            CompanionStep(
                "companions install",
                "warn",
                "No --agents selected — skipping agent-specific companion steps "
                "(binary installs that do not need agents still run). "
                f"Pass --agents cursor,codex,claude or see {COMPANIONS_DOC}",
            )
        )

    if with_i_have_adhd:
        steps.extend(
            _install_skills_sh_source(
                I_HAVE_ADHD_SOURCE,
                "install i-have-adhd",
                resolved,
                all_star=all_star,
                has_agents=has_agents,
                dry_run=dry_run,
            )
        )

    if with_graphify:
        if not detect_graphify():
            uv = _which("uv", "uv.exe")
            if not uv and not dry_run:
                steps.append(
                    CompanionStep(
                        "install graphify",
                        "warn",
                        "graphify not found and uv not on PATH — "
                        f"run: uv tool install graphifyy · {COMPANIONS_DOC}. "
                        "Hub connect still succeeded",
                    )
                )
            else:
                cmd = [uv or "uv", "tool", "install", "graphifyy"]
                status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
                steps.append(CompanionStep("install graphify binary", status, detail))
        else:
            steps.append(
                CompanionStep(
                    "install graphify binary",
                    "ok",
                    f"found: {resolve_graphify_bin()}",
                )
            )

        if not has_agents:
            steps.append(
                CompanionStep(
                    "install graphify register",
                    "warn",
                    "skipped — pass --agents to register Graphify · " + COMPANIONS_DOC,
                )
            )
        else:
            gbin = resolve_graphify_bin()
            register_cmds = graphify_register_commands(resolved, all_star=all_star)
            if not register_cmds:
                steps.append(
                    CompanionStep(
                        "install graphify register",
                        "warn",
                        f"no known Graphify recipe for selected agents — {COMPANIONS_DOC}",
                    )
                )
            elif not gbin and not dry_run:
                steps.append(
                    CompanionStep(
                        "install graphify register",
                        "warn",
                        "graphify installed but not found under PATH or ~/.local/bin — "
                        "run `uv tool update-shell`, open a new terminal, then: "
                        + "; ".join(register_cmds),
                    )
                )
            else:
                exe = gbin or "graphify"
                for line in register_cmds:
                    parts = line.split()
                    # Prefer absolute shim so register works before PATH refresh.
                    cmd = [exe, *parts[1:]] if parts else [exe]
                    status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
                    steps.append(CompanionStep("install graphify register", status, detail))

    if with_rtk:
        if not detect_rtk():
            steps.append(_try_install_rtk_binary(dry_run=dry_run))
        else:
            steps.append(
                CompanionStep("install rtk binary", "ok", f"found: {resolve_rtk_bin()}")
            )

        binary_ready = detect_rtk() or dry_run
        if not binary_ready:
            # Install step already warned; skip init without a binary.
            pass
        elif not has_agents:
            steps.append(
                CompanionStep(
                    "install rtk init",
                    "warn",
                    "rtk binary ready; pass --agents to run rtk init · " + COMPANIONS_DOC,
                )
            )
        else:
            rtk = resolve_rtk_bin() or "rtk"
            init_cmds = rtk_init_commands(resolved, all_star=all_star)
            if not init_cmds:
                steps.append(
                    CompanionStep(
                        "install rtk init",
                        "warn",
                        f"no known RTK recipe for selected agents — {COMPANIONS_DOC}",
                    )
                )
            for line in init_cmds:
                parts = line.split()
                cmd = [rtk, *parts[1:]] if parts else [rtk]
                status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
                detail = (
                    f"{detail} · telemetry opt-in only — leave disabled unless you consent"
                )
                steps.append(CompanionStep("install rtk init", status, detail))

    if with_superpowers:
        if not has_agents:
            steps.append(
                CompanionStep(
                    "install superpowers",
                    "warn",
                    "skipped — pass --agents for harness-specific Superpowers hints · "
                    + COMPANIONS_DOC,
                )
            )
        else:
            gemini_agents = [a for a in resolved if a == "gemini"]
            other_agents = [a for a in resolved if a != "gemini"]
            if gemini_agents and _which("gemini", "gemini.exe"):
                cmd = [
                    _which("gemini", "gemini.exe") or "gemini",
                    "extensions",
                    "install",
                    SUPERPOWERS_REPO,
                ]
                status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
                steps.append(CompanionStep("install superpowers", status, detail))
            hint_agents = (
                other_agents if gemini_agents and _which("gemini", "gemini.exe") else resolved
            )
            if hint_agents or not gemini_agents:
                steps.append(
                    CompanionStep(
                        "install superpowers",
                        "warn",
                        "Hub cannot fully auto-install Superpowers for most harnesses — "
                        + superpowers_manual_hint(hint_agents or resolved),
                    )
                )

    if with_context7:
        if not has_agents:
            steps.append(
                CompanionStep(
                    "install context7",
                    "warn",
                    "skipped — pass --agents to merge Context7 MCP · " + COMPANIONS_DOC,
                )
            )
        else:
            snippet = context7_mcp_snippet()
            targets: list[tuple[str, Path]] = []
            if "cursor" in resolved or all_star:
                targets.append(("cursor", Path.home() / ".cursor" / "mcp.json"))
            if "claude" in resolved or all_star:
                targets.append(("claude", Path.home() / ".claude" / "mcp.json"))
            if not targets and resolved and "codex" not in resolved and not all_star:
                steps.append(
                    CompanionStep(
                        "install context7",
                        "warn",
                        "no Cursor/Claude/Codex MCP path for selected agents — "
                        f"configure Context7 manually · {CONTEXT7_REPO}",
                    )
                )
            for label, mcp_path in targets:
                try:
                    action = merge_stdio_mcp_json(
                        mcp_path, "context7", snippet, dry_run=dry_run
                    )
                    steps.append(
                        CompanionStep(
                            "install context7",
                            "ok",
                            f"{label} MCP {action}: {mcp_path} · optional API key for higher limits",
                        )
                    )
                except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    steps.append(
                        CompanionStep(
                            "install context7",
                            "warn",
                            f"{label} MCP merge failed: {exc} · {CONTEXT7_REPO}",
                        )
                    )
            if "codex" in resolved or all_star:
                codex_path = Path.home() / ".codex" / "config.toml"
                try:
                    action = merge_codex_stdio_mcp(
                        codex_path,
                        "context7",
                        "npx",
                        ["-y", CONTEXT7_MCP_PACKAGE],
                        dry_run=dry_run,
                    )
                    steps.append(
                        CompanionStep(
                            "install context7",
                            "ok",
                            f"codex MCP {action}: {codex_path}",
                        )
                    )
                except (OSError, ValueError) as exc:
                    steps.append(
                        CompanionStep(
                            "install context7",
                            "warn",
                            f"codex MCP merge failed: {exc} · {CONTEXT7_REPO}",
                        )
                    )

    if with_agent_browser:
        if not detect_agent_browser():
            npm = _which("npm", "npm.cmd")
            if not npm and not dry_run:
                steps.append(
                    CompanionStep(
                        "install agent-browser binary",
                        "warn",
                        "agent-browser not found and npm not on PATH — "
                        f"run: npm i -g agent-browser · {AGENT_BROWSER_REPO}. "
                        "Hub connect still succeeded",
                    )
                )
            else:
                cmd = [npm or "npm", "install", "-g", "agent-browser"]
                status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
                steps.append(CompanionStep("install agent-browser binary", status, detail))
        else:
            steps.append(
                CompanionStep(
                    "install agent-browser binary",
                    "ok",
                    f"found: {resolve_agent_browser_bin()}",
                )
            )
        ab = resolve_agent_browser_bin()
        if ab or dry_run:
            cmd = [ab or "agent-browser", "install"]
            status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
            steps.append(CompanionStep("install agent-browser chromium", status, detail))
        elif not dry_run:
            steps.append(
                CompanionStep(
                    "install agent-browser chromium",
                    "warn",
                    "agent-browser installed but not found on PATH — "
                    "open a new terminal, then run: agent-browser install · "
                    f"{AGENT_BROWSER_REPO}",
                )
            )
        if all_star:
            cmd = [
                "npx",
                "skills",
                "add",
                AGENT_BROWSER_SKILLS_SOURCE,
                "-g",
                "-y",
                "--agent",
                "*",
            ]
            status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
            steps.append(CompanionStep("install agent-browser skill", status, detail))
        else:
            targets = normalize_skills_agents(resolved)
            if not targets:
                steps.append(
                    CompanionStep(
                        "install agent-browser skill",
                        "warn",
                        "no skills.sh-mapped agents — install skill manually · "
                        + COMPANIONS_DOC,
                    )
                )
            else:
                cmd = ["npx", "skills", "add", AGENT_BROWSER_SKILLS_SOURCE, "-g", "-y"]
                for t in targets:
                    cmd.extend(["-a", t])
                status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
                steps.append(CompanionStep("install agent-browser skill", status, detail))

    if with_serena:
        if not detect_serena():
            uv = _which("uv", "uv.exe")
            if not uv and not dry_run:
                steps.append(
                    CompanionStep(
                        "install serena",
                        "warn",
                        "serena not found and uv not on PATH — "
                        f"run: uv tool install -p 3.13 serena-agent · {SERENA_REPO}. "
                        "Hub connect still succeeded",
                    )
                )
            else:
                cmd = [uv or "uv", "tool", "install", "-p", "3.13", "serena-agent"]
                status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
                steps.append(CompanionStep("install serena binary", status, detail))
        else:
            steps.append(
                CompanionStep(
                    "install serena binary",
                    "ok",
                    f"found: {resolve_serena_bin()}",
                )
            )
        sbin = resolve_serena_bin()
        if sbin or dry_run:
            cmd = [sbin or "serena", "init"]
            status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
            steps.append(CompanionStep("install serena init", status, detail))
        snippet = serena_mcp_snippet(sbin)
        mcp_targets: list[tuple[str, Path]] = []
        if "cursor" in resolved or all_star:
            mcp_targets.append(("cursor", Path.home() / ".cursor" / "mcp.json"))
        if "claude" in resolved or all_star:
            mcp_targets.append(("claude", Path.home() / ".claude" / "mcp.json"))
        for label, mcp_path in mcp_targets:
            try:
                action = merge_stdio_mcp_json(
                    mcp_path, "serena", snippet, dry_run=dry_run
                )
                steps.append(
                    CompanionStep(
                        "install serena mcp",
                        "ok",
                        f"{label} MCP {action}: {mcp_path}",
                    )
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                steps.append(
                    CompanionStep(
                        "install serena mcp",
                        "warn",
                        f"{label} MCP merge failed: {exc} · {SERENA_REPO}",
                    )
                )
        if "codex" in resolved or all_star:
            codex_path = Path.home() / ".codex" / "config.toml"
            try:
                action = merge_codex_stdio_mcp(
                    codex_path,
                    "serena",
                    snippet["command"],
                    list(snippet["args"]),
                    dry_run=dry_run,
                )
                steps.append(
                    CompanionStep(
                        "install serena mcp",
                        "ok",
                        f"codex MCP {action}: {codex_path}",
                    )
                )
            except (OSError, ValueError) as exc:
                steps.append(
                    CompanionStep(
                        "install serena mcp",
                        "warn",
                        f"codex MCP merge failed: {exc} · {SERENA_REPO}",
                    )
                )

    if with_ponytail:
        steps.extend(
            _install_ponytail(
                resolved,
                all_star=all_star,
                has_agents=has_agents,
                dry_run=dry_run,
            )
        )

    if with_humanizer:
        hz_steps = _install_skills_sh_source(
            HUMANIZER_SOURCE,
            "install humanizer",
            resolved,
            all_star=all_star,
            has_agents=has_agents,
            dry_run=dry_run,
        )
        note = (
            " · on-demand skill only — Hub does not auto-rewrite prose or code"
        )
        steps.extend(
            CompanionStep(s.name, s.status, s.detail + note) if has_agents else s
            for s in hz_steps
        )

    return steps


def append_companion_steps(
    report_add,
    agents: list[str] | None,
    *,
    with_i_have_adhd: bool = False,
    with_graphify: bool = False,
    with_rtk: bool = False,
    with_superpowers: bool = False,
    with_context7: bool = False,
    with_agent_browser: bool = False,
    with_serena: bool = False,
    with_ponytail: bool = False,
    with_humanizer: bool = False,
    dry_run: bool = False,
) -> None:
    """Add recommend (+ optional install) steps via ``report.add(name, status, detail)``."""
    enabled = resolve_enabled_companions(
        with_i_have_adhd=with_i_have_adhd,
        with_graphify=with_graphify,
        with_rtk=with_rtk,
        with_superpowers=with_superpowers,
        with_context7=with_context7,
        with_agent_browser=with_agent_browser,
        with_serena=with_serena,
        with_ponytail=with_ponytail,
        with_humanizer=with_humanizer,
    )
    installing = {f"companion {cid}": on for cid, on in enabled.items()}
    for step in recommend_companions(agents):
        # Avoid stale "missing" lines when this run is about to install that tool.
        if (
            installing.get(step.name)
            and step.status in {"missing", "manual"}
            and step.name.startswith("companion ")
        ):
            report_add(
                step.name,
                "skipped",
                f"installing on this run ({step.detail})",
            )
            continue
        report_add(step.name, step.status, step.detail)
    for step in install_companions(
        agents,
        with_i_have_adhd=with_i_have_adhd,
        with_graphify=with_graphify,
        with_rtk=with_rtk,
        with_superpowers=with_superpowers,
        with_context7=with_context7,
        with_agent_browser=with_agent_browser,
        with_serena=with_serena,
        with_ponytail=with_ponytail,
        with_humanizer=with_humanizer,
        dry_run=dry_run,
    ):
        report_add(step.name, step.status, step.detail)
