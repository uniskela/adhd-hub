from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ForgeProvider(StrEnum):
    none = "none"
    github = "github"
    gitea = "gitea"


class ForgeConfig(BaseModel):
    """Runtime forge settings (env defaults + data/forge.json overrides)."""

    provider: ForgeProvider = ForgeProvider.none
    base_url: str = "https://api.github.com"
    # For Gitea use e.g. https://gitea.example.com/api/v1
    web_base_url: str = "https://github.com"
    token: str = ""
    owner: str = ""
    repo: str = ""

    wiki_enabled: bool = False
    wiki_path: str = "adhd-hub/wiki"  # path prefix inside the repo
    wiki_branch: str = "main"
    # When true, sync also seeds README.md (+ helpers) so this forge repo
    # is clearly a dedicated ADHD Hub memory mirror (not an app codebase).
    primary_memory_repo: bool = False
    # Public hub base URL for README → /ui link (overrides ADHD_HUB_PUBLIC_URL when set).
    hub_public_url: str = ""

    board_enabled: bool = False
    # GitHub Projects v2 number (org/user project), or Gitea project id as string
    project_number: int | None = None
    project_id: str | None = None  # Gitea numeric id as string, or GitHub node id if known
    issue_labels: list[str] = Field(default_factory=lambda: ["adhd-hub"])

    def api_root(self) -> str:
        return self.base_url.rstrip("/")

    def web_browse_root(self) -> str:
        """Human-facing forge host for issue links (not the API root)."""
        if self.provider == ForgeProvider.gitea:
            web = (self.web_base_url or "").rstrip("/")
            if web and "github.com" not in web:
                return web
            root = self.base_url.rstrip("/").removesuffix("/api/v1")
            return root.rstrip("/")
        return (self.web_base_url or "https://github.com").rstrip("/")

    def issue_web_url(self, number: int) -> str | None:
        if not (self.owner and self.repo and number):
            return None
        return f"{self.web_browse_root()}/{self.owner}/{self.repo}/issues/{number}"

    def file_web_url(self, rel_path: str) -> str | None:
        """Browser URL for a file under wiki_path (Gitea/GitHub blob/src view)."""
        if not (self.owner and self.repo):
            return None
        prefix = (self.wiki_path or "").strip("/")
        full = f"{prefix}/{rel_path.lstrip('/')}" if prefix else rel_path.lstrip("/")
        branch = self.wiki_branch or "main"
        root = self.web_browse_root()
        if self.provider == ForgeProvider.gitea:
            return f"{root}/{self.owner}/{self.repo}/src/branch/{branch}/{full}"
        return f"{root}/{self.owner}/{self.repo}/blob/{branch}/{full}"

    def enabled(self) -> bool:
        return (
            self.provider != ForgeProvider.none
            and bool(self.token and self.owner and self.repo)
        )

    def public_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        if self.token:
            data["token"] = "***" + self.token[-4:] if len(self.token) > 4 else "***"
        return data


def forge_config_path(data_dir: Path) -> Path:
    return data_dir / "forge.json"


def load_forge_config(data_dir: Path, env_defaults: ForgeConfig | None = None) -> ForgeConfig:
    base = env_defaults or ForgeConfig()
    path = forge_config_path(data_dir)
    if not path.is_file():
        return base
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base
    merged = base.model_dump()
    merged.update({k: v for k, v in raw.items() if v is not None})
    # Keep existing token if UI sent masked value
    if isinstance(merged.get("token"), str) and merged["token"].startswith("***"):
        merged["token"] = base.token
    return ForgeConfig.model_validate(merged)


def save_forge_config(data_dir: Path, config: ForgeConfig) -> Path:
    path = forge_config_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def forge_from_settings(settings: Any) -> ForgeConfig:
    """Build ForgeConfig from ADHD_HUB_FORGE_* settings fields."""
    primary = bool(getattr(settings, "forge_primary_memory_repo", False))
    raw_wiki = getattr(settings, "forge_wiki_path", None)
    if raw_wiki is None or str(raw_wiki).strip() == "":
        wiki_path = "" if primary else "adhd-hub/wiki"
    else:
        wiki_path = str(raw_wiki)
    return ForgeConfig(
        provider=ForgeProvider(getattr(settings, "forge_provider", "none") or "none"),
        base_url=getattr(settings, "forge_base_url", None) or "https://api.github.com",
        web_base_url=getattr(settings, "forge_web_base_url", None) or "https://github.com",
        token=getattr(settings, "forge_token", None) or "",
        owner=getattr(settings, "forge_owner", None) or "",
        repo=getattr(settings, "forge_repo", None) or "",
        wiki_enabled=bool(getattr(settings, "forge_wiki_enabled", False)),
        wiki_path=wiki_path,
        wiki_branch=getattr(settings, "forge_wiki_branch", None) or "main",
        primary_memory_repo=primary,
        hub_public_url=(getattr(settings, "public_url", None) or getattr(settings, "hub_url", None) or "")
        or "",
        board_enabled=bool(getattr(settings, "forge_board_enabled", False)),
        project_number=getattr(settings, "forge_project_number", None),
        project_id=getattr(settings, "forge_project_id", None),
    )
