"""Persisted Wave 6 AI scan-line settings with an encrypted API key.

Mirrors OpenClaw: env vars bootstrap a fresh instance; Settings → Preferences
owns ongoing admin. The API key is encrypted with the Hub auth token and never
returned to the browser.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field, field_validator

log = logging.getLogger(__name__)

DEFAULT_AI_MODEL = "llama3.2"
# Local / proxy models (Ollama, Codex-lb, etc.) often need longer than a few seconds.
DEFAULT_AI_TIMEOUT = 15.0
MAX_AI_TIMEOUT = 30.0


class AiConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Soft default: off until enabled (env base URL still opts in via ai_from_settings).
    enabled: bool = False
    base_url: str = ""
    model: str = DEFAULT_AI_MODEL
    api_key: str = ""
    timeout_seconds: float = Field(default=DEFAULT_AI_TIMEOUT, gt=0, le=MAX_AI_TIMEOUT)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        cleaned = (value or "").strip().rstrip("/")
        if not cleaned:
            return ""
        parsed = urlsplit(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("AI base URL must be a complete http(s) URL")
        if parsed.username or parsed.password:
            raise ValueError("AI base URL must not contain credentials")
        return cleaned

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        from adhd_hub.ai_client import normalize_openai_model_id

        cleaned = normalize_openai_model_id(value or "")
        return cleaned or DEFAULT_AI_MODEL

    def is_active(self) -> bool:
        return bool(self.enabled and self.base_url)

    def public_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "api_key_configured": bool(self.api_key),
            "active": self.is_active(),
        }


def ai_config_path(data_dir: Path) -> Path:
    return data_dir / "ai.json"


def _cipher(auth_token: str) -> Fernet:
    digest = hashlib.sha256(f"adhd-hub-ai-v1:{auth_token}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def ai_from_settings(settings: Any) -> AiConfig:
    """Bootstrap from env/Settings. A non-empty env base URL counts as opted-in."""
    base = str(getattr(settings, "ai_base_url", None) or "").strip()
    key = str(getattr(settings, "ai_api_key", None) or "")
    model = str(getattr(settings, "ai_model", None) or DEFAULT_AI_MODEL)
    timeout = float(getattr(settings, "ai_timeout_seconds", DEFAULT_AI_TIMEOUT) or DEFAULT_AI_TIMEOUT)
    return AiConfig(
        enabled=bool(base),
        base_url=base,
        model=model,
        api_key=key,
        timeout_seconds=timeout,
    )


def load_ai_config(
    data_dir: Path,
    *,
    env_defaults: AiConfig,
    auth_token: str,
) -> AiConfig:
    path = ai_config_path(data_dir)
    if not path.is_file():
        return env_defaults
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return env_defaults
    merged = env_defaults.model_dump()
    merged.update({k: v for k, v in raw.items() if k != "api_key_encrypted" and v is not None})
    if "api_key_encrypted" in raw:
        encrypted = raw.get("api_key_encrypted")
        merged["api_key"] = ""
        if isinstance(encrypted, str) and encrypted:
            try:
                merged["api_key"] = _cipher(auth_token).decrypt(encrypted.encode()).decode()
            except (InvalidToken, UnicodeDecodeError):
                log.warning(
                    "Saved AI API key could not be decrypted; re-enter it in Settings"
                )
    return AiConfig.model_validate(merged)


def save_ai_config(data_dir: Path, config: AiConfig, *, auth_token: str) -> Path:
    path = ai_config_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(exclude={"api_key"})
    payload["api_key_encrypted"] = (
        _cipher(auth_token).encrypt(config.api_key.encode()).decode() if config.api_key else ""
    )
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path
