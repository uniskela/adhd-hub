from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    return Path.cwd() / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ADHD_HUB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8787
    data_dir: Path = Field(default_factory=_default_data_dir)
    auth_token: str = "change-me"
    stale_days: int = 3
    digest_limit: int = 5
    overlap_limit: int = 5
    remind_cooldown_days: int = 3
    digest_max_nudge: int = 2

    openclaw_webhook_url: str | None = None
    openclaw_agent_url: str | None = None
    openclaw_token: str | None = None

    stale_nudge_cron: str = "0 9 * * *"
    wiki_index_cron: str = "30 9 * * *"

    # Indexer (used by CLI; also loadable from config.toml [indexer])
    cursor_projects_dir: Path | None = None
    codex_sessions_dir: Path | None = None
    claude_projects_dir: Path | None = None
    max_sessions: int = 50
    hub_url: str | None = None
    timezone: str = "UTC"  # IANA, e.g. Australia/Sydney; also overridable via /ui prefs

    # Optional forge (GitHub / Gitea) — UI can override via data/forge.json
    forge_provider: str = "none"  # none | github | gitea
    forge_base_url: str = "https://api.github.com"
    forge_web_base_url: str = "https://github.com"
    forge_token: str | None = None
    forge_owner: str | None = None
    forge_repo: str | None = None
    forge_wiki_enabled: bool = False
    forge_wiki_path: str = "adhd-hub/wiki"
    forge_wiki_branch: str = "main"
    forge_primary_memory_repo: bool = False
    forge_board_enabled: bool = False
    forge_project_number: int | None = None
    forge_project_id: str | None = None

    def resolve_public_url(self) -> str | None:
        """Best known externally reachable hub base URL (no trailing slash)."""
        for candidate in (self.public_url, self.hub_url):
            if candidate and str(candidate).strip():
                return str(candidate).strip().rstrip("/")
        return None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "hub.sqlite3"

    @property
    def wiki_dir(self) -> Path:
        return self.data_dir / "wiki"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        (self.wiki_dir / "projects").mkdir(parents=True, exist_ok=True)


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        data = tomllib.load(f)
    flat: dict[str, Any] = {}
    for key, value in data.items():
        if key == "indexer" and isinstance(value, dict):
            for ik, iv in value.items():
                flat[ik] = iv
        elif not isinstance(value, dict):
            flat[key] = value
    return flat


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from optional TOML, then env overrides."""
    candidates: list[Path] = []
    if config_path:
        candidates.append(config_path)
    candidates.extend(
        [
            Path.cwd() / "config.toml",
            Path.home() / ".config" / "adhd-hub" / "config.toml",
        ]
    )
    file_vals: dict[str, Any] = {}
    for c in candidates:
        file_vals = _load_toml(c)
        if file_vals:
            break

    # Expand ~ in path-like fields from TOML
    for key in (
        "data_dir",
        "cursor_projects_dir",
        "codex_sessions_dir",
        "claude_projects_dir",
    ):
        if key in file_vals and isinstance(file_vals[key], str):
            file_vals[key] = Path(file_vals[key]).expanduser()

    return Settings(**file_vals)
