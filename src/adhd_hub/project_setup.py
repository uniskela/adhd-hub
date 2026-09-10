"""Install reversible ADHD Hub continuity guidance in a project."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

BEGIN_MARKER = "<!-- adhd-hub:project-agent:start -->"
END_MARKER = "<!-- adhd-hub:project-agent:end -->"

# Hub logical ids → skills.sh agent ids (skills rejects some aliases, e.g. "claude").
SKILLS_AGENT_ALIASES = {
    "claude": "claude-code",
    "claude-code": "claude-code",
    "cursor": "cursor",
    "codex": "codex",
}

CONNECT_AGENT_CHOICES = ("cursor", "codex", "claude", "*")


def normalize_skills_agents(agents: list[str] | None) -> list[str]:
    """Map Hub agent aliases to skills.sh ids; drop empties and ``*``."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in agents or []:
        key = raw.strip().lower()
        if not key or key == "*":
            continue
        mapped = SKILLS_AGENT_ALIASES.get(key, key)
        if mapped not in seen:
            seen.add(mapped)
            out.append(mapped)
    return out


def agent_block() -> str:
    return f"""{BEGIN_MARKER}
## ADHD Hub continuity

For substantial work in this project:

- Do not call Hub tools for trivial/read-only questions, tiny edits, or other
  work that does not benefit from continuity tracking.
- Once per session/checkout, call `resolve_project` with the current absolute
  project root, then `session_digest` with that path and a brief task query.
  Reuse resolved context where possible.
- Before starting new work that may duplicate an existing thread, call
  `check_overlap`.
- At meaningful checkpoints or before pausing/switching context, call
  `upsert_progress` for the resolved project and known thread using a concise
  `Now / Done / Next / Waiting / Return cue` summary.
- On genuine completion, call `mark_done` only for the known thread. Never close
  unrelated overlap results.
- Send summaries only; never send secrets, credentials, keys, env files, or
  transcripts.
- Never publish Hub URLs/tokens, internal hosts, machine paths, or private Hub
  metadata. The local project path may only be sent to the configured Hub for
  resolution.
{END_MARKER}"""


def install_agent_guidance(project_dir: Path) -> tuple[Path, str]:
    root = project_dir.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"project folder does not exist: {root}")
    path = root / "AGENTS.md"
    if path.is_symlink():
        raise ValueError(f"refusing to modify symlink: {path}")
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    has_begin = BEGIN_MARKER in original
    has_end = END_MARKER in original
    if has_begin != has_end:
        raise ValueError(f"incomplete ADHD Hub managed block in {path}")

    block = agent_block()
    if has_begin:
        before, remainder = original.split(BEGIN_MARKER, 1)
        _managed, after = remainder.split(END_MARKER, 1)
        updated = before.rstrip() + "\n\n" + block + after
        action = "unchanged" if updated == original else "updated"
    else:
        prefix = original.rstrip()
        if not prefix:
            prefix = "# AGENTS.md"
        updated = prefix + "\n\n" + block + "\n"
        action = "created" if not original else "updated"

    if updated != original:
        path.write_text(updated, encoding="utf-8")
    return path, action


def uninstall_agent_guidance(project_dir: Path) -> tuple[Path, str]:
    root = project_dir.expanduser().resolve()
    path = root / "AGENTS.md"
    if not path.exists():
        return path, "not installed"
    if path.is_symlink():
        raise ValueError(f"refusing to modify symlink: {path}")
    original = path.read_text(encoding="utf-8")
    has_begin = BEGIN_MARKER in original
    has_end = END_MARKER in original
    if has_begin != has_end:
        raise ValueError(f"incomplete ADHD Hub managed block in {path}")
    if not has_begin:
        return path, "not installed"

    before, remainder = original.split(BEGIN_MARKER, 1)
    _managed, after = remainder.split(END_MARKER, 1)
    updated = (before.rstrip() + "\n" + after.lstrip("\n")).rstrip() + "\n"
    path.write_text(updated, encoding="utf-8")
    return path, "removed"


def install_skills(
    source: str,
    *,
    agents: list[str] | None = None,
    all_agents: bool = False,
) -> int:
    """Install Hub skills via ``npx skills`` (non-interactive)."""
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        print("npx not found on PATH", file=__import__("sys").stderr)
        return 127
    command = [npx, "skills", "add", source, "-g", "-y", "--skill", "*"]
    if all_agents:
        command.extend(["--agent", "*"])
    else:
        targets = normalize_skills_agents(agents)
        if not targets:
            print(
                "No skills agents selected (map Hub aliases like claude → claude-code). "
                "Set --agents or Settings → Connections.",
                file=__import__("sys").stderr,
            )
            return 2
        for agent in targets:
            command.extend(["-a", agent])
    print("Running:", " ".join(command))
    return subprocess.run(command, check=False).returncode
