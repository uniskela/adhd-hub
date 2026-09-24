from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import dotenv_values
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from adhd_hub.data_dir import apply_container_data_dir

# Loopback binds only — keep in sync with oauth._LOOPBACK_HOSTS.
_LOOPBACK_BIND_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Exact placeholders that must never back a public / proxied / tunnelled Hub.
_WEAK_AUTH_TOKENS = frozenset(
    {
        "",
        "change-me",
        "change-me-to-a-long-random-string",  # .env.example copy-paste foot-gun
    }
)


def _default_data_dir() -> Path:
    return Path.cwd() / "data"


def is_weak_auth_token(token: str | None) -> bool:
    """True for empty / documented default placeholders (not a real secret)."""
    return (token or "").strip() in _WEAK_AUTH_TOKENS


def is_loopback_bind_host(host: str | None) -> bool:
    if not host:
        return False
    return host.lower().strip("[]") in _LOOPBACK_BIND_HOSTS


def public_url_is_non_loopback(url: str | None) -> bool:
    """True when a configured public/hub URL hostname is missing or not loopback."""
    if not url or not str(url).strip():
        return False
    try:
        parsed = urlparse(str(url).strip())
    except ValueError:
        return True
    host = (parsed.hostname or "").lower()
    if not host:
        return True
    return not is_loopback_bind_host(host)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ADHD_HUB_",
        env_file=None,
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
    openclaw_alerts_enabled: bool = True

    stale_nudge_cron: str = "0 9 * * *"
    wiki_index_cron: str = "30 9 * * *"
    forge_inbox_cron: str = "*/15 * * * *"
    forge_reconcile_cron: str = "*/30 * * * *"

    # Indexer (used by CLI; also loadable from config.toml [indexer])
    cursor_projects_dir: Path | None = None
    codex_sessions_dir: Path | None = None
    claude_projects_dir: Path | None = None
    max_sessions: int = 50
    public_url: str | None = None
    hub_url: str | None = None
    timezone: str = "UTC"  # IANA, e.g. Australia/Sydney; also overridable via /ui prefs
    # Cookie Secure: None = auto (https request or trusted X-Forwarded-Proto).
    cookie_secure: bool | None = None
    # When true, honour X-Forwarded-Proto / Host from a trusted reverse proxy (Tailscale, Caddy).
    trust_proxy_headers: bool = False
    # MCP OAuth discovery + challenge; disable to roll back Auth-button discovery.
    oauth_enabled: bool = True

    # Opt-in Wave 6 AI scan-lines (OpenAI-compatible; local/Ollama preferred).
    # Soft default off: needs ai_enabled + base URL (Settings UI and/or env).
    # Env URL bootstraps enabled=True via ai_config.ai_from_settings. Never send transcripts.
    # Runtime may also load overrides from data/ai.json (encrypted API key).
    ai_enabled: bool = False
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model: str = "llama3.2"
    ai_timeout_seconds: float = Field(default=15.0, gt=0, le=30, allow_inf_nan=False)

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
    forge_board_inbox_enabled: bool = False
    forge_board_inbox_synced_label: str = "adhd-hub-synced"
    # Comma-separated forge logins allowed to create inbox issues (fail closed if empty).
    forge_board_inbox_authors: str = ""
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


def validate_bind_token_safety(settings: Settings) -> None:
    """Refuse weak tokens when the Hub is (or looks) reachable beyond pure local-dev.

    Intentional local loopback + default token without PUBLIC_URL / proxy trust is OK.
    Non-loopback bind, non-loopback PUBLIC_URL/HUB_URL, or TRUST_PROXY_HEADERS → fail closed.
    """
    if not is_weak_auth_token(settings.auth_token):
        return

    problems: list[str] = []
    if not is_loopback_bind_host(settings.host):
        problems.append(f"bind host {settings.host!r} is not loopback")

    public = settings.resolve_public_url()
    if public and public_url_is_non_loopback(public):
        problems.append(f"PUBLIC_URL/HUB_URL {public!r} is not a loopback URL")

    if settings.trust_proxy_headers:
        problems.append("ADHD_HUB_TRUST_PROXY_HEADERS is enabled")

    if not problems:
        return

    raise ValueError(
        "Refusing to start with a weak/default ADHD_HUB_AUTH_TOKEN when the Hub "
        "appears reachable beyond local-only development ("
        + "; ".join(problems)
        + "). Set a long random token before using a public URL, reverse proxy, "
        "tunnel, or non-loopback bind. See docs/remote-mcp-access.md."
    )


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
    """Load settings with precedence: process env > first nonempty TOML > .env."""
    candidates: list[Path] = []
    if config_path:
        candidates.append(config_path)
    candidates.extend(
        [
            Path.cwd() / "config.toml",
            Path.home() / ".config" / "adhd-hub" / "config.toml",
        ]
    )
    file_vals: dict[str, Any] = {
        key.removeprefix("ADHD_HUB_").lower(): value
        for key, value in dotenv_values(Path.cwd() / ".env").items()
        if key.startswith("ADHD_HUB_") and value is not None
    }
    for c in candidates:
        toml_vals = _load_toml(c)
        if toml_vals:
            file_vals.update(toml_vals)
            break

    file_vals.update(
        {
            field: os.environ[f"ADHD_HUB_{field.upper()}"]
            for field in Settings.model_fields
            if f"ADHD_HUB_{field.upper()}" in os.environ
        }
    )

    # Expand ~ in path-like fields from any source.
    for key in (
        "data_dir",
        "cursor_projects_dir",
        "codex_sessions_dir",
        "claude_projects_dir",
    ):
        if key in file_vals and isinstance(file_vals[key], str):
            file_vals[key] = Path(file_vals[key]).expanduser()

    settings = Settings(**file_vals)
    # Containers: remap relative ./data → /data and recover /app/data leftovers.
    settings.data_dir = apply_container_data_dir(settings.data_dir)
    return settings
