"""Git-local ephemeral continuity-guard state (never commit)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adhd_hub.continuity_guard.machine import GuardPhase

SCHEMA_VERSION = 1
STATE_REL = Path(".git") / "adhd-hub" / "continuity-guard.json"

# Reject obvious secret-like values if they ever appear in string fields.
_SECRETISH = re.compile(
    r"(?i)("
    r"ADHD_HUB_AUTH_TOKEN\s*="
    r"|Bearer\s+[A-Za-z0-9._~\-/+=]{20,}"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r")"
)


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class GuardState:
    """Disposable per-repo guard state. Reconstructable; never contains secrets."""

    schema_version: int = SCHEMA_VERSION
    phase: str = GuardPhase.not_required.value
    conversation_id: str | None = None
    session_started_at: str | None = None
    updated_at: str | None = None
    continuity_method: str | None = None  # mcp | forge | none
    project_slug: str | None = None
    thread_id: str | None = None
    meaningful_work: bool = False
    files_changed: int = 0
    mutations_since_checkpoint: int = 0
    evidence_resolve: bool = False
    evidence_digest: bool = False
    evidence_overlap: bool = False
    evidence_progress: bool = False
    evidence_pause: bool = False
    evidence_done: bool = False
    evidence_forge_fallback: bool = False
    fallback_issue_number: int | None = None
    fallback_issue_url: str | None = None
    guard_retry_count: int = 0
    persistence_unavailable: bool = False
    last_warning: str | None = None
    touched_paths: list[str] = field(default_factory=list)

    def phase_enum(self) -> GuardPhase:
        try:
            return GuardPhase(self.phase)
        except ValueError:
            return GuardPhase.not_required

    def set_phase(self, phase: GuardPhase) -> None:
        self.phase = phase.value
        self.updated_at = _utcnow()

    def to_public_dict(self) -> dict[str, Any]:
        """Serialize for disk — strips empty lists and never writes secrets."""
        data = asdict(self)
        # Cap touched paths to relative short names only
        paths = []
        for p in data.get("touched_paths") or []:
            if not isinstance(p, str):
                continue
            clean = p.replace("\\", "/").lstrip("/")
            if ".." in clean.split("/") or _SECRETISH.search(clean):
                continue
            # Prefer basename or short relative
            if len(clean) > 200:
                clean = clean[-200:]
            paths.append(clean)
            if len(paths) >= 40:
                break
        data["touched_paths"] = paths
        for key in ("project_slug", "thread_id", "conversation_id", "last_warning"):
            val = data.get(key)
            if isinstance(val, str) and _SECRETISH.search(val):
                data[key] = None
        if isinstance(data.get("fallback_issue_url"), str) and _SECRETISH.search(
            data["fallback_issue_url"]
        ):
            data["fallback_issue_url"] = None
        return data


def state_path_for(project_dir: Path | str) -> Path:
    """Return the Git-local state path for ``project_dir``."""
    project = Path(project_dir).expanduser().resolve()
    git_dir = _resolve_git_dir(project)
    return git_dir / "adhd-hub" / "continuity-guard.json"


def _resolve_git_dir(project: Path) -> Path:
    """Locate ``.git`` directory (file or dir). Fall back to project/.git."""
    candidate = project / ".git"
    if candidate.is_file():
        try:
            text = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            return candidate
        if text.startswith("gitdir:"):
            gitdir = text.split(":", 1)[1].strip()
            path = Path(gitdir)
            if not path.is_absolute():
                path = (project / path).resolve()
            return path
    if candidate.is_dir():
        return candidate
    # Non-git workspace: still use project/.git/adhd-hub (ephemeral; may be created)
    return candidate


def load_state(project_dir: Path | str) -> GuardState:
    """Load state or return a fresh default. Malformed JSON → fresh state."""
    path = state_path_for(project_dir)
    if not path.is_file():
        return GuardState(session_started_at=_utcnow(), updated_at=_utcnow())
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return GuardState(session_started_at=_utcnow(), updated_at=_utcnow())
    if not isinstance(raw, dict):
        return GuardState(session_started_at=_utcnow(), updated_at=_utcnow())
    return _from_dict(raw)


def save_state(project_dir: Path | str, state: GuardState) -> Path:
    """Persist state under ``.git/adhd-hub/``. Creates directories as needed.

    Writes atomically (temp file + ``os.replace``) so concurrent hook
    ``load_state`` calls never observe a truncated JSON file.
    """
    path = state_path_for(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = _utcnow()
    if not state.session_started_at:
        state.session_started_at = state.updated_at
    payload = json.dumps(state.to_public_dict(), indent=2, ensure_ascii=False) + "\n"
    if _SECRETISH.search(payload):
        raise ValueError("refusing to write secret-like material to guard state")
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    except Exception:
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass
        raise
    return path


def clear_state(project_dir: Path | str) -> bool:
    """Delete guard state file if present. Returns True when removed."""
    path = state_path_for(project_dir)
    if path.is_file():
        path.unlink()
        return True
    return False


def reset_state(project_dir: Path | str) -> GuardState:
    """Clear and return a fresh state (also saved)."""
    clear_state(project_dir)
    state = GuardState(session_started_at=_utcnow(), updated_at=_utcnow())
    save_state(project_dir, state)
    return state


def _from_dict(raw: dict[str, Any]) -> GuardState:
    known = {f.name for f in GuardState.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    kwargs: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in known:
            continue
        kwargs[key] = value
    state = GuardState(**{k: v for k, v in kwargs.items() if k in known})
    # Normalize phase
    try:
        GuardPhase(state.phase)
    except ValueError:
        state.phase = GuardPhase.not_required.value
    if state.schema_version != SCHEMA_VERSION:
        # Soft upgrade: keep evidence flags, reset phase if unknown schema
        state.schema_version = SCHEMA_VERSION
    return state


def is_state_stale(state: GuardState, *, max_age_hours: float) -> bool:
    """True when ``updated_at`` is older than ``max_age_hours``."""
    if not state.updated_at:
        return False
    try:
        stamp = state.updated_at.replace("Z", "+00:00")
        when = datetime.fromisoformat(stamp)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
    except ValueError:
        return True
    age = datetime.now(UTC) - when.astimezone(UTC)
    return age.total_seconds() > max_age_hours * 3600
