"""Observe Hub MCP / forge evidence from hook payloads (no secrets stored)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

# Hub MCP tool names (bare and MCP: prefixed).
HUB_TOOLS: dict[str, str] = {
    "resolve_project": "resolve",
    "session_digest": "digest",
    "check_overlap": "overlap",
    "upsert_progress": "progress",
    "upsert_thread": "progress",
    "pause_thread": "pause",
    "mark_done": "done",
    "register_workspace": "resolve",
}

HUB_SERVER_HINTS = frozenset(
    {
        "adhd-hub",
        "user-adhd-hub",
        "plugin-adhd-hub",
        "adhd_hub",
    }
)

_ADHD_ISSUE_TITLE = re.compile(r"\[adhd\]\s*", re.IGNORECASE)
_ISSUE_URL = re.compile(
    r"https://(?:github\.com|[^/\s]+)/(?:[^/\s]+)/(?:[^/\s]+)/issues/(\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EvidenceHit:
    kind: str  # resolve|digest|overlap|progress|pause|done|forge_fallback
    project_slug: str | None = None
    thread_id: str | None = None
    fallback_issue_number: int | None = None
    fallback_issue_url: str | None = None
    continuity_method: str | None = None


def normalize_mcp_tool_name(tool_name: str | None) -> str:
    if not tool_name:
        return ""
    name = tool_name.strip()
    if name.upper().startswith("MCP:"):
        name = name.split(":", 1)[1]
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    if "." in name:
        name = name.rsplit(".", 1)[-1]
    return name.strip()


def is_hub_mcp_server(server_name: str | None) -> bool:
    if not server_name:
        return False
    key = server_name.strip().lower().replace("_", "-")
    if key in HUB_SERVER_HINTS:
        return True
    return "adhd-hub" in key or key.endswith("adhd-hub")


def observe_mcp_tool(
    tool_name: str | None,
    *,
    mcp_server_name: str | None = None,
    tool_input: Any = None,
    success: bool = True,
) -> EvidenceHit | None:
    """Return evidence for a successful Hub MCP tool call."""
    if not success:
        return None
    bare = normalize_mcp_tool_name(tool_name)
    kind = HUB_TOOLS.get(bare)
    if kind is None:
        return None
    # If server name present, require Hub-ish server; if absent (cloud postToolUse),
    # trust tool name match alone.
    if mcp_server_name and not is_hub_mcp_server(mcp_server_name):
        return None
    slug, thread = _extract_ids(tool_input)
    method = "mcp"
    return EvidenceHit(
        kind=kind,
        project_slug=slug,
        thread_id=thread,
        continuity_method=method,
    )


def observe_forge_action(
    *,
    tool_name: str | None = None,
    command: str | None = None,
    tool_output: Any = None,
    tool_input: Any = None,
) -> EvidenceHit | None:
    """Detect authorised [ADHD] forge issue create/update evidence."""
    name = (tool_name or "").lower()
    cmd = command or ""
    if isinstance(tool_input, dict) and not cmd:
        maybe = tool_input.get("command")
        if isinstance(maybe, str):
            cmd = maybe

    looks_issue = False
    if "gh issue create" in cmd or "gh issue edit" in cmd:
        looks_issue = True
    if "create_issue" in name or "issue_write" in name or "update_issue" in name:
        looks_issue = True
    if not looks_issue:
        return None

    # Prefer title containing [ADHD]
    blob = " ".join(
        [
            cmd,
            _safe_str(tool_input),
            _safe_str(tool_output),
        ]
    )
    if (
        not _ADHD_ISSUE_TITLE.search(blob)
        and "adhd-hub" not in blob.lower()
        and "[ADHD]" not in blob
        and "[adhd]" not in blob.lower()
    ):
        return None

    number = None
    url = None
    match = _ISSUE_URL.search(blob)
    if match:
        number = int(match.group(1))
        url = match.group(0)
    # Also parse "number": 123 from JSON-ish output
    if number is None:
        m2 = re.search(r'"number"\s*:\s*(\d+)', blob)
        if m2:
            number = int(m2.group(1))

    return EvidenceHit(
        kind="forge_fallback",
        fallback_issue_number=number,
        fallback_issue_url=url,
        continuity_method="forge",
    )


def apply_evidence_to_state(state: Any, hit: EvidenceHit) -> None:
    """Mutate guard state evidence flags from a hit (no Hub fabrication)."""
    if hit.kind == "resolve":
        state.evidence_resolve = True
    elif hit.kind == "digest":
        state.evidence_digest = True
    elif hit.kind == "overlap":
        state.evidence_overlap = True
    elif hit.kind == "progress":
        state.evidence_progress = True
    elif hit.kind == "pause":
        state.evidence_pause = True
        state.evidence_progress = True
    elif hit.kind == "done":
        state.evidence_done = True
        state.evidence_progress = True
    elif hit.kind == "forge_fallback":
        state.evidence_forge_fallback = True
        if hit.fallback_issue_number is not None:
            state.fallback_issue_number = hit.fallback_issue_number
        if hit.fallback_issue_url:
            state.fallback_issue_url = hit.fallback_issue_url
    if hit.project_slug:
        state.project_slug = hit.project_slug
    if hit.thread_id:
        state.thread_id = hit.thread_id
    if hit.continuity_method:
        state.continuity_method = hit.continuity_method


def _extract_ids(tool_input: Any) -> tuple[str | None, str | None]:
    data = _as_dict(tool_input)
    if not data:
        return None, None
    slug = data.get("project_slug") or data.get("slug")
    thread = data.get("thread_id")
    slug_s = slug.strip()[:80] if isinstance(slug, str) else None
    thread_s = thread.strip()[:64] if isinstance(thread, str) else None
    return slug_s, thread_s


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        # Cap size — never keep huge tool outputs in memory for matching long
        return value[:4000]
    try:
        return json.dumps(value, ensure_ascii=False)[:4000]
    except (TypeError, ValueError):
        return str(value)[:4000]
