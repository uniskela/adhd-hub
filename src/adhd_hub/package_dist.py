"""Locate the CLI wheel shipped with a Hub install (Docker / local dist)."""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def wheel_search_dirs() -> list[Path]:
    """Directories that may contain a packaged CLI wheel.

    When ``ADHD_HUB_WHEEL_PATH`` / ``ADHD_HUB_WHEEL_DIR`` is set, only those
    locations are searched (so tests and Docker can isolate the package).
    """
    env_path = os.environ.get("ADHD_HUB_WHEEL_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return [p.parent]
        return [p]
    env_dir = os.environ.get("ADHD_HUB_WHEEL_DIR", "").strip()
    if env_dir:
        return [Path(env_dir)]
    return [
        Path("/app/dist"),
        _REPO_ROOT / "dist",
        Path(__file__).resolve().parent / "dist",
    ]


def find_cli_wheel() -> Path | None:
    """Return the newest ``adhd_hub-*.whl`` / ``adhd_hub-*.whl`` path if present."""
    env_file = os.environ.get("ADHD_HUB_WHEEL_PATH", "").strip()
    if env_file:
        p = Path(env_file)
        if p.is_file() and p.suffix == ".whl":
            return p
    candidates: list[Path] = []
    for directory in wheel_search_dirs():
        if not directory.is_dir():
            continue
        candidates.extend(directory.glob("adhd_hub-*.whl"))
        candidates.extend(directory.glob("adhd-hub-*.whl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)
