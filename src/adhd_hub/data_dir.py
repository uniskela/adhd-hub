"""Container-aware ADHD_HUB_DATA_DIR resolution and legacy path recovery.

Inside the published image the durable volume is ``/data``. A relative path such
as ``./data`` (or the host-oriented default) resolves under ``WORKDIR`` ``/app``
and is **not** the Compose/Docker volume — container recreation then looks like
an upgrade that wiped project tags, ``ai.json``, and scan-line cache.

This module remaps those ephemeral paths to ``/data`` in a container and, when
``/data`` is empty but ``/app/data`` still has Hub files, copies them over once.
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
)


def is_container_runtime() -> bool:
    """True when running in Docker/OCI (or tests force container behaviour)."""
    flag = (os.environ.get("ADHD_HUB_FORCE_CONTAINER_DATA_DIR") or "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    return Path("/.dockerenv").is_file()


def looks_like_hub_data(path: Path) -> bool:
    """True when path already holds recognizable Hub persistence files."""
    try:
        if not path.is_dir():
            return False
    except OSError:
        return False
    for name in _HUB_MARKERS:
        try:
            if (path / name).exists():
                return True
        except OSError:
            continue
    wiki = path / "wiki"
    try:
        return wiki.is_dir() and any(wiki.iterdir())
    except OSError:
        return False


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
    """Relative dirs and ``/app/data`` are lost when the container is recreated."""
    if not data_dir.is_absolute():
        return True
    return resolve_path(data_dir) == resolve_path(LEGACY_APP_DATA_DIR)


def migrate_legacy_app_data(target: Path) -> list[str]:
    """Copy Hub files from ``/app/data`` into ``target`` when target looks empty.

    Returns the list of top-level names copied. Never deletes the legacy tree
    (operators can remove it after verifying the volume).
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
    if looks_like_hub_data(target):
        return []

    target.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    try:
        entries = sorted(legacy.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        log.warning("Could not read legacy Hub data at %s: %s", legacy, exc)
        return []

    for entry in entries:
        dest = target / entry.name
        if dest.exists():
            continue
        try:
            if entry.is_dir():
                shutil.copytree(entry, dest, dirs_exist_ok=False)
            else:
                shutil.copy2(entry, dest)
            copied.append(entry.name)
        except OSError as exc:
            log.warning("Failed to migrate %s → %s: %s", entry, dest, exc)

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

    Outside a container this is a no-op (returns the resolved path unchanged in
    meaning — still the caller-supplied location). Inside a container, relative
    paths and ``/app/data`` become ``/data``.
    """
    if not is_container_runtime():
        return data_dir

    original = data_dir
    if is_ephemeral_container_data_dir(data_dir):
        log.warning(
            "ADHD_HUB_DATA_DIR=%s is ephemeral inside the container; using %s. "
            "Set ADHD_HUB_DATA_DIR=/data and mount a named volume or bind at /data "
            "so project tags, AI settings (ai.json), and scan-line cache survive upgrades.",
            original,
            CONTAINER_DATA_DIR,
        )
        data_dir = CONTAINER_DATA_DIR

    migrate_legacy_app_data(data_dir)
    return data_dir
