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
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# Image VOLUME and Compose mount target (Dockerfile ADHD_HUB_DATA_DIR).
CONTAINER_DATA_DIR = Path("/data")
# Default Path.cwd()/data when WORKDIR is /app and DATA_DIR was relative.
LEGACY_APP_DATA_DIR = Path("/app/data")
# Written under the target after a successful migration pass so later startups
# do not re-copy files an operator intentionally removed from the volume.
MIGRATION_COMPLETE_MARKER = ".legacy_app_data_migrated"

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


def _publish_new_file(tmp: Path, dest: Path) -> bool:
    """Publish ``tmp`` as ``dest`` only if ``dest`` does not already exist.

    Prefers ``os.link`` so publication atomically fails when ``dest`` already
    exists (never replaces). On filesystems without hard links, claims ``dest``
    with ``O_CREAT|O_EXCL`` then replaces that empty placeholder with ``tmp``.
    Never uses unconditional ``rename``/``replace`` onto a pre-existing path.
    Returns True on success, False when ``dest`` already exists.
    """
    try:
        os.link(tmp, dest)
        return True
    except FileExistsError:
        return False
    except OSError:
        pass

    # No hard-link support (or other link failure): exclusive name claim.
    try:
        fd = os.open(os.fspath(dest), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    os.close(fd)
    try:
        os.replace(tmp, dest)
        return True
    except OSError:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _copy_file_atomic(src: Path, dest: Path) -> bool | None:
    """Copy ``src`` to ``dest`` via a temp file in ``dest``'s directory.

    Returns True when a new file was published, False when ``dest`` already
    exists (skip), or None when copy/publish failed. Never leaves a permanent
    partial file at ``dest`` — failed attempts clean up the temp file.
    """
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{dest.name}.",
            suffix=".tmp",
            dir=dest.parent,
        )
        tmp = Path(tmp_name)
        os.close(fd)
        shutil.copy2(src, tmp)
        if _publish_new_file(tmp, dest):
            return True
        # Destination appeared while we were copying — treat as skip, not failure.
        return False if dest.exists() else None
    except OSError as exc:
        log.warning("Failed to migrate %s → %s: %s", src, dest, exc)
        return None
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def _copy_missing(src: Path, dest: Path) -> bool | None:
    """Copy ``src`` into ``dest`` without overwriting existing files.

    Returns True if at least one new file was written, False if nothing new was
    needed (destination already present), or None if a copy failed mid-way.
    """
    try:
        if src.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            wrote = False
            for child in sorted(src.iterdir(), key=lambda p: p.name):
                result = _copy_missing(child, dest / child.name)
                if result is None:
                    return None
                if result:
                    wrote = True
            return wrote
        if dest.exists():
            return False
        return _copy_file_atomic(src, dest)
    except OSError as exc:
        log.warning("Failed to migrate %s → %s: %s", src, dest, exc)
        return None


def _migration_marker_path(target: Path) -> Path:
    return target / MIGRATION_COMPLETE_MARKER


def migration_completed(target: Path) -> bool:
    """True when a prior successful legacy migration was recorded for ``target``."""
    try:
        return _migration_marker_path(target).is_file()
    except OSError:
        return False


def _mark_migration_complete(target: Path) -> None:
    marker = _migration_marker_path(target)
    try:
        marker.write_text("1\n", encoding="utf-8")
    except OSError as exc:
        log.warning("Could not record legacy migration completion at %s: %s", marker, exc)


def migrate_legacy_app_data(target: Path) -> list[str]:
    """Copy missing Hub files from ``/app/data`` into ``target``.

    Resumes after a partial/interrupted copy: existing target files are never
    overwritten; only absent paths are filled. After a fully successful pass,
    records completion so later calls do not restore files an operator removed.
    Incomplete migrations stay retryable. Returns top-level names that received
    at least one new file. Never deletes the legacy tree (operators can remove
    it after verifying the volume).
    """
    target = resolve_path(target)
    legacy = LEGACY_APP_DATA_DIR
    if migration_completed(target):
        return []
    if not looks_like_hub_data(legacy):
        return []
    try:
        if resolve_path(legacy) == target:
            return []
    except OSError:
        pass

    target.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    failed = False
    try:
        entries = sorted(legacy.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        log.warning("Could not read legacy Hub data at %s: %s", legacy, exc)
        return []

    for entry in entries:
        # Do not treat the completion marker as a migratable payload if present.
        if entry.name == MIGRATION_COMPLETE_MARKER:
            continue
        dest = target / entry.name
        result = _copy_missing(entry, dest)
        if result is None:
            failed = True
        elif result:
            copied.append(entry.name)

    if failed:
        log.warning(
            "Legacy Hub data migration from %s into %s was incomplete; "
            "will retry missing paths on the next startup.",
            legacy,
            target,
        )
        return copied

    _mark_migration_complete(target)
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
    Automatic legacy migration runs only when that known default was remapped.
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
