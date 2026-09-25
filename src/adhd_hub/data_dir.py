"""Container-aware ADHD_HUB_DATA_DIR resolution and legacy path recovery.

Inside the published image the durable volume is ``/data``. The known default
``./data`` resolves under ``WORKDIR`` ``/app`` to ``/app/data`` and is **not**
the Compose/Docker volume — container recreation then looks like an upgrade that
wiped project tags, ``ai.json``, and scan-line cache.

This module remaps that known ephemeral path to ``/data`` in a container and,
when ``/data`` still lacks Hub files that exist under ``/app/data``, copies the
missing entries over (without overwriting). Custom relative or bind-mount paths
are left alone after resolve.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

# Image VOLUME and Compose mount target (Dockerfile ADHD_HUB_DATA_DIR).
CONTAINER_DATA_DIR = Path("/data")
# Default Path.cwd()/data when WORKDIR is /app and DATA_DIR was relative.
LEGACY_APP_DATA_DIR = Path("/app/data")

_HUB_MARKERS = (
    "hub.sqlite3",
    "ai.json",
    "prefs.json",
    "forge.json",
    "openclaw.json",
    "browser_sessions.sqlite3",
    "connect.sqlite3",
)


def is_container_runtime() -> bool:
    """True when running in Docker/OCI (or tests force container behaviour)."""
    flag = (os.environ.get("ADHD_HUB_FORCE_CONTAINER_DATA_DIR") or "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    return Path("/.dockerenv").is_file()


def _wiki_has_real_files(wiki: Path) -> bool:
    """True when wiki contains at least one file (empty scaffold dirs do not count)."""
    try:
        if not wiki.is_dir():
            return False
        for _root, _dirs, files in os.walk(wiki):
            if files:
                return True
    except OSError:
        return False
    return False


def looks_like_hub_data(path: Path) -> bool:
    """True when path already holds recognizable Hub persistence files.

    Empty ``wiki/`` / ``wiki/projects/`` scaffolding from ``ensure_dirs`` is not
    enough — those directories alone must not skip legacy migration or mark health
    as populated.
    """
    try:
        if not path.is_dir():
            return False
    except OSError:
        return False
    for name in _HUB_MARKERS:
        try:
            if (path / name).is_file():
                return True
        except OSError:
            continue
    return _wiki_has_real_files(path / "wiki")


def resolve_path(data_dir: Path) -> Path:
    """Expand ``~`` and resolve relative paths against the process cwd."""
    path = Path(data_dir).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        return path.resolve()
    except OSError:
        return path


def is_ephemeral_container_data_dir(data_dir: Path) -> bool:
    """True only for the known ``/app/data`` default (not other relative mounts)."""
    try:
        return resolve_path(data_dir) == resolve_path(LEGACY_APP_DATA_DIR)
    except OSError:
        return False


def _copy_missing(src: Path, dest: Path) -> bool:
    """Copy ``src`` into ``dest`` without overwriting existing files.

    Returns True if at least one new file was written (dirs alone do not count).
    """
    try:
        if src.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            wrote = False
            for child in sorted(src.iterdir(), key=lambda p: p.name):
                if _copy_missing(child, dest / child.name):
                    wrote = True
            return wrote
        if dest.exists():
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return True
    except OSError as exc:
        log.warning("Failed to migrate %s → %s: %s", src, dest, exc)
        return False


def migrate_legacy_app_data(target: Path) -> list[str]:
    """Copy missing Hub files from ``/app/data`` into ``target``.

    Resumes after a partial/interrupted copy: existing target files are never
    overwritten; only absent paths are filled. Returns top-level names that
    received at least one new file. Never deletes the legacy tree (operators can
    remove it after verifying the volume).
    """
    target = resolve_path(target)
    legacy = LEGACY_APP_DATA_DIR
    if not looks_like_hub_data(legacy):
        return []
    try:
        if resolve_path(legacy) == target:
            return []
    except OSError:
        pass

    target.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    try:
        entries = sorted(legacy.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        log.warning("Could not read legacy Hub data at %s: %s", legacy, exc)
        return []

    for entry in entries:
        dest = target / entry.name
        if _copy_missing(entry, dest):
            copied.append(entry.name)

    if copied:
        log.warning(
            "Migrated Hub data from ephemeral %s into %s (%s). "
            "Confirm the Compose/Docker volume mounts at /data, then you may "
            "remove /app/data inside the old container layer.",
            legacy,
            target,
            ", ".join(copied),
        )
    return copied


def apply_container_data_dir(data_dir: Path) -> Path:
    """Return the durable data dir for this process; migrate legacy files if needed.

    Outside a container this is a no-op (returns the caller-supplied path).
    Inside a container, only the known ``/app/data`` default becomes ``/data``;
    other configured relative or absolute paths are preserved after resolve.
    """
    if not is_container_runtime():
        return data_dir

    original = data_dir
    if is_ephemeral_container_data_dir(data_dir):
        log.warning(
            "ADHD_HUB_DATA_DIR=%s resolves to ephemeral %s inside the container; "
            "using %s. Set ADHD_HUB_DATA_DIR=/data and mount a named volume or "
            "bind at /data so project tags, AI settings (ai.json), and scan-line "
            "cache survive upgrades.",
            original,
            LEGACY_APP_DATA_DIR,
            CONTAINER_DATA_DIR,
        )
        data_dir = CONTAINER_DATA_DIR

    migrate_legacy_app_data(data_dir)
    return data_dir
