"""Deterministic ADHD Hub project-sync (no LLM).

Copies Hub-owned guidance/skills into a consumer repository:

- AGENTS.md managed block (markers only)
- `.cursor/rules/adhd-hub.mdc`
- `.agents/skills/{adhd-hub-projects,adhd-hub-session,env-check}/**`
- Hub-owned entries in `skills-lock.json`

Preserves unrelated project content. Idempotent.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from adhd_hub.connect import expected_cursor_rule_text, install_cursor_rule
from adhd_hub.guidance_health import (
    AGENT_GUIDANCE_VERSION,
    BEGIN_MARKER,
    CURSOR_RULE_VERSION,
    END_MARKER,
    ENV_CHECK_SKILL_VERSION,
    HUB_OWNED_SKILLS,
    PROJECTS_SKILL_VERSION,
    SESSION_SKILL_VERSION,
)
from adhd_hub.project_setup import agent_block, install_agent_guidance

HUB_REPO = "uniskela/adhd-hub"
HUB_DOCS_BLOB = "https://github.com/uniskela/adhd-hub/blob/main/docs"

HUB_SKILL_NAMES: tuple[str, ...] = tuple(HUB_OWNED_SKILLS.keys())

# Files/dirs sync may create or rewrite under the project root.
MANAGED_PATH_PREFIXES: tuple[str, ...] = (
    "AGENTS.md",
    ".cursor/rules/adhd-hub.mdc",
    ".agents/skills/adhd-hub-projects/",
    ".agents/skills/adhd-hub-session/",
    ".agents/skills/env-check/",
    "skills-lock.json",
)

REL_DOCS_LINK_RE = re.compile(r"\]\(\.\./\.\./docs/([^)]+)\)")
FORBIDDEN_SECRETISH_RE = re.compile(
    r"(?i)("
    r"ADHD_HUB_AUTH_TOKEN\s*=\s*\S+"
    r"|Bearer\s+(?!authentication\b|<)[A-Za-z0-9._~\-/+=]{20,}"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r")"
)

EXECUTABLE_REL_PATHS = frozenset(
    {
        ".agents/skills/env-check/scripts/check_runtime.sh",
    }
)


class SyncMode(StrEnum):
    apply = "apply"
    check = "check"
    dry_run = "dry_run"


class ChangeKind(StrEnum):
    create = "create"
    update = "update"
    chmod = "chmod"
    unchanged = "unchanged"


@dataclass(frozen=True)
class PlannedChange:
    relative_path: str
    kind: ChangeKind
    detail: str = ""


@dataclass
class SyncResult:
    mode: SyncMode
    project: Path
    source: Path
    changes: list[PlannedChange] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    versions: dict[str, int] = field(default_factory=dict)

    @property
    def needs_sync(self) -> bool:
        return any(c.kind != ChangeKind.unchanged for c in self.changes)

    @property
    def ok(self) -> bool:
        return not self.errors


def hub_package_root() -> Path:
    """Return the ADHD Hub checkout root that owns `skills/` + adapters."""
    # src/adhd_hub/project_sync.py → parents[2] == repo root when editable/source layout
    here = Path(__file__).resolve()
    candidate = here.parents[2]
    if (candidate / "skills" / "adhd-hub-session" / "SKILL.md").is_file():
        return candidate
    # Installed wheel: look beside package data if present
    pkg = here.parent
    if (pkg / "skills" / "adhd-hub-session" / "SKILL.md").is_file():
        return pkg
    raise FileNotFoundError(
        "Cannot locate Hub skills source (expected skills/adhd-hub-session/SKILL.md "
        "next to the ADHD Hub checkout)."
    )


def resolve_source(source: str | Path | None) -> Path:
    if source is None:
        return hub_package_root()
    path = Path(source).expanduser().resolve()
    if (path / "skills" / "adhd-hub-session" / "SKILL.md").is_file():
        return path
    if path.name == "skills" and (path / "adhd-hub-session" / "SKILL.md").is_file():
        return path.parent
    raise FileNotFoundError(f"Hub skills source not found under: {path}")


def skill_sha256(skill_md: Path) -> str:
    return hashlib.sha256(skill_md.read_bytes()).hexdigest()


def rewrite_docs_links(text: str) -> str:
    """Rewrite Hub-repo-relative docs links to stable GitHub blob URLs."""
    return REL_DOCS_LINK_RE.sub(rf"]({HUB_DOCS_BLOB}/\1)", text)


def parse_frontmatter_versions(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not text.startswith("---\n"):
        return out
    end = text.find("\n---\n", 4)
    if end == -1:
        return out
    for line in text[4:end].splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in {"hub_skill_version", "hub_guidance_version"}:
            out[key] = value.strip()
    return out


def _is_under_managed(rel: str) -> bool:
    norm = rel.replace("\\", "/")
    for prefix in MANAGED_PATH_PREFIXES:
        if prefix.endswith("/"):
            if norm == prefix[:-1] or norm.startswith(prefix):
                return True
        elif norm == prefix:
            return True
    return False


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _plan_text_file(
    *,
    relative_path: str,
    desired: str,
    current: str | None,
) -> PlannedChange:
    if current is None:
        return PlannedChange(relative_path, ChangeKind.create)
    if current == desired:
        return PlannedChange(relative_path, ChangeKind.unchanged)
    return PlannedChange(relative_path, ChangeKind.update)


def _copy_skill_tree_plans(
    source_skill: Path,
    dest_skill: Path,
    *,
    skill_name: str,
) -> list[tuple[PlannedChange, bytes | str, bool]]:
    """Return planned file writes: (change, content_or_bytes, executable)."""
    if not source_skill.is_dir():
        raise FileNotFoundError(f"missing Hub skill source: {source_skill}")
    plans: list[tuple[PlannedChange, bytes | str, bool]] = []
    for src in sorted(source_skill.rglob("*")):
        if not src.is_file():
            continue
        rel_inside = src.relative_to(source_skill).as_posix()
        dest = dest_skill / rel_inside
        project_rel = f".agents/skills/{skill_name}/{rel_inside}"
        executable = project_rel in EXECUTABLE_REL_PATHS or bool(
            src.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        )
        if src.suffix in {".md", ".mdc", ".txt"}:
            text = rewrite_docs_links(src.read_text(encoding="utf-8"))
            current = _read_text(dest)
            change = _plan_text_file(
                relative_path=project_rel, desired=text, current=current
            )
            plans.append((change, text, executable))
        else:
            data = src.read_bytes()
            if dest.is_file() and dest.read_bytes() == data:
                change = PlannedChange(project_rel, ChangeKind.unchanged)
            elif dest.is_file():
                change = PlannedChange(project_rel, ChangeKind.update)
            else:
                change = PlannedChange(project_rel, ChangeKind.create)
            plans.append((change, data, executable))
            if dest.is_file() and executable and not (dest.stat().st_mode & stat.S_IXUSR):
                plans.append(
                    (
                        PlannedChange(project_rel, ChangeKind.chmod, "set executable"),
                        data,
                        True,
                    )
                )
    return plans


def _agents_desired_text(project: Path) -> tuple[str, PlannedChange]:
    """Compute desired AGENTS.md without writing; fail on malformed markers."""
    path = project / "AGENTS.md"
    original = path.read_text(encoding="utf-8") if path.is_file() else ""
    has_begin = BEGIN_MARKER in original
    has_end = END_MARKER in original
    if has_begin != has_end:
        raise ValueError(f"incomplete ADHD Hub managed block in {path}")
    block = agent_block()
    if has_begin:
        before, remainder = original.split(BEGIN_MARKER, 1)
        _managed, after = remainder.split(END_MARKER, 1)
        updated = before.rstrip() + "\n\n" + block + after
    else:
        prefix = original.rstrip() or "# AGENTS.md"
        updated = prefix + "\n\n" + block + "\n"
    if not path.is_file():
        kind = ChangeKind.create
    elif updated == original:
        kind = ChangeKind.unchanged
    else:
        kind = ChangeKind.update
    return updated, PlannedChange("AGENTS.md", kind)


def _lock_desired(
    project: Path,
    source: Path,
) -> tuple[dict, PlannedChange]:
    lock_path = project / "skills-lock.json"
    if lock_path.is_file():
        try:
            data = json.loads(lock_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed skills-lock.json: {exc}") from exc
        if not isinstance(data, dict):
            raise TypeError("skills-lock.json root must be an object")
    else:
        data = {"version": 1, "skills": {}}

    skills = data.setdefault("skills", {})
    if not isinstance(skills, dict):
        raise TypeError("skills-lock.json 'skills' must be an object")

    for name in HUB_SKILL_NAMES:
        skill_md = source / "skills" / name / "SKILL.md"
        if not skill_md.is_file():
            raise FileNotFoundError(f"missing {skill_md}")
        skills[name] = {
            "source": HUB_REPO,
            "sourceType": "github",
            "skillPath": f"skills/{name}/SKILL.md",
            "computedHash": skill_sha256(skill_md),
        }

    data["version"] = int(data.get("version") or 1)
    # Stable key order for Hub entries first is not required; preserve unrelated keys.
    rendered = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    current = _read_text(lock_path)
    if current is None:
        kind = ChangeKind.create
    elif current == rendered:
        kind = ChangeKind.unchanged
    else:
        # Normalize current for comparison (skills.sh may omit trailing newline)
        try:
            current_obj = json.loads(current)
            if current_obj == data:
                kind = ChangeKind.unchanged
                rendered = current if current.endswith("\n") else current + "\n"
            else:
                kind = ChangeKind.update
        except json.JSONDecodeError:
            kind = ChangeKind.update
    return data, PlannedChange("skills-lock.json", kind, rendered)


def validate_synced_tree(project: Path) -> list[str]:
    """Post-sync / dry-run validation of managed content."""
    errors: list[str] = []
    agents = project / "AGENTS.md"
    if agents.is_file():
        text = agents.read_text(encoding="utf-8")
        has_begin = BEGIN_MARKER in text
        has_end = END_MARKER in text
        if has_begin != has_end:
            errors.append("AGENTS.md has incomplete Hub managed markers")
        elif (
            has_begin
            and f"adhd-hub:guidance-version:{AGENT_GUIDANCE_VERSION}" not in text
        ):
            errors.append(
                f"AGENTS.md missing guidance-version:{AGENT_GUIDANCE_VERSION}"
            )

    rule = project / ".cursor" / "rules" / "adhd-hub.mdc"
    if rule.is_file():
        rule_text = rule.read_text(encoding="utf-8")
        if f"hub_guidance_version: {CURSOR_RULE_VERSION}" not in rule_text and (
            f"hub_guidance_version:{CURSOR_RULE_VERSION}" not in rule_text
        ):
            errors.append(f"Cursor rule missing hub_guidance_version: {CURSOR_RULE_VERSION}")
        if FORBIDDEN_SECRETISH_RE.search(rule_text):
            errors.append("Cursor rule contains credential-like material")

    expected_versions = {
        "adhd-hub-session": SESSION_SKILL_VERSION,
        "adhd-hub-projects": PROJECTS_SKILL_VERSION,
        "env-check": ENV_CHECK_SKILL_VERSION,
    }
    for name, version in expected_versions.items():
        skill_md = project / ".agents" / "skills" / name / "SKILL.md"
        if not skill_md.is_file():
            errors.append(f"missing project skill: .agents/skills/{name}/SKILL.md")
            continue
        text = skill_md.read_text(encoding="utf-8")
        if f"hub_skill_version: {version}" not in text:
            errors.append(f"{name}: expected hub_skill_version: {version}")
        if REL_DOCS_LINK_RE.search(text):
            errors.append(f"{name}: still has relative ../../docs/ links")
        if FORBIDDEN_SECRETISH_RE.search(text):
            errors.append(f"{name}: contains credential-like material")
        # Docs links must not point at nonexistent local docs/
        for match in re.finditer(r"\]\(([^)]+)\)", text):
            target = match.group(1)
            if target.startswith("../../docs/"):
                errors.append(f"{name}: broken relative docs link {target}")
            if target.startswith("docs/") and not (project / target).exists():
                # Downstream repos should not need a local docs tree
                errors.append(
                    f"{name}: local docs link {target} would break downstream "
                    "(use GitHub blob URL)"
                )

    runtime = project / ".agents" / "skills" / "env-check" / "scripts" / "check_runtime.sh"
    if runtime.is_file():
        mode = runtime.stat().st_mode
        if not (mode & stat.S_IXUSR):
            errors.append("check_runtime.sh is not executable")
    else:
        errors.append("missing .agents/skills/env-check/scripts/check_runtime.sh")

    return errors


def sync_project(
    project_dir: Path | str,
    *,
    source: Path | str | None = None,
    mode: SyncMode = SyncMode.apply,
    agents: list[str] | None = None,
) -> SyncResult:
    """Sync Hub-managed project files.

    ``agents`` is accepted for CLI compatibility (cursor,codex) and currently
    only gates whether the Cursor rule is written when ``cursor`` is selected.
    Codex/AGENTS guidance is always managed when syncing.
    """
    project = Path(project_dir).expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"project folder does not exist: {project}")

    src = resolve_source(source)
    result = SyncResult(
        mode=mode,
        project=project,
        source=src,
        versions={
            "agent_guidance_version": AGENT_GUIDANCE_VERSION,
            "session_skill_version": SESSION_SKILL_VERSION,
            "projects_skill_version": PROJECTS_SKILL_VERSION,
            "env_check_skill_version": ENV_CHECK_SKILL_VERSION,
            "cursor_rule_version": CURSOR_RULE_VERSION,
        },
    )

    agent_set = {a.strip().lower() for a in (agents or ["cursor", "codex"]) if a.strip()}
    write_cursor_rule = not agent_set or "cursor" in agent_set or "*" in agent_set

    try:
        _agents_text, agents_change = _agents_desired_text(project)
    except ValueError as exc:
        result.errors.append(str(exc))
        return result

    result.changes.append(agents_change)

    rule_text = expected_cursor_rule_text()
    rule_path = project / ".cursor" / "rules" / "adhd-hub.mdc"
    if write_cursor_rule:
        rule_change = _plan_text_file(
            relative_path=".cursor/rules/adhd-hub.mdc",
            desired=rule_text,
            current=_read_text(rule_path),
        )
        result.changes.append(rule_change)
    else:
        rule_change = PlannedChange(
            ".cursor/rules/adhd-hub.mdc", ChangeKind.unchanged, "skipped (agents)"
        )
        result.changes.append(rule_change)

    skill_payloads: list[tuple[PlannedChange, bytes | str, bool]] = []
    for name in HUB_SKILL_NAMES:
        skill_payloads.extend(
            _copy_skill_tree_plans(
                src / "skills" / name,
                project / ".agents" / "skills" / name,
                skill_name=name,
            )
        )
    for change, _payload, _exe in skill_payloads:
        if change.kind != ChangeKind.unchanged or not any(
            c.relative_path == change.relative_path for c in result.changes
        ):
            result.changes.append(change)

    try:
        lock_data, lock_change_raw = _lock_desired(project, src)
    except (ValueError, TypeError, FileNotFoundError, json.JSONDecodeError) as exc:
        result.errors.append(str(exc))
        return result
    lock_change = PlannedChange(lock_change_raw.relative_path, lock_change_raw.kind)
    result.changes.append(lock_change)

    if mode in {SyncMode.check, SyncMode.dry_run}:
        # Validate against desired content conceptually: for check without writes,
        # only validate existing tree when already synced; otherwise report drift.
        if mode == SyncMode.check and not result.needs_sync:
            result.errors.extend(validate_synced_tree(project))
        return result

    # Apply writes
    try:
        if agents_change.kind != ChangeKind.unchanged:
            install_agent_guidance(project)
        if write_cursor_rule and rule_change.kind != ChangeKind.unchanged:
            install_cursor_rule(project)
        for change, payload, executable in skill_payloads:
            dest = project / change.relative_path
            if change.kind == ChangeKind.chmod:
                if dest.is_file():
                    dest.chmod(dest.stat().st_mode | 0o111)
                continue
            if change.kind == ChangeKind.unchanged:
                if executable and dest.is_file() and not (dest.stat().st_mode & stat.S_IXUSR):
                    dest.chmod(dest.stat().st_mode | 0o111)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(payload, str):
                dest.write_text(payload, encoding="utf-8", newline="\n")
            else:
                dest.write_bytes(payload)
            if executable:
                dest.chmod(dest.stat().st_mode | 0o111)
        if lock_change.kind != ChangeKind.unchanged:
            (project / "skills-lock.json").write_text(
                json.dumps(lock_data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    except OSError as exc:
        result.errors.append(str(exc))
        return result

    result.errors.extend(validate_synced_tree(project))
    return result


def format_sync_report(result: SyncResult) -> str:
    lines = [
        f"ADHD Hub project sync ({result.mode})",
        f"  project: {result.project}",
        f"  source:  {result.source}",
        (
            f"  versions: guidance={result.versions.get('agent_guidance_version')} "
            f"session={result.versions.get('session_skill_version')} "
            f"projects={result.versions.get('projects_skill_version')} "
            f"env-check={result.versions.get('env_check_skill_version')} "
            f"rule={result.versions.get('cursor_rule_version')}"
        ),
        "",
    ]
    actionable = [c for c in result.changes if c.kind != ChangeKind.unchanged]
    if not actionable:
        lines.append("No changes needed.")
    else:
        lines.append("Changes:" if result.mode == SyncMode.apply else "Would change:")
        for change in actionable:
            extra = f" ({change.detail})" if change.detail else ""
            lines.append(f"  {change.kind}: {change.relative_path}{extra}")
    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"  - {w}" for w in result.warnings)
    if result.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  - {e}" for e in result.errors)
    return "\n".join(lines) + "\n"


def assert_only_managed_paths(changed_paths: list[str]) -> list[str]:
    """Return any paths outside the Hub-managed allowlist."""
    return [p for p in changed_paths if not _is_under_managed(p)]


def remove_project_skills(project_dir: Path | str) -> list[str]:
    """Remove Hub-owned project-scoped skill trees only (not unrelated skills)."""
    project = Path(project_dir).expanduser().resolve()
    removed: list[str] = []
    for name in HUB_SKILL_NAMES:
        path = project / ".agents" / "skills" / name
        if path.is_dir():
            shutil.rmtree(path)
            removed.append(str(path.relative_to(project)))
    return removed
