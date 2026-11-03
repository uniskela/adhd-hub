"""Agent registrations and diagnostics shared by connect and the agents commands."""

from __future__ import annotations

import os
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any

from adhd_hub.connect import (
    CURSOR_MCP_KEY,
    ConnectReport,
    _read_json,
    claude_user_mcp_path,
    codex_config_path,
    cursor_user_mcp_path,
    mcp_url_for,
    merge_claude_mcp,
    merge_codex_mcp,
    merge_cursor_mcp,
    normalize_hub_url,
)
from adhd_hub.mcp_probe import probe_mcp, validate_mcp_url

AGENTS = ("codex", "claude", "cursor")


def agent_executable(agent: str) -> str | None:
    candidates = {
        "codex": ("codex",),
        "claude": ("claude",),
        "cursor": ("cursor", "cursor-agent", "agent"),
    }[agent]
    return next((path for name in candidates if (path := shutil.which(name))), None)


def select_agents(raw: str, *, non_interactive: bool = False) -> list[str]:
    selected = [a.strip().lower() for a in raw.split(",") if a.strip()]
    if selected:
        return list(dict.fromkeys("claude" if a == "claude-code" else a for a in selected))
    detected = [a for a in AGENTS if agent_executable(a)]
    if non_interactive or not sys.stdin.isatty():
        raise ValueError(
            "No agents selected. Pass --agents codex,claude,cursor "
            "(detected: " + (",".join(detected) or "none on PATH") + ")."
        )
    print("Detected on PATH: " + (", ".join(detected) or "none"))
    answer = input("Agents to configure (comma list) [" + ",".join(detected) + "]: ").strip()
    return select_agents(answer or ",".join(detected), non_interactive=True)


def config_paths(agent: str, project: Path | None) -> list[tuple[str, Path]]:
    user = {
        "cursor": cursor_user_mcp_path,
        "codex": codex_config_path,
        "claude": claude_user_mcp_path,
    }[agent]()
    paths = [("user", user)]
    if project is not None:
        relative = {
            "cursor": ".cursor/mcp.json",
            "codex": ".codex/config.toml",
            "claude": ".mcp.json",
        }[agent]
        paths.append(("project", project / relative))
        if agent == "codex":
            for parent in project.parents:
                path = parent / relative
                if path != user:
                    paths.append(("ancestor", path))
                if (parent / ".git").exists():
                    break
    return list(dict.fromkeys(paths))


def read_registration(agent: str, path: Path) -> Any:
    if not path.exists():
        return None
    if agent == "codex":
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        servers = data.get("mcp_servers", {})
    else:
        servers = _read_json(path).get("mcpServers", {})
    if not isinstance(servers, dict):
        raise TypeError("MCP servers must be an object")
    return servers.get(CURSOR_MCP_KEY)


def registrations(agent: str, project: Path | None) -> list[tuple[str, Path, Any]]:
    entries = [
        (scope, path, read_registration(agent, path))
        for scope, path in config_paths(agent, project)
    ]
    if agent == "claude" and project is not None:
        path = claude_user_mcp_path()
        projects = _read_json(path).get("projects", {})
        if not isinstance(projects, dict):
            raise ValueError("Claude projects must be an object")
        local = projects.get(str(project), {})
        if not isinstance(local, dict) or not isinstance(local.get("mcpServers", {}), dict):
            raise ValueError("Claude local MCP servers must be an object")
        if entry := local.get("mcpServers", {}).get(CURSOR_MCP_KEY):
            entries.append(("local", path, entry))
    return entries


def setup_agents(
    *,
    hub_url: str,
    agents: list[str],
    scope: str = "user",
    project: Path | None = None,
    dry_run: bool = False,
) -> ConnectReport:
    hub_url = normalize_hub_url(hub_url)
    report = ConnectReport(hub_url=hub_url, dry_run=dry_run)
    try:
        validate_mcp_url(mcp_url_for(hub_url))
    except ValueError:
        report.add("hub", "error", "Use a valid HTTPS Hub URL (HTTP is allowed only on loopback)")
        return report
    if scope not in {"user", "project"} or (scope == "project" and project is None):
        report.add("agents", "error", "--scope project requires --project /path/to/project")
        return report
    if project is not None:
        project = project.expanduser().resolve()
        if not project.is_dir():
            report.add("project", "error", "project must be an accessible directory")
            return report
    if not agents:
        report.add("agents", "error", "No targets: pass --agents codex,claude,cursor")
        return report
    for agent in agents:
        if agent not in AGENTS:
            report.add("agents", "error", "Supported MCP targets: codex,claude,cursor")
            continue
        executable = agent_executable(agent)
        report.add(
            f"{agent} executable",
            "ok" if executable else "warn",
            "detected on PATH"
            if executable
            else "not installed or not on this process's PATH; add the agent executable directory",
        )
        try:
            entries = registrations(agent, project)
            path = next(path for location, path, _ in entries if location == scope)
            conflicts = [
                (location, p)
                for location, p, entry in entries
                if entry is not None and (p != path or location == "local")
            ]
            if conflicts:
                report.add(
                    f"{agent} MCP",
                    "error",
                    "scope conflict: adhd-hub already exists in "
                    + ", ".join(f"{s}: {p}" for s, p in conflicts)
                    + "; use that scope or remove the redundant entry after review",
                )
                continue
            merge = {
                "cursor": merge_cursor_mcp,
                "codex": merge_codex_mcp,
                "claude": merge_claude_mcp,
            }[agent]
            action = merge(path, hub_url, dry_run=dry_run)
            report.add(
                f"{agent} MCP ({scope})",
                "ok",
                f"{action}: {path}; "
                "environment bearer for new registrations; existing authentication preserved",
            )
        except (OSError, ValueError, TypeError) as exc:
            # Parser exceptions can include literal credential values.
            report.add(
                f"{agent} MCP",
                "error",
                f"Cannot safely update configuration ({type(exc).__name__}); "
                "inspect custom authentication, transport, syntax and file permissions",
            )
    report.add(
        "agent authentication",
        "warn",
        "ADHD_HUB_AUTH_TOKEN: "
        + ("SET" if _env_token() else "MISSING")
        + "; CLI login does not populate agent environments. Existing OAuth/custom auth is preserved.",
    )
    from shlex import join

    command = join(
        [
            "adhd-hub",
            "agents",
            "doctor",
            "--hub",
            hub_url,
            "--agents",
            ",".join(agents),
            "--scope",
            scope,
            *(["--project", str(project)] if project else []),
        ]
    )
    report.add(
        "agent runtime",
        "warn",
        "Runtime verification not available: no agent was launched. "
        "Restart selected agents, then run: " + command,
    )
    return report


def _env_token() -> str | None:
    token = (os.environ.get("ADHD_HUB_AUTH_TOKEN") or "").strip()
    return token if token and token != "change-me" else None


def _auth_mode(agent: str, entry: dict[str, Any]) -> tuple[str, str | None]:
    if "command" in entry:
        return "local stdio (not probed)", None
    if entry.get("type") not in (None, "http"):
        return "custom transport (not probed)", None
    if agent == "codex":
        if any(k in entry for k in ("http_headers", "env_http_headers", "http_headers_helper")):
            return "custom authentication (not probed)", None
        if entry.get("bearer_token_env_var") == "ADHD_HUB_AUTH_TOKEN":
            return "environment bearer", _env_token()
        if entry.get("bearer_token_env_var"):
            return "custom authentication (not probed)", None
    else:
        headers = entry.get("headers", {})
        expected = (
            "Bearer ${ADHD_HUB_AUTH_TOKEN}"
            if agent == "claude"
            else "Bearer ${env:ADHD_HUB_AUTH_TOKEN}"
        )
        if headers == {"Authorization": expected}:
            return "environment bearer", _env_token()
        alternate = (
            "Bearer ${env:ADHD_HUB_AUTH_TOKEN}"
            if agent == "claude"
            else "Bearer ${ADHD_HUB_AUTH_TOKEN}"
        )
        if isinstance(headers, dict) and headers.get("Authorization") == alternate:
            return "invalid environment interpolation", None
        if headers or entry.get("auth"):
            return "custom authentication (not probed)", None
    return "client OAuth (not available to this CLI)", None


def diagnose_agents(
    *,
    hub_url: str,
    agents: list[str] | None = None,
    scope: str | None = None,
    project: Path | None = None,
    probe: bool = True,
) -> ConnectReport:
    hub_url = normalize_hub_url(hub_url)
    report = ConnectReport(hub_url=hub_url)
    project = project.expanduser().resolve() if project is not None else None
    report.add("diagnostic context", "ok", f"HOME: {Path.home()} · project: {project or '(none)'}")
    report.add(
        "service environment",
        "warn",
        "Checks use this process's HOME/PATH/environment. "
        "A systemd EnvironmentFile is not inherited by SSH or a diagnostic shell. "
        "Run as the service account from an accessible directory with its injected environment; "
        "this command never reads service environment files.",
    )
    cache: dict[tuple[str, bool], dict[str, Any]] = {}
    targets = agents if agents is not None else AGENTS
    for agent in dict.fromkeys("claude" if a == "claude-code" else a for a in targets):
        if agent not in AGENTS:
            report.add("agents", "error", "Supported MCP targets: codex,claude,cursor")
            continue
        row: dict[str, Any] = {
            "agent": agent,
            "installed": bool(agent_executable(agent)),
            "credentials": "MISSING",
            "configured": False,
            "runtime_verification": "not available",
            "registrations": [],
        }
        report.agent_status.append(row)
        label = f"{agent} MCP"
        try:
            entries = []
            seen = set()
            for s, p, e in registrations(agent, project):
                key = (p, s == "local")
                if e is not None and key not in seen:
                    entries.append((s, p, e))
                    seen.add(key)
            row["registrations"] = [{"scope": s, "path": str(p)} for s, p, _ in entries]
            row["configured"] = bool(entries)
            if not row["installed"]:
                report.add(f"{agent} executable", "warn", "not installed or not on PATH")
            if len(entries) > 1:
                report.add(
                    label,
                    "error",
                    "scope conflict: multiple adhd-hub registrations; "
                    "review registrations and remove redundant entries",
                )
                row["state"] = "scope conflict"
                continue
            if scope:
                entries = [item for item in entries if item[0] == scope]
            if not entries:
                row["state"] = "not configured"
                report.add(
                    label,
                    "error",
                    "not configured in requested scope; run adhd-hub agents setup "
                    f"--agents {agent} --scope {scope or 'user'}",
                )
                continue
            location, path, entry = entries[0]
            if not isinstance(entry, dict):
                raise TypeError("invalid registration")
            mode, credential = _auth_mode(agent, entry)
            row["authentication_method"] = mode
            if entry.get("enabled") is False or entry.get("disabled") is True:
                row["state"] = "disabled"
                report.add(
                    label,
                    "error",
                    "adhd-hub registration is disabled; enable it in the client config",
                )
                continue
            row["credentials"] = "SET" if credential else "MISSING"
            row["state"] = "configured"
            report.add(label + f" ({location})", "ok", str(path))
            if mode == "invalid environment interpolation":
                report.add(
                    label + " auth",
                    "error",
                    "invalid environment interpolation; "
                    "preview: adhd-hub agents repair --agents " + agent,
                )
                row["state"] = "invalid configuration"
                continue
            if mode == "local stdio (not probed)":
                report.add(
                    label + " transport", "warn", mode + "; runtime verification not available"
                )
                continue
            if entry.get("url") != mcp_url_for(hub_url):
                report.add(
                    label + " URL",
                    "error",
                    "configured URL differs from intended --hub; "
                    "inspect configuration before repair",
                )
                row["state"] = "different endpoint or transport"
                continue
            validate_mcp_url(entry["url"])
            if mode == "environment bearer" and not credential:
                report.add(
                    label + " auth",
                    "error",
                    "configured but ADHD_HUB_AUTH_TOKEN: MISSING. "
                    "Inject it into the agent launch environment or configure client OAuth.",
                )
                row["state"] = "configured but missing credentials"
            elif not credential:
                report.add(label + " auth", "warn", mode + "; runtime verification not available")
            if probe and mode == "environment bearer":
                key = (entry["url"], bool(credential))
                if key not in cache:
                    cache[key] = probe_mcp(entry["url"], token=credential)
                result = cache[key]
                row["mcp"] = result
                success = result["tools_discovered"]
                report.add(
                    label + " direct HTTP",
                    "ok" if success else "error" if credential else "warn",
                    result["detail"] + "; no agent was launched",
                )
                if success and not (mode == "environment bearer" and not credential):
                    row["state"] = "MCP tools successfully discovered by direct HTTP"
            elif not probe:
                report.add(label + " direct HTTP", "skipped", "not probed")
        except (OSError, ValueError, TypeError) as exc:
            row["state"] = "invalid or unreadable configuration"
            report.add(
                label,
                "error",
                f"Cannot safely inspect configuration ({type(exc).__name__}); "
                "check syntax, HTTPS URL and file permissions",
            )
        if agent == "claude" and (Path.home() / ".claude/mcp.json").exists():
            report.add(
                "claude legacy path",
                "warn",
                "~/.claude/mcp.json is not a Claude Code "
                "user registration; run agents setup --agents claude --scope user",
            )
    return report
