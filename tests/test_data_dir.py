"""Container data_dir remap and legacy /app/data migration."""

from __future__ import annotations

from pathlib import Path

from adhd_hub.config import Settings, load_settings
from adhd_hub.data_dir import (
    apply_container_data_dir,
    looks_like_hub_data,
    migrate_legacy_app_data,
)
from adhd_hub.models import ProjectUpsert
from adhd_hub.service import HubService


def test_relative_data_dir_remaps_in_container(tmp_path, monkeypatch):
    monkeypatch.setenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", "1")
    monkeypatch.chdir(tmp_path)
    fake_data = tmp_path / "volume-data"
    fake_data.mkdir()
    monkeypatch.setattr("adhd_hub.data_dir.CONTAINER_DATA_DIR", fake_data)

    resolved = apply_container_data_dir(Path("./data"))
    assert resolved == fake_data


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


def test_absolute_custom_dir_unchanged_in_container(tmp_path, monkeypatch):
    monkeypatch.setenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", "1")
    custom = tmp_path / "custom-mount"
    custom.mkdir()
    assert apply_container_data_dir(custom) == custom


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


def test_migrate_skips_when_target_populated(tmp_path, monkeypatch):
    legacy = tmp_path / "app-data"
    target = tmp_path / "volume"
    legacy.mkdir()
    target.mkdir()
    (legacy / "hub.sqlite3").write_bytes(b"old")
    (target / "hub.sqlite3").write_bytes(b"new")
    monkeypatch.setattr("adhd_hub.data_dir.LEGACY_APP_DATA_DIR", legacy)
    assert migrate_legacy_app_data(target) == []
    assert (target / "hub.sqlite3").read_bytes() == b"new"


def test_load_settings_applies_container_remap(tmp_path, monkeypatch):
    monkeypatch.setenv("ADHD_HUB_FORCE_CONTAINER_DATA_DIR", "1")
    monkeypatch.chdir(tmp_path)
    fake_data = tmp_path / "volume-data"
    fake_data.mkdir()
    monkeypatch.setattr("adhd_hub.data_dir.CONTAINER_DATA_DIR", fake_data)
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
