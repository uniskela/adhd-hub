from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from adhd_hub.work_identity import ExternalIdentity, WorkSource, normalize_host

DEFAULT_CONNECTION_PROFILE_ID = "default"
_PROFILES_MIGRATED_META = "forge_connection_profiles_migrated_v1"


class ForgeProvider(StrEnum):
    none = "none"
    github = "github"
    gitea = "gitea"


class IssueImportPolicy(StrEnum):
    manual = "manual"
    all_open = "all_open"
    labels = "labels"
    assigned_to_me = "assigned_to_me"
    adhd_inbox = "adhd_inbox"


class ForgeConnectionProfile(BaseModel):
    """Named forge credentials + per-profile discovery policy."""

    id: str
    name: str = ""
    provider: ForgeProvider = ForgeProvider.none
    token: str = ""
    base_url: str = "https://api.github.com"
    web_base_url: str = "https://github.com"
    owner: str = ""
    repo: str = ""
    issue_import_policy: IssueImportPolicy = IssueImportPolicy.manual
    issue_import_labels: list[str] = Field(default_factory=list)
    forge_account_login: str = ""
    publish_hub_status_block: bool = False

    def display_name(self) -> str:
        if self.name.strip():
            return self.name.strip()
        host = profile_canonical_host(self) or self.provider.value
        return f"{self.provider.value} — {host}"


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
    # Poll forge issues (hub label OR [ADHD] title) and import as threads (cloud mailbox).
    board_inbox_enabled: bool = False
    # After import: close the issue and add this label (never delete).
    board_inbox_synced_label: str = "adhd-hub-synced"
    # Forge usernames allowed to create inbox issues (login / username). Fail closed:
    # when inbox is enabled but this list is empty, import nothing.
    board_inbox_authors: list[str] = Field(default_factory=list)
    # GitHub Projects v2 number (org/user project), or Gitea project id as string
    project_number: int | None = None
    project_id: str | None = None  # Gitea numeric id as string, or GitHub node id if known
    issue_labels: list[str] = Field(default_factory=lambda: ["adhd-hub"])

    # Foundation B2a — repo-primary import / mirror controls (mirrored from default profile)
    issue_import_policy: IssueImportPolicy = IssueImportPolicy.manual
    issue_import_labels: list[str] = Field(default_factory=list)
    forge_account_login: str = ""
    board_mirror_local: bool = False
    board_inbox_close_imported: bool = False
    publish_hub_status_block: bool = False

    # v0.8.1 — multi-forge connection profiles
    connection_profiles: list[ForgeConnectionProfile] = Field(default_factory=list)
    default_connection_profile_id: str | None = None

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

    def profile_by_id(self, profile_id: str | None) -> ForgeConnectionProfile | None:
        if not profile_id:
            return None
        for prof in self.connection_profiles:
            if prof.id == profile_id:
                return prof
        return None

    def default_profile(self) -> ForgeConnectionProfile | None:
        return self.profile_by_id(self.default_connection_profile_id)

    def public_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        data["token"] = _mask_token(self.token)
        profiles = []
        for prof in self.connection_profiles:
            row = prof.model_dump()
            row["token"] = _mask_token(prof.token)
            row["name"] = prof.display_name()
            profiles.append(row)
        data["connection_profiles"] = profiles
        return data


def _mask_token(token: str) -> str:
    if not token:
        return ""
    return "***" + token[-4:] if len(token) > 4 else "***"


def _is_masked_token(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("***")


def forge_config_path(data_dir: Path) -> Path:
    return data_dir / "forge.json"


def profile_canonical_host(profile: ForgeConnectionProfile) -> str | None:
    if profile.provider == ForgeProvider.none:
        return None
    src = WorkSource(profile.provider.value)
    browse = profile.web_base_url or profile.base_url
    if profile.provider == ForgeProvider.gitea:
        web = (profile.web_base_url or "").rstrip("/")
        if web and "github.com" not in web:
            browse = web
        else:
            browse = profile.base_url.rstrip("/").removesuffix("/api/v1")
    try:
        return normalize_host(src, browse)
    except ValueError:
        return None


def profile_matches_identity_host(
    profile: ForgeConnectionProfile, identity: ExternalIdentity
) -> bool:
    if profile.provider == ForgeProvider.none or not profile.token:
        return False
    if identity.provider.value != profile.provider.value:
        return False
    if identity.provider == WorkSource.github:
        return profile.provider == ForgeProvider.github
    host = profile_canonical_host(profile)
    return bool(host and host == identity.host)


def config_from_profile(
    base: ForgeConfig, profile: ForgeConnectionProfile
) -> ForgeConfig:
    """Build an operational ForgeConfig from a profile + hub-level wiki/board flags."""
    data = base.model_dump()
    data.update(
        {
            "provider": profile.provider,
            "token": profile.token,
            "base_url": profile.base_url,
            "web_base_url": profile.web_base_url,
            "owner": profile.owner or base.owner,
            "repo": profile.repo or base.repo,
            "issue_import_policy": profile.issue_import_policy,
            "issue_import_labels": list(profile.issue_import_labels),
            "forge_account_login": profile.forge_account_login,
            "publish_hub_status_block": profile.publish_hub_status_block,
        }
    )
    return ForgeConfig.model_validate(data)


def _legacy_needs_default_profile(cfg: ForgeConfig) -> bool:
    if cfg.connection_profiles:
        return False
    return cfg.provider != ForgeProvider.none or bool(cfg.token or cfg.owner or cfg.repo)


def ensure_connection_profiles(
    cfg: ForgeConfig,
    *,
    incoming_override: ForgeConfig | None = None,
) -> ForgeConfig:
    """Ensure connection_profiles exist; migrate legacy top-level forge into default."""
    del incoming_override  # reserved for callers that already merged payloads
    if cfg.connection_profiles:
        # Keep top-level mirrored from default profile for wiki/scaffold callers.
        default = cfg.default_profile()
        if default is None and cfg.default_connection_profile_id is None:
            cfg = cfg.model_copy(
                update={"default_connection_profile_id": cfg.connection_profiles[0].id}
            )
            default = cfg.default_profile()
        if default:
            cfg = cfg.model_copy(
                update={
                    "provider": default.provider,
                    "token": default.token or cfg.token,
                    "base_url": default.base_url or cfg.base_url,
                    "web_base_url": default.web_base_url or cfg.web_base_url,
                    "owner": default.owner or cfg.owner,
                    "repo": default.repo or cfg.repo,
                    "issue_import_policy": default.issue_import_policy,
                    "issue_import_labels": list(default.issue_import_labels),
                    "forge_account_login": default.forge_account_login,
                    "publish_hub_status_block": default.publish_hub_status_block,
                }
            )
        return cfg

    if not _legacy_needs_default_profile(cfg):
        return cfg

    host = None
    try:
        if cfg.provider != ForgeProvider.none:
            host = normalize_host(
                WorkSource(cfg.provider.value), cfg.web_browse_root() or cfg.base_url
            )
    except ValueError:
        host = None
    name = f"{cfg.provider.value} — {host or cfg.provider.value}"
    profile = ForgeConnectionProfile(
        id=DEFAULT_CONNECTION_PROFILE_ID,
        name=name,
        provider=cfg.provider,
        token=cfg.token,
        base_url=cfg.base_url,
        web_base_url=cfg.web_base_url,
        owner=cfg.owner,
        repo=cfg.repo,
        issue_import_policy=cfg.issue_import_policy,
        issue_import_labels=list(cfg.issue_import_labels),
        forge_account_login=cfg.forge_account_login,
        publish_hub_status_block=cfg.publish_hub_status_block,
    )
    return cfg.model_copy(
        update={
            "connection_profiles": [profile],
            "default_connection_profile_id": DEFAULT_CONNECTION_PROFILE_ID,
        }
    )


def merge_forge_config_payload(current: ForgeConfig, payload: dict[str, Any]) -> ForgeConfig:
    """Merge UI/API payload into current config, preserving masked tokens."""
    data = current.model_dump()
    incoming = {k: v for k, v in payload.items() if v is not None}
    if _is_masked_token(incoming.get("token")):
        incoming.pop("token", None)
    profiles_raw = incoming.pop("connection_profiles", None)
    data.update(incoming)
    if isinstance(profiles_raw, list):
        current_by_id = {p.id: p for p in current.connection_profiles}
        merged_profiles: list[dict[str, Any]] = []
        for raw in profiles_raw:
            if not isinstance(raw, dict):
                continue
            pid = str(raw.get("id") or "").strip()
            if not pid:
                continue
            prev = current_by_id.get(pid)
            row = prev.model_dump() if prev else {}
            row.update({k: v for k, v in raw.items() if v is not None})
            if _is_masked_token(row.get("token")):
                row["token"] = prev.token if prev else ""
            elif not row.get("token") and prev:
                row["token"] = prev.token
            row["id"] = pid  # immutable once set
            merged_profiles.append(row)
        data["connection_profiles"] = merged_profiles
    cfg = ForgeConfig.model_validate(data)
    return ensure_connection_profiles(cfg)


def load_forge_config(data_dir: Path, env_defaults: ForgeConfig | None = None) -> ForgeConfig:
    base = env_defaults or ForgeConfig()
    path = forge_config_path(data_dir)
    if not path.is_file():
        return ensure_connection_profiles(base)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ensure_connection_profiles(base)
    if not isinstance(raw, dict):
        return ensure_connection_profiles(base)
    merged = base.model_dump()
    merged.update({k: v for k, v in raw.items() if v is not None})
    # Keep existing token if UI sent masked value
    if _is_masked_token(merged.get("token")):
        merged["token"] = base.token
    # Migrated inbox installs: retain adhd_inbox when policy key was absent.
    if "issue_import_policy" not in raw and bool(raw.get("board_inbox_enabled")):
        merged["issue_import_policy"] = IssueImportPolicy.adhd_inbox.value
    # Preserve profile tokens when masked in file (shouldn't happen) or partial loads
    if isinstance(merged.get("connection_profiles"), list):
        base_profiles = {
            p["id"]: p
            for p in (base.model_dump().get("connection_profiles") or [])
            if isinstance(p, dict) and p.get("id")
        }
        fixed = []
        for row in merged["connection_profiles"]:
            if not isinstance(row, dict):
                continue
            if _is_masked_token(row.get("token")):
                prev = base_profiles.get(str(row.get("id") or ""))
                row = dict(row)
                row["token"] = (prev or {}).get("token") or ""
            fixed.append(row)
        merged["connection_profiles"] = fixed
    cfg = ForgeConfig.model_validate(merged)
    ensured = ensure_connection_profiles(cfg)
    # Persist migration when profiles were synthesized from legacy top-level fields.
    if not cfg.connection_profiles and ensured.connection_profiles:
        save_forge_config(data_dir, ensured)
    return ensured


def save_forge_config(data_dir: Path, config: ForgeConfig) -> Path:
    path = forge_config_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    config = ensure_connection_profiles(config)
    payload = config.model_dump()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def host_from_repo_url(repo_url: str | None) -> str | None:
    if not repo_url or not str(repo_url).strip():
        return None
    try:
        parsed = urlparse(str(repo_url).strip())
        host = (parsed.hostname or "").strip().casefold()
        return host or None
    except ValueError:
        return None


def _parse_inbox_authors(raw: Any) -> list[str]:
    """Normalize allowlist from env (comma string) or list."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [part.strip() for part in str(raw).replace(";", ",").split(",") if part.strip()]


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
        board_inbox_enabled=bool(getattr(settings, "forge_board_inbox_enabled", False)),
        board_inbox_synced_label=getattr(settings, "forge_board_inbox_synced_label", None)
        or "adhd-hub-synced",
        board_inbox_authors=_parse_inbox_authors(
            getattr(settings, "forge_board_inbox_authors", None)
        ),
        project_number=getattr(settings, "forge_project_number", None),
        project_id=getattr(settings, "forge_project_id", None),
    )
