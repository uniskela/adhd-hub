"""Container data_dir remap and legacy /app/data migration."""

from __future__ import annotations

import errno
from pathlib import Path
from unittest.mock import patch

from adhd_hub.config import Settings, load_settings
from adhd_hub.data_dir import (
    MIGRATION_COMPLETE_MARKER,
    _publish_new_file,
    apply_container_data_dir,
    is_container_runtime,
    looks_like_hub_data,
    migrate_legacy_app_data,
    migration_completed,
)
from adhd_hub.models import ProjectUpsert
from adhd_hub.service import HubService


def test_relative_data_dir_remaps_in_container(tmp_path, monkeypatch):
    """Only the known WORKDIR ./data → /app/data default remaps to /data."""
    monkeypatch.setenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", "1")
    app_root = tmp_path / "app"
    app_root.mkdir()
    monkeypatch.chdir(app_root)
    legacy = app_root / "data"
    fake_data = tmp_path / "volume-data"
    fake_data.mkdir()
    monkeypatch.setattr("adhd_hub.data_dir.CONTAINER_DATA_DIR", fake_data)
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)

    resolved = apply_container_data_dir(Path("./data"))
    assert resolved == fake_data


def test_custom_relative_path_preserved_in_container(tmp_path, monkeypatch):
    monkeypatch.setenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", "1")
    app_root = tmp_path / "app"
    app_root.mkdir()
    monkeypatch.chdir(app_root)
    fake_data = tmp_path / "volume-data"
    fake_data.mkdir()
    monkeypatch.setattr("adhd_hub.data_dir.CONTAINER_DATA_DIR", fake_data)
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", app_root / "data")

    path = Path("./persistent")
    assert apply_container_data_dir(path) == path


def test_legacy_app_data_path_remaps_in_container(tmp_path, monkeypatch):
    monkeypatch.setenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", "1")
    fake_data = tmp_path / "volume-data"
    fake_data.mkdir()
    legacy = tmp_path / "app-data"
    legacy.mkdir()
    monkeypatch.setattr("adhd_hub.data_dir.CONTAINER_DATA_DIR", fake_data)
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)

    resolved = apply_container_data_dir(legacy)
    assert resolved == fake_data


def test_non_container_relative_path_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", "0")
    monkeypatch.chdir(tmp_path)
    path = Path("./data")
    assert apply_container_data_dir(path) == path


def test_is_container_runtime_detects_podman_containerenv(monkeypatch):
    """Podman uses /run/.containerenv instead of /.dockerenv."""
    monkeypatch.delenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", raising=False)

    class _ProbePath:
        def __init__(self, arg: object) -> None:
            self._arg = str(arg)

        def is_file(self) -> bool:
            return self._arg == "/run/.containerenv"

    with patch("adhd_hub.data_dir.Path", _ProbePath):
        assert is_container_runtime() is True


def test_is_container_runtime_env_override_beats_markers(monkeypatch):
    monkeypatch.setenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", "0")
    assert is_container_runtime() is False
    monkeypatch.setenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", "1")
    assert is_container_runtime() is True


def test_mounted_app_data_not_remapped(tmp_path, monkeypatch):
    """When /app/data is itself a volume/bind, keep it — do not redirect to /data."""
    monkeypatch.setenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", "1")
    legacy = tmp_path / "app-data"
    legacy.mkdir()
    fake_data = tmp_path / "volume-data"
    fake_data.mkdir()
    monkeypatch.setattr("adhd_hub.data_dir.CONTAINER_DATA_DIR", fake_data)
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)

    with patch("adhd_hub.data_dir._is_mount", return_value=True):
        assert apply_container_data_dir(legacy) == legacy
    assert not migration_completed(fake_data)
    assert not (fake_data / "hub.sqlite3").exists()


def test_migrate_skips_sqlite_sidecars_when_target_db_exists(tmp_path, monkeypatch):
    """Do not attach legacy -wal/-shm/-journal to a different existing target DB."""
    legacy = tmp_path / "app-data"
    target = tmp_path / "volume"
    legacy.mkdir()
    target.mkdir()
    (legacy / "hub.sqlite3").write_bytes(b"legacy-db")
    (legacy / "hub.sqlite3-wal").write_bytes(b"legacy-wal")
    (legacy / "hub.sqlite3-shm").write_bytes(b"legacy-shm")
    (legacy / "hub.sqlite3-journal").write_bytes(b"legacy-journal")
    (legacy / "ai.json").write_text('{"enabled": true}\n', encoding="utf-8")
    (target / "hub.sqlite3").write_bytes(b"target-db")
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)

    copied = migrate_legacy_app_data(target)
    assert "ai.json" in copied
    assert "hub.sqlite3-wal" not in copied
    assert "hub.sqlite3-shm" not in copied
    assert "hub.sqlite3-journal" not in copied
    assert (target / "hub.sqlite3").read_bytes() == b"target-db"
    assert not (target / "hub.sqlite3-wal").exists()
    assert not (target / "hub.sqlite3-shm").exists()
    assert not (target / "hub.sqlite3-journal").exists()
    assert (target / "ai.json").is_file()
    assert migration_completed(target)


def test_migrate_copies_sqlite_sidecars_with_missing_db(tmp_path, monkeypatch):
    """When the target DB is absent, copy DB + sidecars together as a unit."""
    legacy = tmp_path / "app-data"
    target = tmp_path / "volume"
    legacy.mkdir()
    target.mkdir()
    (legacy / "hub.sqlite3").write_bytes(b"legacy-db")
    (legacy / "hub.sqlite3-wal").write_bytes(b"legacy-wal")
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)

    copied = migrate_legacy_app_data(target)
    assert set(copied) >= {"hub.sqlite3", "hub.sqlite3-wal"}
    assert (target / "hub.sqlite3").read_bytes() == b"legacy-db"
    assert (target / "hub.sqlite3-wal").read_bytes() == b"legacy-wal"
    assert migration_completed(target)


def test_absolute_custom_dir_unchanged_in_container(tmp_path, monkeypatch):
    monkeypatch.setenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", "1")
    custom = tmp_path / "custom-mount"
    custom.mkdir()
    assert apply_container_data_dir(custom) == custom


def test_custom_data_dir_skips_automatic_legacy_migration(tmp_path, monkeypatch):
    """Custom mounts must not receive leftover /app/data copies."""
    monkeypatch.setenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", "1")
    legacy = tmp_path / "app-data"
    legacy.mkdir()
    (legacy / "ai.json").write_text('{"enabled": true}\n', encoding="utf-8")
    custom = tmp_path / "custom-mount"
    custom.mkdir()
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)
    monkeypatch.setattr("adhd_hub.data_dir.CONTAINER_DATA_DIR", tmp_path / "volume-data")

    assert apply_container_data_dir(custom) == custom
    assert not (custom / "ai.json").exists()
    assert not migration_completed(custom)


def test_remap_runs_legacy_migration_into_volume(tmp_path, monkeypatch):
    monkeypatch.setenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", "1")
    app_root = tmp_path / "app"
    app_root.mkdir()
    monkeypatch.chdir(app_root)
    legacy = app_root / "data"
    legacy.mkdir()
    (legacy / "hub.sqlite3").write_bytes(b"sqlite")
    fake_data = tmp_path / "volume-data"
    fake_data.mkdir()
    monkeypatch.setattr("adhd_hub.data_dir.CONTAINER_DATA_DIR", fake_data)
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)

    assert apply_container_data_dir(Path("./data")) == fake_data
    assert (fake_data / "hub.sqlite3").read_bytes() == b"sqlite"
    assert migration_completed(fake_data)


def test_empty_wiki_scaffolding_not_populated(tmp_path):
    root = tmp_path / "data"
    (root / "wiki" / "projects").mkdir(parents=True)
    assert looks_like_hub_data(root) is False


def test_wiki_with_real_file_is_populated(tmp_path):
    root = tmp_path / "data"
    wiki = root / "wiki" / "projects"
    wiki.mkdir(parents=True)
    (wiki / "x.md").write_text("# x\n", encoding="utf-8")
    assert looks_like_hub_data(root) is True


def test_migrate_legacy_app_data_copies_markers(tmp_path, monkeypatch):
    legacy = tmp_path / "app-data"
    target = tmp_path / "volume"
    legacy.mkdir()
    target.mkdir()
    (legacy / "hub.sqlite3").write_bytes(b"sqlite")
    (legacy / "ai.json").write_text('{"enabled": true}\n', encoding="utf-8")
    wiki = legacy / "wiki" / "projects"
    wiki.mkdir(parents=True)
    (wiki / "x.md").write_text("# x\n", encoding="utf-8")

    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)
    copied = migrate_legacy_app_data(target)
    assert set(copied) >= {"hub.sqlite3", "ai.json", "wiki"}
    assert (target / "hub.sqlite3").read_bytes() == b"sqlite"
    assert (target / "ai.json").is_file()
    assert (target / "wiki" / "projects" / "x.md").is_file()
    assert (legacy / "hub.sqlite3").is_file()
    assert migration_completed(target)


def test_migrate_skips_existing_files_without_overwrite(tmp_path, monkeypatch):
    legacy = tmp_path / "app-data"
    target = tmp_path / "volume"
    legacy.mkdir()
    target.mkdir()
    (legacy / "hub.sqlite3").write_bytes(b"old")
    (target / "hub.sqlite3").write_bytes(b"new")
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)
    # Target already has the only legacy file → nothing new to copy.
    assert migrate_legacy_app_data(target) == []
    assert (target / "hub.sqlite3").read_bytes() == b"new"
    assert migration_completed(target)


def test_migrate_resumes_after_partial_copy(tmp_path, monkeypatch):
    legacy = tmp_path / "app-data"
    target = tmp_path / "volume"
    legacy.mkdir()
    target.mkdir()
    (legacy / "hub.sqlite3").write_bytes(b"sqlite")
    (legacy / "ai.json").write_text('{"enabled": true}\n', encoding="utf-8")
    # Interrupted earlier: sqlite landed, ai.json did not.
    (target / "hub.sqlite3").write_bytes(b"sqlite")
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)

    copied = migrate_legacy_app_data(target)
    assert copied == ["ai.json"]
    assert (target / "ai.json").read_text(encoding="utf-8") == '{"enabled": true}\n'
    assert (target / "hub.sqlite3").read_bytes() == b"sqlite"
    assert migration_completed(target)


def test_migrate_does_not_restore_after_completion(tmp_path, monkeypatch):
    legacy = tmp_path / "app-data"
    target = tmp_path / "volume"
    legacy.mkdir()
    target.mkdir()
    (legacy / "hub.sqlite3").write_bytes(b"sqlite")
    (legacy / "ai.json").write_text('{"enabled": true}\n', encoding="utf-8")
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)

    assert set(migrate_legacy_app_data(target)) >= {"hub.sqlite3", "ai.json"}
    assert migration_completed(target)

    (target / "ai.json").unlink()
    assert migrate_legacy_app_data(target) == []
    assert not (target / "ai.json").exists()


def test_migrate_retries_after_copy_failure(tmp_path, monkeypatch):
    legacy = tmp_path / "app-data"
    target = tmp_path / "volume"
    legacy.mkdir()
    target.mkdir()
    (legacy / "hub.sqlite3").write_bytes(b"sqlite")
    (legacy / "ai.json").write_text('{"enabled": true}\n', encoding="utf-8")
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)

    real_copy = None
    import adhd_hub.data_dir as data_dir_mod

    real_copy = data_dir_mod._copy_file_atomic
    calls = {"ai": 0}

    def flaky_copy(src: Path, dest: Path):
        if src.name == "ai.json" and calls["ai"] == 0:
            calls["ai"] += 1
            return None
        return real_copy(src, dest)

    with patch.object(data_dir_mod, "_copy_file_atomic", side_effect=flaky_copy):
        first = migrate_legacy_app_data(target)
    assert "hub.sqlite3" in first
    assert "ai.json" not in first
    assert not migration_completed(target)

    second = migrate_legacy_app_data(target)
    assert second == ["ai.json"]
    assert (target / "ai.json").is_file()
    assert migration_completed(target)


def test_migrate_atomic_copy_cleans_temp_on_failure(tmp_path, monkeypatch):
    legacy = tmp_path / "app-data"
    target = tmp_path / "volume"
    legacy.mkdir()
    target.mkdir()
    (legacy / "hub.sqlite3").write_bytes(b"sqlite-payload")
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)

    import adhd_hub.data_dir as data_dir_mod

    def boom_copy2(src, dest, *args, **kwargs):
        Path(dest).write_bytes(b"partial")
        raise OSError("simulated interrupt")

    with patch.object(data_dir_mod.shutil, "copy2", side_effect=boom_copy2):
        assert migrate_legacy_app_data(target) == []
    assert not (target / "hub.sqlite3").exists()
    leftovers = list(target.glob(".hub.sqlite3.*.tmp"))
    assert leftovers == []
    assert not migration_completed(target)

    # Retry succeeds once the interrupt is gone.
    assert migrate_legacy_app_data(target) == ["hub.sqlite3"]
    assert (target / "hub.sqlite3").read_bytes() == b"sqlite-payload"


def test_publish_link_fails_when_dest_exists(tmp_path):
    dest = tmp_path / "hub.sqlite3"
    dest.write_bytes(b"other-writer")
    tmp = tmp_path / ".hub.sqlite3.staged.tmp"
    tmp.write_bytes(b"migrated")
    assert _publish_new_file(tmp, dest) is False
    assert dest.read_bytes() == b"other-writer"
    assert tmp.is_file()


def test_publish_fallback_exclusive_when_no_hardlink(tmp_path):
    dest = tmp_path / "hub.sqlite3"
    tmp = tmp_path / ".hub.sqlite3.staged.tmp"
    tmp.write_bytes(b"migrated")

    def no_hardlinks(src, dst):
        raise OSError(errno.EOPNOTSUPP, "Operation not supported")

    with patch("adhd_hub.data_dir.os.link", side_effect=no_hardlinks):
        assert _publish_new_file(tmp, dest) is True
    assert dest.read_bytes() == b"migrated"
    assert not tmp.exists()


def test_publish_fallback_does_not_overwrite_existing(tmp_path):
    """O_EXCL claim must fail closed when another writer already created dest."""
    dest = tmp_path / "hub.sqlite3"
    dest.write_bytes(b"other-writer")
    tmp = tmp_path / ".hub.sqlite3.staged.tmp"
    tmp.write_bytes(b"migrated")

    def no_hardlinks(src, dst):
        raise OSError(errno.EOPNOTSUPP, "Operation not supported")

    with patch("adhd_hub.data_dir.os.link", side_effect=no_hardlinks):
        assert _publish_new_file(tmp, dest) is False
    assert dest.read_bytes() == b"other-writer"
    assert tmp.is_file()


def test_migrate_fills_missing_wiki_under_scaffolding(tmp_path, monkeypatch):
    legacy = tmp_path / "app-data"
    target = tmp_path / "volume"
    legacy.mkdir()
    target.mkdir()
    (legacy / "hub.sqlite3").write_bytes(b"sqlite")
    wiki_src = legacy / "wiki" / "projects"
    wiki_src.mkdir(parents=True)
    (wiki_src / "x.md").write_text("# x\n", encoding="utf-8")
    # ensure_dirs-style empty scaffolding on the volume
    (target / "wiki" / "projects").mkdir(parents=True)
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)

    copied = migrate_legacy_app_data(target)
    assert "wiki" in copied
    assert (target / "wiki" / "projects" / "x.md").read_text(encoding="utf-8") == "# x\n"
    assert (target / "hub.sqlite3").read_bytes() == b"sqlite"
    assert (target / MIGRATION_COMPLETE_MARKER).is_file()


def test_load_settings_applies_container_remap(tmp_path, monkeypatch):
    monkeypatch.setenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", "1")
    monkeypatch.chdir(tmp_path)
    fake_data = tmp_path / "volume-data"
    fake_data.mkdir()
    monkeypatch.setattr("adhd_hub.data_dir.CONTAINER_DATA_DIR", fake_data)
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", tmp_path / "data")
    monkeypatch.delenv("ADHD_HUB_DATA_DIR", raising=False)
    monkeypatch.delenv("ADHD_HUB_AUTH_TOKEN", raising=False)
    (tmp_path / ".env").write_text(
        "ADHD_HUB_DATA_DIR=./data\nADHD_HUB_AUTH_TOKEN=test-token\n"
    )

    settings = load_settings()
    assert settings.data_dir == fake_data


def test_health_reports_data_dir(tmp_path):
    service = HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))
    service.upsert_project(ProjectUpsert(slug="demo", title="Demo", tags=["lab"]))
    health = service.health()
    assert health["data_dir_populated"] is True
    assert health["ai_config_present"] is False
    assert looks_like_hub_data(service.settings.data_dir)
    assert str(service.settings.data_dir.resolve()) == health["data_dir"]
