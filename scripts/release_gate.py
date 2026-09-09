"""Decide whether a trusted main-branch push should invoke Release Please."""

from __future__ import annotations

import re
import subprocess
import sys

RELEASABLE_SUBJECT = re.compile(r"^(?:feat|fix|perf|revert)(?:\([^)]+\))?!?:")
BREAKING_SUBJECT = re.compile(r"^[a-z]+(?:\([^)]+\))?!:")
RELEASE_MERGE_SUBJECT = re.compile(r"^chore\(main\): release \d+\.\d+\.\d+(?:\s|$)")
RUNTIME_FILES = {"pyproject.toml", "uv.lock", "Dockerfile", "docker-compose.yml"}


def is_release_surface(path: str) -> bool:
    """Return whether a changed path can alter shipped application behavior."""
    return path.startswith("src/") or path in RUNTIME_FILES


def subject_can_release(subject: str) -> bool:
    return bool(RELEASABLE_SUBJECT.match(subject) or BREAKING_SUBJECT.match(subject))


def git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return [line for line in result.stdout.splitlines() if line]


def should_run(before: str, after: str) -> bool:
    revision_range = after if before == "0" * 40 else f"{before}..{after}"
    for commit in git_lines("rev-list", "--reverse", revision_range):
        subject = git_lines("show", "-s", "--format=%s", commit)[0]
        if RELEASE_MERGE_SUBJECT.match(subject):
            return True
        if not subject_can_release(subject):
            continue
        changed_paths = git_lines("diff-tree", "--no-commit-id", "--name-only", "-r", "-m", commit)
        if any(is_release_surface(path) for path in changed_paths):
            return True
    return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: release_gate.py <before-sha> <after-sha>")
    print(f"should_run={'true' if should_run(sys.argv[1], sys.argv[2]) else 'false'}")
