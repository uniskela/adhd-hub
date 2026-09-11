"""Hub-owned agent guidance / skill version health (local FS checks only)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

# Independent from package release version (pyproject). Bump only when Hub-owned
# generated guidance or Hub-owned skill contracts change meaningfully.
AGENT_GUIDANCE_VERSION = 2  # thread-outcome model + structured upsert_progress
SESSION_SKILL_VERSION = 2
PROJECTS_SKILL_VERSION = 2
CURSOR_RULE_VERSION = 2

BEGIN_MARKER = "<!-- adhd-hub:project-agent:start -->"
END_MARKER = "<!-- adhd-hub:project-agent:end -->"
VERSION_MARKER_RE = re.compile(
    r"<!--\s*adhd-hub:guidance-version:(\d+)\s*-->",
    re.IGNORECASE,
)
HUB_SKILL_VERSION_RE = re.compile(
    r"(?m)^hub_skill_version:\s*(\d+)\s*$",
)
HUB_RULE_VERSION_RE = re.compile(
    r"(?m)^hub_guidance_version:\s*(\d+)\s*$",
)

HUB_OWNED_SKILLS: dict[str, int] = {
    "adhd-hub-session": SESSION_SKILL_VERSION,
    "adhd-hub-projects": PROJECTS_SKILL_VERSION,
}


class GuidanceStatus(StrEnum):
    current = "current"
    outdated = "outdated"
    missing = "missing"
    malformed = "malformed"
    locally_modified = "locally_modified"
    not_applicable = "not_applicable"


@dataclass(frozen=True)
class ComponentHealth:
    name: str
    status: GuidanceStatus
    installed_version: int | None
    expected_version: int | None
    detail: str
    path: Path | None = None

    @property
    def needs_repair(self) -> bool:
        return self.status in {
            GuidanceStatus.outdated,
            GuidanceStatus.missing,
            GuidanceStatus.malformed,
            GuidanceStatus.locally_modified,
        }


def version_marker(version: int) -> str:
    return f"<!-- adhd-hub:guidance-version:{version} -->"


def parse_guidance_version(managed_body: str) -> int | None:
    match = VERSION_MARKER_RE.search(managed_body)
    if not match:
        return None
    return int(match.group(1))


def _normalize_managed_body(body: str) -> str:
    """Strip volatile whitespace for comparison; keep version marker."""
    lines = [line.rstrip() for line in body.strip().splitlines()]
    return "\n".join(lines).strip() + "\n"


def managed_body_fingerprint(body: str) -> str:
    return hashlib.sha256(_normalize_managed_body(body).encode("utf-8")).hexdigest()[:16]


def split_agents_file(text: str) -> tuple[str, str | None, str] | tuple[None, None, None]:
    """Return (before, managed_inner_including_markers_content, after) or Nones if absent.

    managed portion is the text BETWEEN markers (exclusive of markers).
    """
    has_begin = BEGIN_MARKER in text
    has_end = END_MARKER in text
    if has_begin != has_end:
        return None, None, None  # malformed sentinel via caller
    if not has_begin:
        return "", None, text
    before, remainder = text.split(BEGIN_MARKER, 1)
    managed, after = remainder.split(END_MARKER, 1)
    return before, managed, after


def inspect_agents_md(project_dir: Path, *, expected_body: str) -> ComponentHealth:
    path = project_dir.expanduser().resolve() / "AGENTS.md"
    expected_inner = expected_body
    if BEGIN_MARKER in expected_body and END_MARKER in expected_body:
        expected_inner = expected_body.split(BEGIN_MARKER, 1)[1].split(END_MARKER, 1)[0]
    expected_version = parse_guidance_version(expected_inner) or AGENT_GUIDANCE_VERSION

    if not path.is_file():
        return ComponentHealth(
            name="AGENTS.md guidance",
            status=GuidanceStatus.missing,
            installed_version=None,
            expected_version=expected_version,
            detail="managed block missing",
            path=path,
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return ComponentHealth(
            name="AGENTS.md guidance",
            status=GuidanceStatus.malformed,
            installed_version=None,
            expected_version=expected_version,
            detail=str(exc),
            path=path,
        )

    has_begin = BEGIN_MARKER in text
    has_end = END_MARKER in text
    if has_begin != has_end:
        return ComponentHealth(
            name="AGENTS.md guidance",
            status=GuidanceStatus.malformed,
            installed_version=None,
            expected_version=expected_version,
            detail="incomplete markers — will not rewrite until fixed",
            path=path,
        )
    if not has_begin:
        return ComponentHealth(
            name="AGENTS.md guidance",
            status=GuidanceStatus.missing,
            installed_version=None,
            expected_version=expected_version,
            detail="managed block missing",
            path=path,
        )

    _before, managed, _after = split_agents_file(text)
    assert managed is not None
    installed = parse_guidance_version(managed)
    expected_norm = _normalize_managed_body(expected_inner)
    installed_norm = _normalize_managed_body(managed)

    if installed is None:
        return ComponentHealth(
            name="AGENTS.md guidance",
            status=GuidanceStatus.outdated,
            installed_version=None,
            expected_version=expected_version,
            detail=f"unversioned block (pre-v{expected_version}); expected v{expected_version}",
            path=path,
        )
    if installed < expected_version:
        return ComponentHealth(
            name="AGENTS.md guidance",
            status=GuidanceStatus.outdated,
            installed_version=installed,
            expected_version=expected_version,
            detail=f"v{installed}, current v{expected_version}",
            path=path,
        )
    if installed > expected_version:
        return ComponentHealth(
            name="AGENTS.md guidance",
            status=GuidanceStatus.locally_modified,
            installed_version=installed,
            expected_version=expected_version,
            detail=f"newer than this Hub (v{installed} > v{expected_version})",
            path=path,
        )
    if installed_norm != expected_norm:
        return ComponentHealth(
            name="AGENTS.md guidance",
            status=GuidanceStatus.locally_modified,
            installed_version=installed,
            expected_version=expected_version,
            detail=f"v{installed} present but body differs from Hub template",
            path=path,
        )
    return ComponentHealth(
        name="AGENTS.md guidance",
        status=GuidanceStatus.current,
        installed_version=installed,
        expected_version=expected_version,
        detail=f"current (v{installed})",
        path=path,
    )


def inspect_cursor_rule(project_dir: Path, *, expected_content: str) -> ComponentHealth:
    path = project_dir.expanduser().resolve() / ".cursor" / "rules" / "adhd-hub.mdc"
    expected_version = parse_rule_version(expected_content) or CURSOR_RULE_VERSION
    if not path.is_file():
        return ComponentHealth(
            name="Cursor rule",
            status=GuidanceStatus.missing,
            installed_version=None,
            expected_version=expected_version,
            detail="Hub Cursor rule not installed",
            path=path,
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return ComponentHealth(
            name="Cursor rule",
            status=GuidanceStatus.malformed,
            installed_version=None,
            expected_version=expected_version,
            detail=str(exc),
            path=path,
        )
    installed = parse_rule_version(text)
    if installed is None:
        return ComponentHealth(
            name="Cursor rule",
            status=GuidanceStatus.outdated,
            installed_version=None,
            expected_version=expected_version,
            detail=f"unversioned rule; expected v{expected_version}",
            path=path,
        )
    if installed < expected_version:
        return ComponentHealth(
            name="Cursor rule",
            status=GuidanceStatus.outdated,
            installed_version=installed,
            expected_version=expected_version,
            detail=f"v{installed}, current v{expected_version}",
            path=path,
        )
    if _normalize_managed_body(text) != _normalize_managed_body(expected_content):
        return ComponentHealth(
            name="Cursor rule",
            status=GuidanceStatus.locally_modified,
            installed_version=installed,
            expected_version=expected_version,
            detail=f"v{installed} present but content differs",
            path=path,
        )
    return ComponentHealth(
        name="Cursor rule",
        status=GuidanceStatus.current,
        installed_version=installed,
        expected_version=expected_version,
        detail=f"current (v{installed})",
        path=path,
    )


def parse_rule_version(text: str) -> int | None:
    match = HUB_RULE_VERSION_RE.search(text)
    return int(match.group(1)) if match else None


def parse_skill_version(text: str) -> int | None:
    match = HUB_SKILL_VERSION_RE.search(text)
    return int(match.group(1)) if match else None


def hub_skill_search_roots(project_dir: Path | None = None) -> list[Path]:
    home = Path.home()
    roots = [
        home / ".agents" / "skills",
        home / ".claude" / "skills",
        home / ".codex" / "skills",
        home / ".cursor" / "skills-cursor",  # unlikely for hub skills; harmless
    ]
    if project_dir is not None:
        root = project_dir.expanduser().resolve()
        roots.extend(
            [
                root / ".agents" / "skills",
                root / "skills",
            ]
        )
    return roots


def find_hub_skill_file(skill_name: str, project_dir: Path | None = None) -> Path | None:
    for root in hub_skill_search_roots(project_dir):
        candidate = root / skill_name / "SKILL.md"
        if candidate.is_file():
            return candidate
    return None


def inspect_hub_skill(
    skill_name: str,
    *,
    expected_version: int,
    project_dir: Path | None = None,
) -> ComponentHealth:
    path = find_hub_skill_file(skill_name, project_dir)
    label = f"{skill_name} skill"
    if path is None:
        return ComponentHealth(
            name=label,
            status=GuidanceStatus.missing,
            installed_version=None,
            expected_version=expected_version,
            detail="not found in known skill directories",
            path=None,
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return ComponentHealth(
            name=label,
            status=GuidanceStatus.malformed,
            installed_version=None,
            expected_version=expected_version,
            detail=str(exc),
            path=path,
        )
    installed = parse_skill_version(text)
    if installed is None:
        return ComponentHealth(
            name=label,
            status=GuidanceStatus.outdated,
            installed_version=None,
            expected_version=expected_version,
            detail=f"unversioned install at {path}; expected v{expected_version}",
            path=path,
        )
    if installed < expected_version:
        return ComponentHealth(
            name=label,
            status=GuidanceStatus.outdated,
            installed_version=installed,
            expected_version=expected_version,
            detail=f"v{installed}, current v{expected_version}",
            path=path,
        )
    if installed > expected_version:
        return ComponentHealth(
            name=label,
            status=GuidanceStatus.locally_modified,
            installed_version=installed,
            expected_version=expected_version,
            detail=f"newer than this Hub (v{installed} > v{expected_version})",
            path=path,
        )
    return ComponentHealth(
        name=label,
        status=GuidanceStatus.current,
        installed_version=installed,
        expected_version=expected_version,
        detail=f"current (v{installed})",
        path=path,
    )


def inspect_project_continuity(
    project_dir: Path,
    *,
    expected_agents_block: str,
    expected_cursor_rule: str,
    check_skills: bool = True,
) -> list[ComponentHealth]:
    items = [
        inspect_agents_md(project_dir, expected_body=expected_agents_block),
        inspect_cursor_rule(project_dir, expected_content=expected_cursor_rule),
    ]
    if check_skills:
        for name, version in HUB_OWNED_SKILLS.items():
            items.append(
                inspect_hub_skill(name, expected_version=version, project_dir=project_dir)
            )
    return items


def repair_hint(items: list[ComponentHealth]) -> list[str]:
    hints: list[str] = []
    agents = next((i for i in items if i.name.startswith("AGENTS.md")), None)
    rule = next((i for i in items if i.name == "Cursor rule"), None)
    skills_stale = [i for i in items if i.name.endswith(" skill") and i.needs_repair]
    if agents and agents.needs_repair and agents.status != GuidanceStatus.malformed:
        hints.append("adhd-hub setup . --refresh")
    if agents and agents.status == GuidanceStatus.malformed:
        hints.append("Fix incomplete AGENTS.md markers, then: adhd-hub setup . --refresh")
    if rule and rule.needs_repair:
        hints.append("adhd-hub connect . --cursor-rule  (or setup + connect for full wire-up)")
    if skills_stale:
        hints.append("adhd-hub setup . --install-skills   # opt-in; Hub-owned skills only")
    return hints


def expected_versions_payload() -> dict[str, int]:
    return {
        "agent_guidance_version": AGENT_GUIDANCE_VERSION,
        "session_skill_version": SESSION_SKILL_VERSION,
        "projects_skill_version": PROJECTS_SKILL_VERSION,
        "cursor_rule_version": CURSOR_RULE_VERSION,
    }


def guidance_digest_payload(
    *,
    last_verified: dict | None = None,
) -> dict:
    """Honest MCP/API payload: never claim local files are current without verification."""
    expected = AGENT_GUIDANCE_VERSION
    last_ver = None
    last_at = None
    if last_verified:
        last_ver = last_verified.get("agent_guidance_version")
        last_at = last_verified.get("verified_at")
    if last_ver is None:
        status = "local_verification_required"
    elif int(last_ver) < expected:
        status = "verification_recommended"
    elif int(last_ver) == expected:
        status = "last_verified_current"
    else:
        status = "verification_recommended"
    return {
        "expected_version": expected,
        "expected_session_skill_version": SESSION_SKILL_VERSION,
        "last_verified_version": last_ver,
        "last_verified_at": last_at,
        "status": status,
        "hint": "Run locally: adhd-hub doctor --project <path>",
    }


def format_continuity_report(items: list[ComponentHealth]) -> str:
    lines = ["Project continuity"]
    marks = {
        GuidanceStatus.current: "✓",
        GuidanceStatus.outdated: "!",
        GuidanceStatus.missing: "!",
        GuidanceStatus.malformed: "!!",
        GuidanceStatus.locally_modified: "!",
        GuidanceStatus.not_applicable: "-",
    }
    for item in items:
        mark = marks.get(item.status, "?")
        lines.append(f"{mark} {item.name}: {item.detail}")
    hints = repair_hint(items)
    if hints:
        lines.append("")
        lines.append("Do next")
        for hint in hints:
            lines.append(f"→ {hint}")
    return "\n".join(lines)


def dump_verification_record(
    *,
    agent_guidance_version: int | None,
    session_skill_version: int | None = None,
    cursor_rule_version: int | None = None,
    source: str = "doctor",
) -> str:
    from adhd_hub.store import utcnow

    return json.dumps(
        {
            "agent_guidance_version": agent_guidance_version,
            "session_skill_version": session_skill_version,
            "cursor_rule_version": cursor_rule_version,
            "source": source,
            "verified_at": utcnow().isoformat(),
        }
    )
