"""Wave 6.C — heuristic project organiser suggestions.

Suggests tags from project title/description and open-thread continuity.
Never auto-applies; callers must confirm before writing.
"""

from __future__ import annotations

import re
from typing import Any

from adhd_hub.models import MAX_PROJECT_TAGS, Project, Thread, normalize_project_tags

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,23}")

# Lightweight keyword → tag map for calm defaults (heuristic only).
_KEYWORD_TAGS: dict[str, str] = {
    "docs": "docs",
    "documentation": "docs",
    "readme": "docs",
    "wiki": "docs",
    "homelab": "homelab",
    "docker": "homelab",
    "proxmox": "homelab",
    "tailscale": "homelab",
    "ui": "ui",
    "frontend": "ui",
    "dashboard": "ui",
    "api": "api",
    "mcp": "mcp",
    "forge": "forge",
    "github": "forge",
    "gitea": "forge",
    "auth": "auth",
    "oauth": "auth",
    "release": "release",
    "ci": "ci",
    "test": "tests",
    "tests": "tests",
}


def _tokens(*parts: str | None) -> set[str]:
    found: set[str] = set()
    for part in parts:
        if not part:
            continue
        text = str(part).casefold().replace("_", " ").replace("/", " ")
        for match in _WORD_RE.findall(text):
            found.add(match)
    return found


def suggest_tags_for_project(
    project: Project,
    threads: list[Thread],
    *,
    limit: int = 5,
) -> dict[str, Any]:
    """Return suggested tags that are not already on the project."""
    limit = max(0, min(limit, MAX_PROJECT_TAGS - len(project.tags)))
    if not limit:
        return {
            "slug": project.slug, "title": project.title,
            "current_tags": list(project.tags), "suggested_tags": [], "reasons": [],
        }
    bag = _tokens(project.title, project.description, project.slug)
    for thread in threads[:20]:
        bag |= _tokens(
            thread.summary,
            thread.focus,
            thread.goal,
            thread.resume_step,
            *(thread.next_steps or []),
        )
    suggested: list[str] = []
    reasons: list[str] = []
    for token in sorted(bag):
        tag = _KEYWORD_TAGS.get(token)
        if not tag:
            continue
        if tag in project.tags or tag in suggested:
            continue
        suggested.append(tag)
        reasons.append(f"saw “{token}”")
        if len(suggested) >= limit:
            break
    # Title-derived fallback slug token when nothing mapped.
    if not suggested:
        title_bits = normalize_project_tags(
            [bit for bit in re.split(r"[\s/_-]+", project.title or "") if bit]
        )
        for bit in title_bits:
            if bit not in project.tags and bit not in suggested and len(bit) >= 3:
                suggested.append(bit)
                reasons.append("from title")
            if len(suggested) >= min(2, limit):
                break
    suggested = normalize_project_tags(suggested)[:limit]
    return {
        "slug": project.slug,
        "title": project.title,
        "current_tags": list(project.tags or []),
        "suggested_tags": suggested,
        "reasons": reasons[: len(suggested)],
    }
