"""CI-safe continuity-guard audit (no private runtime state)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from adhd_hub.continuity_guard.config import load_guard_config
from adhd_hub.continuity_guard.hooks_sync import (
    HUB_GUARD_COMMAND_MARKER,
    expected_guard_script,
    hooks_json_has_hub_entries,
    plan_hooks_merge,
)


@dataclass
class AuditFinding:
    code: str
    severity: str  # ok | info | warn | error
    message: str


@dataclass
class AuditReport:
    project: Path
    findings: list[AuditFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)


def audit_project(project_dir: Path | str) -> AuditReport:
    """Validate guard install/config without reading Git-local runtime state."""
    project = Path(project_dir).expanduser().resolve()
    report = AuditReport(project=project)
    if not project.is_dir():
        report.findings.append(
            AuditFinding("project", "error", f"project folder does not exist: {project}")
        )
        return report

    cfg = load_guard_config(project)
    hooks_path = project / ".cursor" / "hooks.json"
    script_path = project / ".cursor" / "hooks" / "adhd-hub-guard.sh"
    enrolled = hooks_json_has_hub_entries(hooks_path) or script_path.is_file()

    if not enrolled and not cfg.enabled:
        report.findings.append(
            AuditFinding(
                "continuity_guard",
                "info",
                "continuity guard not enabled",
            )
        )
        return report

    if cfg.enabled and cfg.mode not in {"off", "gentle", "balanced", "strict"}:
        report.findings.append(
            AuditFinding("config", "error", f"malformed continuity_guard.mode: {cfg.mode}")
        )
    elif cfg.enabled:
        report.findings.append(
            AuditFinding("config", "ok", f"continuity_guard mode={cfg.mode}")
        )

    if not script_path.is_file():
        report.findings.append(
            AuditFinding(
                "guard_script",
                "warn" if enrolled else "info",
                "missing .cursor/hooks/adhd-hub-guard.sh",
            )
        )
    else:
        desired = expected_guard_script()
        current = script_path.read_text(encoding="utf-8")
        if current != desired:
            report.findings.append(
                AuditFinding("guard_script", "warn", "adhd-hub-guard.sh drifted from Hub canonical")
            )
        else:
            report.findings.append(
                AuditFinding("guard_script", "ok", "adhd-hub-guard.sh current")
            )

    if not hooks_path.is_file():
        report.findings.append(
            AuditFinding("hooks_json", "warn", "missing .cursor/hooks.json")
        )
    else:
        try:
            changes = plan_hooks_merge(hooks_path)
        except ValueError as exc:
            report.findings.append(AuditFinding("hooks_json", "error", str(exc)))
        else:
            if changes:
                report.findings.append(
                    AuditFinding(
                        "hooks_json",
                        "warn",
                        f"Cursor hooks drift ({len(changes)} Hub-owned change(s))",
                    )
                )
            else:
                report.findings.append(
                    AuditFinding("hooks_json", "ok", "Cursor hooks current")
                )
            # Sanity: marker present
            text = hooks_path.read_text(encoding="utf-8")
            if HUB_GUARD_COMMAND_MARKER not in text:
                report.findings.append(
                    AuditFinding(
                        "hooks_json",
                        "warn",
                        "Hub guard command marker not found in hooks.json",
                    )
                )

    if enrolled:
        report.findings.insert(
            0,
            AuditFinding("continuity_guard", "ok", "continuity guard installed"),
        )
    return report


def format_audit_report(report: AuditReport) -> str:
    lines = [f"ADHD Hub continuity guard audit: {report.project}", ""]
    for finding in report.findings:
        mark = {
            "ok": "✓",
            "info": "-",
            "warn": "!",
            "error": "✗",
        }.get(finding.severity, "?")
        lines.append(f"  {mark} {finding.code:20} {finding.message}")
    return "\n".join(lines) + "\n"
