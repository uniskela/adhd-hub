"""Install reversible ADHD Hub continuity guidance in a project."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from adhd_hub.cli_style import print_running

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

- If ADHD Hub MCP tools are missing, errored, unauthorized, or otherwise
  unavailable: the **first line** of your reply on that turn (and on later
  substantial Hub-worthy turns while still down) MUST state that Hub MCP is
  not available, plus a short fix hint (MCP URL → this Hub's `/mcp`,
  `ADHD_HUB_AUTH_TOKEN`, restart the agent; skip/cancel Auth if it hangs
  until Hub OAuth is enabled). Then continue the authorized work. Never
  invent Hub state or claim a Hub write succeeded.
- Skip Hub for trivial/read-only/tiny work.
- Once per meaningful session: `resolve_project`, then `session_digest` with
  the task query. Reuse resolved context where possible.
- **One thread = one independently finishable outcome** (not the whole repo).
  Before updating a thread, compare new work to that thread's Goal; if it does
  not advance the same outcome, use another thread or create one.
- Known thread → `upsert_progress(thread_id=...)` with compact structured state
  (goal / focus / ≤3 next / blocked if any / resume). Do not silently attach
  to an unrelated open thread.
- `check_overlap` only before potentially new work; reuse only when the Goal
  matches. Different goal → separate thread (`force_new_thread` if needed).
- Pause with one concrete resume action; `mark_done` only the known completed
  thread — never close unrelated overlap results.
- Summaries only; never secrets, credentials, env files, or transcripts.
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
    print_running(command)
    return subprocess.run(command, check=False).returncode
