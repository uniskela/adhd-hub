"""Parse and reconcile structured ADHD forge issue bodies.

Forge content is data only.  This module deliberately performs no command,
URL, or markup execution; it extracts a small allowlisted set of headings.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

SOURCE_FIELDS = ("goal", "focus", "next_steps", "blocked_reason", "resume_step")
_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_TASK = re.compile(r"^\s*[-*]\s+(?:\[[ xX]\]\s*)?(.+?)\s*$")
_HUB_STATUS = re.compile(
    r"<!-- adhd-hub:status:start -->.*?<!-- adhd-hub:status:end -->",
    re.DOTALL,
)


def content_hash(body: str) -> str:
    """Hash source-owned body content, excluding Hub's own mirrored status block."""
    normalized = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = _HUB_STATUS.sub("", normalized).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _sections(body: str) -> dict[str, str]:
    matches = list(_HEADING.finditer(body or ""))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = re.sub(r"\s+", " ", match.group(1).strip().casefold())
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[name] = body[match.end() : end].strip()
    return sections


def _text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _section_text(value: str | None) -> str | None:
    """Return a short section's text, accepting one ordinary Markdown bullet."""
    text = _text(value)
    if not text:
        return None
    lines = text.splitlines()
    if len(lines) == 1 and (match := _TASK.match(lines[0])):
        return match.group(1).strip() or None
    return text


def _steps(value: str | None) -> list[str] | None:
    if value is None:
        return None
    steps = [match.group(1).strip() for line in value.splitlines() if (match := _TASK.match(line))]
    return [step for step in steps if step][:3]


def parse_issue_body(body: str) -> dict[str, Any]:
    """Extract allowlisted continuity headings; never infer or execute prose."""
    sections = _sections(body)
    goal = _section_text(sections.get("goal")) if "goal" in sections else None
    focus_key = next((key for key in ("focus", "now", "current state") if key in sections), None)
    next_key = next((key for key in ("next", "tasks") if key in sections), None)
    blocked_key = next((key for key in ("blocked", "waiting") if key in sections), None)
    resume_key = next(
        (key for key in ("resume", "resume cue", "return cue") if key in sections), None
    )
    values: dict[str, Any] = {}
    if "goal" in sections:
        values["goal"] = goal
    if focus_key:
        values["focus"] = _section_text(sections.get(focus_key))
    if next_key:
        values["next_steps"] = _steps(sections.get(next_key)) or []
    if blocked_key:
        values["blocked_reason"] = _section_text(sections.get(blocked_key))
    if resume_key:
        values["resume_step"] = _section_text(sections.get(resume_key))
    return values


def issue_snapshot(issue: dict[str, Any]) -> dict[str, Any]:
    title = str(issue.get("title") or "").strip()
    summary = re.sub(r"^\[ADHD\]\s*", "", title, flags=re.IGNORECASE).strip() or title
    body = str(issue.get("body") or "")
    return {"summary": summary[:500], **parse_issue_body(body)}


@dataclass(frozen=True, slots=True)
class RefreshPlan:
    changes: dict[str, Any]
    conflicts: dict[str, dict[str, Any]]


def plan_refresh(
    previous: dict[str, Any], current_hub: dict[str, Any], incoming: dict[str, Any], *, title_derived: bool
) -> RefreshPlan:
    """Three-way field plan: source-only edits apply; concurrent edits conflict."""
    changes: dict[str, Any] = {}
    conflicts: dict[str, dict[str, Any]] = {}
    fields = list(SOURCE_FIELDS)
    if title_derived:
        fields.insert(0, "summary")
    for field in fields:
        if field not in incoming:
            continue
        before = previous.get(field)
        hub = current_hub.get(field)
        forge = incoming.get(field)
        # A legacy repo-primary thread may have no source snapshot at all. Its
        # empty continuity defaults are not a user edit, so let the first safe
        # source projection establish the three-way base. Non-empty local
        # values remain protected as potential manual edits.
        if field not in previous:
            default = [] if field == "next_steps" else None
            if hub == default:
                if hub != forge:
                    changes[field] = forge
                continue
        if forge == before:
            continue
        if hub != before and hub != forge:
            conflicts[field] = {"previous": before, "hub": hub, "forge": forge}
        elif hub != forge:
            changes[field] = forge
    return RefreshPlan(changes=changes, conflicts=conflicts)