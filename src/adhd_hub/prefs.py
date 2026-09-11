"""Hub preferences (timezone, etc.) stored under data/prefs.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator

CONNECT_COMPANION_CHOICES = ("i-have-adhd", "graphify", "rtk")


class HubPrefs(BaseModel):
    # IANA name, e.g. Australia/Sydney. Empty/"UTC" = Coordinated Universal Time.
    timezone: str = "UTC"
    # Agents for install/connect defaults: cursor, codex, claude, and/or "*".
    # Empty = not configured in install scripts.
    connect_agents: list[str] = []
    # Optional companions included in install scripts when enabled.
    # Allowed: i-have-adhd, graphify, rtk.
    connect_companions: list[str] = []

    def public_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def connect_agents_csv(self) -> str:
        return ",".join(a.strip() for a in self.connect_agents if a and str(a).strip())

    def companion_enabled(self, name: str) -> bool:
        key = name.strip().lower()
        return key in {c.strip().lower() for c in self.connect_companions if c}

    @field_validator("connect_companions", mode="before")
    @classmethod
    def _normalize_companions(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("connect_companions must be a list")
        allowed = set(CONNECT_COMPANION_CHOICES)
        out: list[str] = []
        for item in value:
            key = str(item).strip().lower()
            if not key:
                continue
            if key not in allowed:
                raise ValueError(
                    f"Unknown connect companion {key!r}; "
                    f"allowed: {', '.join(CONNECT_COMPANION_CHOICES)}"
                )
            if key not in out:
                out.append(key)
        return out


def prefs_path(data_dir: Path) -> Path:
    return data_dir / "prefs.json"


def load_prefs(data_dir: Path, *, default_timezone: str = "UTC") -> HubPrefs:
    path = prefs_path(data_dir)
    base = HubPrefs(timezone=default_timezone or "UTC")
    if not path.is_file():
        return base
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base
    merged = base.model_dump()
    merged.update({k: v for k, v in raw.items() if v is not None})
    return HubPrefs.model_validate(merged)


def save_prefs(data_dir: Path, prefs: HubPrefs) -> Path:
    path = prefs_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs.model_dump(), indent=2) + "\n", encoding="utf-8")
    return path
