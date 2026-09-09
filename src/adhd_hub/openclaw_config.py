"""Persisted OpenClaw connection settings with an encrypted bearer token."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from apscheduler.triggers.cron import CronTrigger
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from adhd_hub.openclaw import parse_cron

log = logging.getLogger(__name__)


class OpenClawConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    alerts_enabled: bool = False
    webhook_url: str = ""
    agent_url: str = ""
    token: str = ""
    stale_nudge_cron: str = "0 9 * * *"
    stale_days: int = Field(default=3, ge=1, le=365)
    remind_cooldown_days: int = Field(default=3, ge=1, le=365)
    digest_max_nudge: int = Field(default=2, ge=1, le=10)

    @field_validator("webhook_url", "agent_url")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        if not cleaned:
            return ""
        parsed = urlsplit(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OpenClaw endpoints must be complete http(s) URLs")
        if parsed.username or parsed.password:
            raise ValueError("OpenClaw endpoints must not contain credentials")
        return cleaned

    @field_validator("stale_nudge_cron")
    @classmethod
    def validate_schedule(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        CronTrigger(**parse_cron(cleaned))
        return cleaned

    @model_validator(mode="after")
    def enabled_alerts_have_a_target(self) -> OpenClawConfig:
        if self.alerts_enabled and not (self.webhook_url or self.agent_url):
            raise ValueError("add an OpenClaw webhook or agent URL before enabling alerts")
        return self

    def public_dict(self) -> dict[str, Any]:
        data = self.model_dump(exclude={"token"})
        data["token_configured"] = bool(self.token)
        data["configured"] = bool(self.webhook_url or self.agent_url)
        return data


def openclaw_config_path(data_dir: Path) -> Path:
    return data_dir / "openclaw.json"


def _cipher(auth_token: str) -> Fernet:
    digest = hashlib.sha256(f"adhd-hub-openclaw-v1:{auth_token}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def openclaw_from_settings(settings: Any) -> OpenClawConfig:
    webhook = str(getattr(settings, "openclaw_webhook_url", None) or "")
    agent = str(getattr(settings, "openclaw_agent_url", None) or "")
    enabled = bool(getattr(settings, "openclaw_alerts_enabled", True) and (webhook or agent))
    return OpenClawConfig(
        alerts_enabled=enabled,
        webhook_url=webhook,
        agent_url=agent,
        token=str(getattr(settings, "openclaw_token", None) or ""),
        stale_nudge_cron=str(getattr(settings, "stale_nudge_cron", "0 9 * * *")),
        stale_days=int(getattr(settings, "stale_days", 3)),
        remind_cooldown_days=int(getattr(settings, "remind_cooldown_days", 3)),
        digest_max_nudge=int(getattr(settings, "digest_max_nudge", 2)),
    )


def load_openclaw_config(
    data_dir: Path,
    *,
    env_defaults: OpenClawConfig,
    auth_token: str,
) -> OpenClawConfig:
    path = openclaw_config_path(data_dir)
    if not path.is_file():
        return env_defaults
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return env_defaults
    merged = env_defaults.model_dump()
    merged.update({k: v for k, v in raw.items() if k != "token_encrypted" and v is not None})
    if "token_encrypted" in raw:
        encrypted = raw.get("token_encrypted")
        merged["token"] = ""
        if isinstance(encrypted, str) and encrypted:
            try:
                merged["token"] = _cipher(auth_token).decrypt(encrypted.encode()).decode()
            except (InvalidToken, UnicodeDecodeError):
                log.warning("Saved OpenClaw token could not be decrypted; reconnect it in Settings")
    return OpenClawConfig.model_validate(merged)


def save_openclaw_config(data_dir: Path, config: OpenClawConfig, *, auth_token: str) -> Path:
    path = openclaw_config_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(exclude={"token"})
    payload["token_encrypted"] = (
        _cipher(auth_token).encrypt(config.token.encode()).decode() if config.token else ""
    )
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path
