"""Optional coding companions: detect, recommend, and opt-in install.

Companions (i-have-adhd, Graphify, RTK) are independent of ADHD Hub.
Install recipes follow the agents selected for connect.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from adhd_hub.cli_style import print_running
from adhd_hub.project_setup import normalize_skills_agents

COMPANIONS_DOC = "https://github.com/uniskela/adhd-hub/blob/main/docs/coding-companions.md"
I_HAVE_ADHD_SOURCE = "ayghri/i-have-adhd"

# Agents we emit concrete recipes for when the user passes ``*``.
STAR_COMPANION_AGENTS = ("cursor", "codex", "claude", "gemini")

# Only these get concrete Graphify / RTK recipes; others stay manual + docs.
GRAPHIFY_KNOWN_AGENTS = frozenset(STAR_COMPANION_AGENTS)
RTK_KNOWN_AGENTS = frozenset(STAR_COMPANION_AGENTS)
SKILLS_KNOWN_AGENTS = frozenset({"cursor", "codex", "claude"})  # via skills.sh mapping

Status = Literal["ok", "missing", "manual", "warn", "error", "skipped"]


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


def detect_i_have_adhd() -> bool | None:
    """Best-effort: True if a known skill dir exists, False if none, None if unknown."""
    home = Path.home()
    candidates = [
        home / ".cursor" / "skills" / "i-have-adhd",
        home / ".agents" / "skills" / "i-have-adhd",
        home / ".claude" / "skills" / "i-have-adhd",
        home / ".codex" / "skills" / "i-have-adhd",
        home / ".copilot" / "skills" / "i-have-adhd",
        home / ".hermes" / "skills" / "i-have-adhd",
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
    return "brew install rtk   # or upstream install.sh — see coding-companions.md"


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


def _try_install_rtk_binary(*, dry_run: bool) -> CompanionStep | None:
    """Best-effort RTK binary install when brew is available; otherwise None."""
    brew = _which("brew")
    if brew:
        status, detail = _optional_result(*_run([brew, "install", "rtk"], dry_run=dry_run))
        return CompanionStep("install rtk binary", status, detail)
    return None


def install_companions(
    agents: list[str] | None,
    *,
    with_i_have_adhd: bool = False,
    with_graphify: bool = False,
    with_rtk: bool = False,
    dry_run: bool = False,
) -> list[CompanionStep]:
    """Opt-in companion installs keyed by selected agents."""
    if not (with_i_have_adhd or with_graphify or with_rtk):
        return []

    all_star, resolved = resolve_companion_agents(agents)
    steps: list[CompanionStep] = []

    if not resolved and not all_star:
        steps.append(
            CompanionStep(
                "companions install",
                "warn",
                "No --agents selected — refusing agent-specific companion install. "
                f"Pass --agents or see {COMPANIONS_DOC}",
            )
        )
        return steps

    if with_i_have_adhd:
        if all_star:
            cmd = ["npx", "skills", "add", I_HAVE_ADHD_SOURCE, "-g", "-y", "--agent", "*"]
            status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
            steps.append(CompanionStep("install i-have-adhd", status, detail))
        else:
            targets = normalize_skills_agents(resolved)
            if not targets:
                steps.append(
                    CompanionStep(
                        "install i-have-adhd",
                        "warn",
                        "no skills.sh-mapped agents — install manually · " + COMPANIONS_DOC,
                    )
                )
            else:
                cmd = ["npx", "skills", "add", I_HAVE_ADHD_SOURCE, "-g", "-y"]
                for t in targets:
                    cmd.extend(["-a", t])
                status, detail = _optional_result(*_run(cmd, dry_run=dry_run))
                steps.append(CompanionStep("install i-have-adhd", status, detail))

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
            attempted = _try_install_rtk_binary(dry_run=dry_run)
            if attempted:
                steps.append(attempted)
            if not detect_rtk() and not dry_run:
                # Optional companion — do not fail the whole Hub connect.
                steps.append(
                    CompanionStep(
                        "install rtk binary",
                        "warn",
                        f"rtk not on PATH — {rtk_binary_hint()}. "
                        "Hub connect still succeeded; install rtk, then re-run "
                        "`adhd-hub connect … --with-rtk`.",
                    )
                )
                return steps
            if dry_run and not detect_rtk():
                steps.append(
                    CompanionStep(
                        "install rtk binary",
                        "warn",
                        f"would need binary first: {rtk_binary_hint()}",
                    )
                )
        else:
            steps.append(
                CompanionStep("install rtk binary", "ok", f"found: {resolve_rtk_bin()}")
            )

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

    return steps


def append_companion_steps(
    report_add,
    agents: list[str] | None,
    *,
    with_i_have_adhd: bool = False,
    with_graphify: bool = False,
    with_rtk: bool = False,
    dry_run: bool = False,
) -> None:
    """Add recommend (+ optional install) steps via ``report.add(name, status, detail)``."""
    installing = {
        "companion i-have-adhd": with_i_have_adhd,
        "companion graphify": with_graphify,
        "companion rtk": with_rtk,
    }
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
        dry_run=dry_run,
    ):
        report_add(step.name, step.status, step.detail)
